"""Validate two independent M2 annotations and their adjudication.

This gate checks completeness, reviewer independence, artifact hashes and
objective GNU ELF facts. It never creates annotations or decides a reviewer
label on their behalf.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from jsonschema import Draft202012Validator, FormatChecker, ValidationError

from scripts.elf_reference import inspect_elf, instruction_rows

PROFILES = ("O0", "O2", "Os")
EVIDENCE_FILES = ("program.elf", "analysis/readelf-symbols.txt",
                  "analysis/readelf-sections.txt", "analysis/objdump-kernel.txt")


class ReviewError(ValueError):
    pass


def _load(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ReviewError(f"Unable to read review file: {path}") from error
    if not isinstance(value, dict):
        raise ReviewError(f"Review file must be an object: {path}")
    return value


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ReviewError(message)


def _corpus_ids(corpus_path: Path) -> list[str]:
    corpus = _load(corpus_path)
    entries = corpus.get("entries")
    _require(corpus.get("status") == "frozen", "Review requires a machine-frozen corpus")
    _require(isinstance(entries, list) and len(entries) == 12, "Review requires exactly 12 frozen programs")
    _require(all(isinstance(entry, dict) for entry in entries), "Invalid corpus entry")
    ids = [entry.get("program_id") for entry in entries]
    _require(all(isinstance(item, str) and item for item in ids) and len(set(ids)) == 12,
             "Corpus program IDs must be unique")
    return sorted(ids)


def _validate_shape(document: dict, ids: list[str], label: str) -> None:
    try:
        Draft202012Validator(_load(ROOT / "contracts/reviewer-annotation.schema.json"),
                             format_checker=FormatChecker()).validate(document)
    except ValidationError as error:
        raise ReviewError(f"{label}: invalid annotation at {list(error.absolute_path)}: {error.message}") from error
    _require(document.get("schema_version") == "0.1.0", f"{label}: unsupported schema version")
    reviewer = document.get("reviewer_id")
    _require(isinstance(reviewer, str) and reviewer.strip(), f"{label}: reviewer_id is required")
    _require(re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(document.get("review_date", ""))) is not None,
             f"{label}: review_date must be YYYY-MM-DD")
    independent = document.get("independent_from")
    _require(isinstance(independent, list) and independent and reviewer not in independent,
             f"{label}: independence declaration is invalid")
    _require(all(item.strip() for item in independent), f"{label}: empty independence declaration")
    programs = document.get("programs")
    _require(isinstance(programs, list), f"{label}: programs must be a list")
    observed = [item.get("program_id") for item in programs if isinstance(item, dict)]
    _require(sorted(observed) == ids and len(observed) == len(set(observed)),
             f"{label}: program set does not exactly match corpus")
    for item in programs:
        profiles = item.get("profiles")
        _require(isinstance(profiles, dict) and set(profiles) == {"O0", "O2", "Os"},
                 f"{label}/{item.get('program_id')}: O0/O2/Os annotations are required")
        for profile, annotation in profiles.items():
            _require(isinstance(annotation, dict), f"{label}/{item['program_id']}/{profile}: invalid annotation")
            _require(annotation.get("kernel_end", 0) > annotation.get("kernel_start", -1),
                     f"{label}/{item['program_id']}/{profile}: invalid kernel range")
            _require(annotation.get("r001") in {"verified", "abstained", "not_applicable"}
                     and annotation.get("r002") in {"verified", "abstained", "not_applicable"},
                     f"{label}/{item['program_id']}/{profile}: rule labels are required")
            _require(isinstance(annotation.get("evidence"), list) and annotation["evidence"],
                     f"{label}/{item['program_id']}/{profile}: evidence locations are required")


def _validate_adjudication(document: dict, ids: list[str], reviewer_ids: set[str]) -> None:
    _require(document.get("schema_version") == "0.1.0", "Adjudication schema version is unsupported")
    names = document.get("reviewer_ids")
    _require(isinstance(names, list) and len(names) == 2
             and all(isinstance(name, str) for name in names) and set(names) == reviewer_ids,
             "Adjudication must name exactly the two independent reviewers")
    decisions = document.get("decisions")
    _require(isinstance(decisions, list), "Adjudication decisions are required")
    expected = {(program, profile) for program in ids for profile in ("O0", "O2", "Os")}
    _require(all(isinstance(item, dict) and isinstance(item.get("program_id"), str)
                 and isinstance(item.get("profile"), str) for item in decisions),
             "Invalid adjudication decision")
    observed = {(item["program_id"], item["profile"]) for item in decisions}
    _require(observed == expected and len(decisions) == len(expected),
             "Adjudication must cover every program/profile pair exactly once")
    for item in decisions:
        _require(item.get("final_r001") in ("verified", "abstained", "not_applicable")
                 and item.get("final_r002") in ("verified", "abstained", "not_applicable"),
                 "Adjudication has an invalid final rule label")
        _require(isinstance(item.get("reason"), str) and item["reason"].strip(),
                 "Every adjudication decision needs a reason")
    signoffs = document.get("signoffs")
    _require(isinstance(signoffs, list) and len(signoffs) == 2
             and all(isinstance(name, str) for name in signoffs) and set(signoffs) == reviewer_ids,
             "Both reviewers must sign the adjudication")


def _inside(root: Path, relative: str) -> Path:
    _require(isinstance(relative, str) and bool(relative), "Invalid batch artifact path")
    posix = PurePosixPath(relative)
    _require(not posix.is_absolute() and ".." not in posix.parts and "\\" not in relative,
             "Batch artifact path must stay inside batch directory")
    path = (root / relative).resolve(strict=True)
    _require(path.is_relative_to(root) and path.is_file(), "Artifact escapes batch directory")
    return path


def _validate_batch(corpus_path: Path, batch_path: Path, ids: list[str]) -> tuple[dict, dict]:
    batch = _load(batch_path)
    _require(batch.get("completed") is True and batch.get("all_passed") is True
             and batch.get("is_mock") is False and batch.get("mode") == "formal"
             and batch.get("corpus_status") == "frozen" and batch.get("exit_code") == 0,
             "Review requires a real completed successful formal batch")
    root = batch_path.parent.resolve(strict=True)
    snapshot = _inside(root, "corpus.json")
    _require(batch.get("corpus_sha256") == _sha(snapshot) and _load(snapshot) == _load(corpus_path),
             "Review corpus does not match frozen batch snapshot")
    manifest = batch.get("artifact_sha256")
    _require(isinstance(manifest, dict) and manifest.get("corpus.json") == _sha(snapshot),
             "Frozen batch artifact manifest is required")
    for relative, digest in manifest.items():
        _require(isinstance(digest, str) and re.fullmatch(r"[a-f0-9]{64}", digest) is not None,
                 "Invalid batch artifact hash")
        _require(_sha(_inside(root, relative)) == digest, f"Batch artifact hash mismatch: {relative}")
    entries = batch.get("programs")
    _require(isinstance(entries, list) and len(entries) == len(ids)
             and all(isinstance(entry, dict) and isinstance(entry.get("program_id"), str) for entry in entries),
             "Invalid or duplicate batch program rows")
    _require(sorted(entry["program_id"] for entry in entries) == ids,
             "Batch does not contain every reviewed program exactly once")
    rows = {entry["program_id"]: entry for entry in entries}
    workspaces = set()
    for program, entry in rows.items():
        _require(entry.get("status") == "passed" and entry.get("exit_code") == 0
                 and entry.get("variant_statuses") == {profile: "passed" for profile in PROFILES},
                 f"{program}: every profile must have passed")
        _require(isinstance(entry.get("result_path"), str), f"{program}: invalid result_path")
        result = Path(entry["result_path"]).resolve(strict=True)
        _require(result.is_file() and result.is_relative_to(root) and result.name == "result.json",
                 f"{program}: result_path must stay inside batch directory")
        _require(result.parent not in workspaces, "Programs must not reuse one experiment directory")
        workspaces.add(result.parent)
        _require(str(result.relative_to(root)) in manifest, f"{program}: result missing from frozen manifest")
        document = _load(result)
        _require(document.get("benchmark_id") == program and document.get("is_mock") is False,
                 f"{program}: result benchmark identity mismatch or mock result")
        variants = document.get("variants")
        _require(isinstance(variants, list) and len(variants) == 3
                 and all(isinstance(variant, dict) and variant.get("status") == "passed"
                         and variant.get("optimization") in PROFILES for variant in variants)
                 and sorted(variant.get("optimization", "") for variant in variants) == sorted(PROFILES),
                 f"{program}: result must contain three successful profiles")
        for profile in PROFILES:
            for filename in (*EVIDENCE_FILES, "analysis/record.json"):
                relative = str((result.parent / profile / filename).relative_to(root))
                _require(relative in manifest, f"{program}/{profile}: artifact missing from frozen manifest: {filename}")
    return batch, rows


def _check_evidence(references: list[str], root: Path, workspace: Path,
                    profile: str, batch_id: str) -> None:
    resolved = set()
    profile_root = (workspace / profile).resolve(strict=True)
    for reference in references:
        # Accept either a fragment or a ': description' after a file location.
        location = reference.split("#", 1)[0].split(": ", 1)[0]
        _require(bool(location.strip()), "Evidence file location is empty")
        path = PurePosixPath(location)
        _require(".." not in path.parts and "\\" not in location, "Evidence path traversal")
        if path.is_absolute():
            # Preserve old locations in annotations after evidence is transferred.
            marker = "/" + batch_id + "/"
            candidates = [root / location.split(marker, 1)[1]] if marker in location else [Path(location)]
        else:
            candidates = [root / location, workspace / location, profile_root / location]
        matches = {item.resolve() for item in candidates if item.is_file()
                   and item.resolve().is_relative_to(profile_root)}
        _require(len(matches) == 1, f"Evidence file missing, ambiguous or outside reviewed profile: {reference}")
        resolved.update(matches)
    expected = {(profile_root / filename).resolve(strict=True) for filename in EVIDENCE_FILES}
    _require(expected <= resolved, "Evidence must cite ELF, symbol table, section table and kernel disassembly")


def _inspect_profile(elf: Path) -> dict:
    try:
        metrics, disassembly = inspect_elf(elf, include_boundaries=True)
        analysis = elf.parent / "analysis"
        symbols = (analysis / "readelf-symbols.txt").read_text(encoding="utf-8")
        boundaries = set((int(address, 16), int(size), int(index))
                         for address, size, index in re.findall(
                             r"^\s*\d+:\s+([0-9a-fA-F]+)\s+(\d+)\s+FUNC\s+\S+\s+\S+\s+(\d+)\s+kernel\s*$",
                             symbols, re.MULTILINE))
        _require(boundaries == {(metrics["kernel_start"], metrics["kernel_code_bytes"], metrics["section_index"])},
                 "Archived GNU symbol boundaries differ from fresh ELF reference")
        sections = (analysis / "readelf-sections.txt").read_text(encoding="utf-8")
        rows = [(int(index), name, int(address, 16), int(size, 16))
                for index, name, address, size in re.findall(
                    r"^\s*\[\s*(\d+)\]\s+(\S+)\s+\S+\s+([0-9a-fA-F]+)\s+[0-9a-fA-F]+\s+([0-9a-fA-F]+)\s+",
                    sections, re.MULTILINE)]
        own = [row for row in rows if row[0] == metrics["section_index"]]
        _require(len(own) == 1 and own[0][1] == ".text" and own[0][3] == metrics["text_section_bytes"]
                 and own[0][2] <= metrics["kernel_start"] < metrics["kernel_end"] <= own[0][2] + own[0][3],
                 "Archived GNU section does not match fresh ELF reference")
        archived = (analysis / "objdump-kernel.txt").read_text(encoding="utf-8")
        _require(instruction_rows(archived) == instruction_rows(disassembly),
                 "Archived GNU instructions differ from fresh ELF reference")
        record = _load(analysis / "record.json")
        _require(record.get("status") == "passed" and record.get("elf_sha256") == _sha(elf),
                 "Analysis record is not bound to reviewed ELF")
        hashes = record.get("artifact_sha256")
        _require(isinstance(hashes, dict), "Missing analysis-time artifact hashes")
        for key, filename in (("symbols", "readelf-symbols.txt"), ("sections", "readelf-sections.txt"),
                              ("disassembly", "objdump-kernel.txt")):
            _require(hashes.get(key) == _sha(analysis / filename), f"Analysis-time {key} hash mismatch")
        return metrics
    except ValueError as error:
        raise ReviewError(f"{elf}: {error}") from error


def validate_reviews(corpus_path: Path, batch_path: Path, review_a: Path, review_b: Path,
                     adjudication: Path) -> dict:
    ids = _corpus_ids(corpus_path)
    first, second = _load(review_a), _load(review_b)
    _validate_shape(first, ids, "reviewer_a")
    _validate_shape(second, ids, "reviewer_b")
    _require(first["reviewer_id"].strip().casefold() != second["reviewer_id"].strip().casefold(),
             "Reviewers must declare distinct identities")
    for reviewer, other in ((first, second), (second, first)):
        _require(other["reviewer_id"] in reviewer["independent_from"],
                 "Each reviewer must declare independence from the other reviewer")
    _require(first.get("batch_id") == second.get("batch_id"), "Reviews must target the same batch")
    batch, rows = _validate_batch(corpus_path, batch_path, ids)
    _require(batch.get("batch_id") == first.get("batch_id"), "Review batch_id does not match batch.json")
    _require(batch.get("completed") and batch.get("all_passed"), "Review requires a completed successful batch")
    _validate_adjudication(_load(adjudication), ids, {first["reviewer_id"], second["reviewer_id"]})

    root = batch_path.parent.resolve(strict=True)
    measured = {}
    for reviewer in (first, second):
        for program in reviewer["programs"]:
            result = Path(rows[program["program_id"]]["result_path"])
            for profile, annotation in program["profiles"].items():
                elf = result.parent / profile / "program.elf"
                _require(_sha(elf) == annotation["elf_sha256"],
                         f"{reviewer['reviewer_id']}/{program['program_id']}/{profile}: ELF hash mismatch")
                _check_evidence(annotation["evidence"], root, result.parent, profile, batch["batch_id"])
                if elf not in measured:
                    measured[elf] = _inspect_profile(elf)
                metrics = measured[elf]
                for field in ("kernel_start", "kernel_end", "section_index", "unclassified_bytes"):
                    _require(annotation[field] == metrics[field],
                             f"{reviewer['reviewer_id']}/{program['program_id']}/{profile}: {field} mismatch")
                for field in ("text_section_bytes", "kernel_code_bytes"):
                    if field == "kernel_code_bytes":
                        expected = metrics[field]
                        observed = annotation["kernel_end"] - annotation["kernel_start"]
                    else:
                        expected = metrics[field]
                        observed = annotation[field]
                    _require(expected == observed, f"{reviewer['reviewer_id']}/{program['program_id']}/{profile}: {field} mismatch")
                _require(annotation["instructions_16"] == metrics["kernel_compressed_instruction_count"],
                         f"{reviewer['reviewer_id']}/{program['program_id']}/{profile}: compressed count mismatch")
                _require(annotation["instructions_16"] + annotation["instructions_32"] == metrics["kernel_static_instruction_count"],
                         f"{reviewer['reviewer_id']}/{program['program_id']}/{profile}: instruction count mismatch")
    return {"reviewers": [first["reviewer_id"], second["reviewer_id"]], "program_count": len(ids),
            "profile_count": len(ids) * 3, "adjudication_count": len(ids) * 3,
            "machine_evidence_checked": True, "declared_signoffs_checked": True,
            "human_identity_verified": False, "acceptance_ready": False}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--batch", type=Path, required=True)
    parser.add_argument("--review-a", type=Path, required=True)
    parser.add_argument("--review-b", type=Path, required=True)
    parser.add_argument("--adjudication", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = validate_reviews(args.corpus.resolve(), args.batch.resolve(), args.review_a.resolve(),
                                  args.review_b.resolve(), args.adjudication.resolve())
    except (OSError, ReviewError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 3
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
