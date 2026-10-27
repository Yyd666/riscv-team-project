"""Read the repository's trusted evaluation registry and seal its input bytes."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
import re


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class CaseAsset:
    case_id: str
    stdin: bytes
    expected_stdout: bytes


@dataclass(frozen=True)
class ProgramAssets:
    program_id: str
    source: bytes
    cases: tuple[CaseAsset, ...]
    case_binding_origin: str

    def input_hashes(self) -> list[dict]:
        return [{"case_id": case.case_id, "stdin_sha256": digest(case.stdin),
                 "expected_stdout_sha256": digest(case.expected_stdout)} for case in self.cases]


def asset(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or "\\" in relative or ":" in relative:
        raise ValueError("Evaluation asset must be a repository-relative POSIX path")
    posix = PurePosixPath(relative)
    if posix.is_absolute() or ".." in posix.parts:
        raise ValueError("Evaluation asset escapes repository")
    path = (root / relative).resolve(strict=True)
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError("Evaluation asset escapes repository or is not a regular file")
    if path.stat().st_size > 1048576:
        raise ValueError("Evaluation asset exceeds the baseline size limit")
    return path


def license_notice(root: Path, corpus: dict) -> bytes | None:
    """Bind new licensed registries while preserving historical corpus formats."""
    if "license_file" not in corpus and "license_sha256" not in corpus:
        if any(isinstance(entry, dict) and entry.get("license") == "MIT" for entry in corpus.get("entries", [])):
            raise ValueError("MIT-licensed evaluation entries require the bound license notice")
        return None
    if corpus.get("license_file") != "evaluation/LICENSE":
        raise ValueError("Only the registered evaluation/LICENSE notice is supported")
    raw = asset(root, "evaluation/LICENSE").read_bytes()
    if digest(raw) != corpus.get("license_sha256"):
        raise ValueError("Evaluation license hash differs from registry")
    return raw


def read_registry(root: Path, path: Path) -> tuple[dict, bytes]:
    root = root.resolve(strict=True)
    if path.resolve(strict=True) != (root / "evaluation/corpus.json").resolve(strict=True):
        raise ValueError("Only the repository's registered evaluation/corpus.json is executable")
    raw = asset(root, "evaluation/corpus.json").read_bytes()
    document = json.loads(raw)
    if not isinstance(document, dict) or not isinstance(document.get("entries"), list) or not document["entries"]:
        raise ValueError("Evaluation registry must contain a non-empty entries list")
    if not isinstance(document.get("corpus_version"), str) or not document["corpus_version"]:
        raise ValueError("Evaluation corpus_version is missing")
    license_notice(root, document)
    seen = set()
    for entry in document["entries"]:
        if not isinstance(entry, dict) or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", str(entry.get("program_id", ""))):
            raise ValueError("Invalid evaluation program ID")
        program = entry["program_id"]
        if program in seen:
            raise ValueError("Duplicate evaluation program ID")
        seen.add(program)
        if entry.get("split") not in {"development", "held_out"}:
            raise ValueError(f"Invalid split for {program}")
        if any(not isinstance(entry.get(key), str) or not entry[key]
               for key in ("family", "provenance", "source_origin", "license")):
            raise ValueError(f"Missing family, provenance, source origin or license for {program}")
        allowed = {f"benchmarks/{program}/main.c", f"evaluation/programs/{program}/main.c"}
        if entry.get("source") not in allowed:
            raise ValueError(f"Unregistered source layout for {program}")
        if not re.fullmatch(r"[a-f0-9]{64}", str(entry.get("source_sha256", ""))):
            raise ValueError(f"Missing source hash for {program}")
    return document, raw


def prepare_program(root: Path, entry: dict, *, diagnostic: bool) -> ProgramAssets:
    source = asset(root, entry["source"])
    raw = source.read_bytes()
    if digest(raw) != entry["source_sha256"]:
        raise ValueError(f"Source hash differs from registry: {entry['program_id']}")
    registered = entry.get("cases")
    binding = "registered_hashes"
    if registered is None:
        if not diagnostic:
            raise ValueError(f"Frozen input/oracle hashes are missing: {entry['program_id']}")
        binding = "discovered_diagnostic"
        registered = [{"case_id": path.stem,
                       "stdin": path.relative_to(root).as_posix(),
                       "expected_stdout": path.with_suffix(".out").relative_to(root).as_posix()}
                      for path in sorted((source.parent / "cases").glob("*.in"))]
    if not isinstance(registered, list) or not registered:
        raise ValueError(f"No input cases for {entry['program_id']}")
    cases = []
    seen = set()
    expected_inputs = set()
    for item in registered:
        if not isinstance(item, dict) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", str(item.get("case_id", ""))):
            raise ValueError("Invalid evaluation case ID")
        case_id = item["case_id"]
        if case_id in seen:
            raise ValueError("Duplicate evaluation case ID")
        seen.add(case_id)
        input_path = asset(root, item.get("stdin"))
        output_path = asset(root, item.get("expected_stdout"))
        if input_path.parent != source.parent / "cases" or output_path != input_path.with_suffix(".out"):
            raise ValueError("Case files must be paired in the program's cases directory")
        expected_inputs.add(input_path)
        stdin, expected = input_path.read_bytes(), output_path.read_bytes()
        if binding == "registered_hashes" and (
            digest(stdin) != item.get("stdin_sha256") or digest(expected) != item.get("expected_stdout_sha256")
        ):
            raise ValueError(f"Frozen input/oracle hash mismatch: {entry['program_id']}/{case_id}")
        cases.append(CaseAsset(case_id, stdin, expected))
    actual_inputs = {path.resolve(strict=True) for path in (source.parent / "cases").glob("*.in")}
    if actual_inputs != expected_inputs:
        raise ValueError("Input registry omits or adds cases relative to the source program")
    return ProgramAssets(entry["program_id"], raw, tuple(cases), binding)
