"""Evidence-backed R001/R002 attribution sidecars for real experiments."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from backend.app.execution.engine import atomic_json
from backend.app.reporting import load_result
from backend.app.static_evidence import (
    EvidenceError, check_section_table, check_symbol_table, count_encodings, read_elf,
)


class AttributionError(ValueError):
    """An attribution input or evidence boundary is invalid."""


ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "config" / "attribution-policy.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _policy_hash() -> str:
    return _sha256(POLICY_PATH)


def _all_runs_passed(variant: Mapping[str, Any], inputs: list) -> bool:
    runs = variant.get("runs")
    expected = [item["case_id"] for item in inputs]
    return bool(expected) and len(set(expected)) == len(expected) and isinstance(runs, list) and (
        sorted(run.get("case_id", "") for run in runs) == sorted(expected)
    ) and all(
        run.get("status") == "passed" and run.get("exit_code") == 0
        and run.get("stderr") == "" and hashlib.sha256(run.get("stdout", "").encode("utf-8")).hexdigest()
        == next(item["expected_stdout_sha256"] for item in inputs if item["case_id"] == run["case_id"])
        for run in runs
    )


def _variant_map(result: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    variants = result.get("variants")
    if not isinstance(variants, list):
        raise AttributionError("Experiment variants must be a list")
    mapped = {str(item["optimization"]): item for item in variants if isinstance(item, Mapping)}
    if len(mapped) != len(variants):
        raise AttributionError("Duplicate or malformed experiment variants")
    return mapped


def _execution_binding(experiment: Mapping[str, Any], workspace: Path) -> str | None:
    """Bind real results to execution-time hashes rather than new file hashes."""
    if experiment.get("is_mock"):
        return None
    try:
        record_path = workspace / "execution.json"
        if not record_path.resolve().is_relative_to(workspace.resolve()):
            raise EvidenceError("Execution record escapes experiment workspace")
        record = json.loads(record_path.read_bytes())
        if not isinstance(record, Mapping):
            raise EvidenceError("Execution record must be an object")
        for field in ("experiment_id", "is_mock", "benchmark_id", "source_sha256",
                      "baseline_config_sha256", "environment"):
            if record.get(field) != experiment.get(field):
                raise EvidenceError(f"Execution/result mismatch: {field}")
        for path, expected in ((workspace / "source/main.c", experiment["source_sha256"]),
                               (workspace / "baseline.json", experiment["baseline_config_sha256"])):
            if not path.resolve().is_relative_to(workspace.resolve()) or _sha256(path) != expected:
                raise EvidenceError("Execution source or configuration snapshot hash mismatch")
        if [{key: row[key] for key in ("case_id", "stdin_sha256", "expected_stdout_sha256")}
            for row in record["inputs"]] != experiment["inputs"]:
            raise EvidenceError("Execution/result input hash mismatch")
        recorded = {item["optimization"]: item for item in record["variants"]}
        for variant in experiment["variants"]:
            if variant["status"] not in {"passed", "analysis_error"}:
                continue
            profile = variant["optimization"]
            original = recorded[profile]
            if original["status"] != "execution_passed":
                raise EvidenceError(f"Execution did not pass: {profile}")
            elf = workspace / profile / "program.elf"
            if not elf.resolve().is_relative_to(workspace.resolve()) or _sha256(elf) != original["elf_sha256"]:
                raise EvidenceError(f"ELF changed after execution: {profile}")
            actual_runs = {run["case_id"]: run for run in original["runs"]}
            if len(actual_runs) != len(original["runs"]) or len(actual_runs) != len(variant["runs"]):
                raise EvidenceError(f"Execution/result case count mismatch: {profile}")
            for run in variant["runs"]:
                actual = actual_runs[run["case_id"]]
                if actual["status"] != run["status"] or any(
                    actual["process"][key] != run[key] for key in ("stdout", "stderr", "exit_code")
                ):
                    raise EvidenceError(f"Execution/result case mismatch: {profile}/{run['case_id']}")
        return None
    except (OSError, ValueError, KeyError, TypeError) as error:
        return f"Execution provenance unavailable or inconsistent: {error}"


def _artifact_evidence(
    profile: str,
    variant: Mapping[str, Any],
    workspace: Path,
) -> tuple[list[dict[str, Any]], bool]:
    # result.json keeps the public schema stable; the analyzer's archive uses
    # these fixed paths in each execution profile directory.
    analysis_dir = workspace / profile / "analysis"
    candidates = {
        "raw_encoding": workspace / profile / "program.elf",
        "disassembly": analysis_dir / "objdump-kernel.txt",
        "symbol_table": analysis_dir / "readelf-symbols.txt",
        "section_table": analysis_dir / "readelf-sections.txt",
    }
    rows: list[dict[str, Any]] = []
    complete = bool(candidates)
    for kind, path in candidates.items():
        if not path.resolve().is_relative_to(workspace.resolve()):
            raise EvidenceError("Evidence path escapes the experiment workspace")
        if not path.is_file():
            complete = False
            continue
        relative = str(path.relative_to(workspace)).replace("\\", "/")
        rows.append({
            "id": f"{profile}-{kind}",
            "profile": profile,
            "kind": kind,
            "artifact_path": relative,
            "artifact_sha256": _sha256(path),
            "locator": "whole-file",
        })
    return rows, complete


def _snapshot(profile: str, variant: Mapping[str, Any], workspace: Path, inputs: list,
              *, require_record: bool = False) -> tuple[dict[str, Any] | None, list[dict[str, Any]], str | None]:
    if variant.get("status") not in {"passed", "analysis_error"} or not _all_runs_passed(variant, inputs):
        return None, [], f"{profile} did not pass all registered cases"
    try:
        evidence, evidence_complete = _artifact_evidence(profile, variant, workspace)
        view = read_elf(workspace / profile / "program.elf")
        by_kind = {row["kind"]: workspace / row["artifact_path"] for row in evidence}
        if require_record:
            archive = workspace / profile / "analysis/record.json"
            if not archive.resolve().is_relative_to(workspace.resolve()):
                raise EvidenceError("Analysis record escapes experiment workspace")
            record = json.loads(archive.read_bytes())
            if not isinstance(record, Mapping) or not isinstance(record.get("artifact_sha256"), Mapping):
                raise EvidenceError("Malformed analysis capture record")
            if record.get("elf_sha256") != hashlib.sha256(view.raw).hexdigest():
                raise EvidenceError("ELF differs from analysis-time hash")
            for kind, key in (("disassembly", "disassembly"), ("symbol_table", "symbols"), ("section_table", "sections")):
                if kind in by_kind and _sha256(by_kind[kind]) != record.get("artifact_sha256", {}).get(key):
                    raise EvidenceError("Archived analysis output changed after analysis")
        if "symbol_table" in by_kind:
            check_symbol_table(by_kind["symbol_table"].read_text(encoding="utf-8"), view)
        if "section_table" in by_kind:
            check_section_table(by_kind["section_table"].read_text(encoding="utf-8"), view)
        disassembly = by_kind["disassembly"].read_text(encoding="utf-8") if "disassembly" in by_kind else ""
        instructions_16, instructions_32, unknown = count_encodings(disassembly, view)
        metrics = variant.get("metrics")
        measured = {
            "elf_file_bytes": len(view.raw), "text_section_bytes": view.text_bytes,
            "kernel_code_bytes": view.length,
        }
        if "disassembly" in by_kind:
            measured.update(kernel_static_instruction_count=instructions_16 + instructions_32,
                            kernel_compressed_instruction_count=instructions_16)
        if isinstance(metrics, Mapping) and any(metrics.get(key) != value for key, value in measured.items()):
            raise EvidenceError("Reported static metrics conflict with ELF or archived encodings")
        if unknown and variant.get("status") == "passed" and "disassembly" in by_kind:
            raise EvidenceError("Passed static analysis contains unknown bytes")
        for row in evidence:
            row["locator"] = (
                f"kernel file bytes [{view.file_offset:#x}, {view.file_offset + view.length:#x}); "
                f"virtual [{view.start:#x}, {view.start + view.length:#x}); section {view.section_index} {view.section_name}"
            )
    except (ValueError, OSError, UnicodeError) as error:
        return None, [], f"{profile}: {error}"
    snapshot = {
        "profile": profile,
        "correctness_passed": True,
        "elf_sha256": hashlib.sha256(view.raw).hexdigest(),
        "text_section_bytes": view.text_bytes,
        "kernel_code_bytes": view.length,
        "instructions_16": instructions_16,
        "instructions_32": instructions_32,
        "unclassified_bytes": unknown,
        "known_padding_bytes": 0,
        "inside_text": view.inside_text,
    }
    if not evidence_complete:
        return snapshot, evidence, f"{profile} lacks one or more raw analysis artifacts"
    return snapshot, evidence, None


def _rule(rule_id: str, status: str, summary: str, evidence_ids: Iterable[str]) -> dict[str, Any]:
    return {
        "rule_id": rule_id,
        "status": status,
        "causal_claim": False,
        "summary": summary,
        "evidence_ids": list(evidence_ids),
    }


def _unavailable(experiment: Mapping[str, Any], raw: bytes, candidate: str, reason: str) -> dict[str, Any]:
    return {
        "analysis_version": "0.1.0",
        "policy_sha256": _policy_hash(),
        "experiment_id": experiment["experiment_id"],
        "experiment_json_sha256": hashlib.sha256(raw).hexdigest(),
        "is_mock": bool(experiment["is_mock"]),
        "status": "unavailable",
        "reference_profile": "O2",
        "candidate_profile": candidate,
        "reason": reason,
        "snapshots": None,
        "deltas": None,
        "rules": [
            _rule("R001", "abstained", reason, []),
            _rule("R002", "abstained", reason, []),
        ],
        "evidence": [],
    }


def build_attribution(
    experiment: Mapping[str, Any],
    raw: bytes,
    workspace: Path,
    candidate: str,
) -> dict[str, Any]:
    if candidate not in {"O0", "Os"}:
        raise AttributionError(f"Unsupported candidate profile: {candidate}")
    variants = _variant_map(experiment)
    binding_error = _execution_binding(experiment, workspace)
    if binding_error:
        return _unavailable(experiment, raw, candidate, binding_error)
    reference = variants.get("O2")
    candidate_variant = variants.get(candidate)
    if reference is None:
        return _unavailable(experiment, raw, candidate, "O2 reference profile was not requested")
    if candidate_variant is None:
        return _unavailable(experiment, raw, candidate, "Candidate profile was not requested")
    inputs = experiment.get("inputs", [])
    require_record = not experiment.get("is_mock")
    ref_snapshot, ref_evidence, ref_reason = _snapshot("O2", reference, workspace, inputs, require_record=require_record)
    cand_snapshot, cand_evidence, cand_reason = _snapshot(candidate, candidate_variant, workspace, inputs, require_record=require_record)
    if ref_snapshot is None or cand_snapshot is None:
        return _unavailable(experiment, raw, candidate, ref_reason or cand_reason or "Comparison precondition failed")
    all_evidence = ref_evidence + cand_evidence
    evidence_ids = {item["id"] for item in all_evidence}
    ref_r1 = {f"O2-raw_encoding", f"O2-disassembly", f"O2-symbol_table"} <= evidence_ids
    cand_r1 = {f"{candidate}-raw_encoding", f"{candidate}-disassembly", f"{candidate}-symbol_table"} <= evidence_ids
    r1_verified = ref_snapshot["unclassified_bytes"] == 0 and cand_snapshot["unclassified_bytes"] == 0 and ref_r1 and cand_r1
    ref_r2 = {"O2-symbol_table", "O2-section_table"} <= evidence_ids
    cand_r2 = {f"{candidate}-symbol_table", f"{candidate}-section_table"} <= evidence_ids
    r2_verified = ref_snapshot["inside_text"] and cand_snapshot["inside_text"] and ref_r2 and cand_r2
    ref_n = ref_snapshot["instructions_16"] + ref_snapshot["instructions_32"]
    cand_n = cand_snapshot["instructions_16"] + cand_snapshot["instructions_32"]
    kernel_delta = cand_snapshot["kernel_code_bytes"] - ref_snapshot["kernel_code_bytes"]
    text_delta = cand_snapshot["text_section_bytes"] - ref_snapshot["text_section_bytes"]
    deltas = {
        "kernel_delta_bytes": kernel_delta,
        "instruction_count_term_bytes": 4 * (cand_n - ref_n),
        "encoding_width_term_bytes": -2 * (cand_snapshot["instructions_16"] - ref_snapshot["instructions_16"]),
        "unclassified_term_bytes": cand_snapshot["unclassified_bytes"] - ref_snapshot["unclassified_bytes"],
        "text_delta_bytes": text_delta,
        "outside_kernel_delta_bytes": text_delta - kernel_delta if r2_verified else None,
    }
    if sum(deltas[key] for key in ("instruction_count_term_bytes", "encoding_width_term_bytes", "unclassified_term_bytes")) != kernel_delta:
        raise AttributionError("R001 byte decomposition does not reconcile")
    if r1_verified and r2_verified:
        status = "complete"
        reason = "R001 and R002 verified from raw ELF and binutils evidence"
    else:
        status = "partial"
        reason = "R001 or R002 lacks complete evidence or contains unclassified bytes"
    return {
        "analysis_version": "0.1.0",
        "policy_sha256": _policy_hash(),
        "experiment_id": experiment["experiment_id"],
        "experiment_json_sha256": hashlib.sha256(raw).hexdigest(),
        "is_mock": bool(experiment["is_mock"]),
        "status": status,
        "reference_profile": "O2",
        "candidate_profile": candidate,
        "reason": reason,
        "snapshots": {"reference": ref_snapshot, "candidate": cand_snapshot},
        "deltas": deltas,
        "rules": [
            _rule("R001", "verified" if r1_verified else "abstained", "Exact RV64GC byte decomposition" if r1_verified else "Unknown bytes or raw encoding evidence prevent a complete decomposition", [item["id"] for item in all_evidence if item["kind"] in {"raw_encoding", "disassembly", "symbol_table"}]),
            _rule("R002", "verified" if r2_verified else ("abstained" if ref_snapshot["inside_text"] and cand_snapshot["inside_text"] else "not_applicable"), "Kernel and outside-.text accounting reconciles" if r2_verified else "Kernel section membership evidence is incomplete", [item["id"] for item in all_evidence if item["kind"] in {"symbol_table", "section_table"}]),
        ],
        "evidence": all_evidence,
    }


def generate_attributions(result_path: Path, result: Mapping[str, Any] | None = None) -> tuple[list[Path], bool]:
    source = Path(result_path).resolve(strict=True)
    raw = source.read_bytes()
    experiment = load_result(source)
    if result is not None and result != experiment:
        raise AttributionError("Supplied result differs from the saved experiment JSON")
    variants = _variant_map(experiment)
    candidates = [profile for profile in ("O0", "Os") if profile in variants]
    output_paths: list[Path] = []
    complete = bool(candidates)
    for candidate in candidates:
        document = build_attribution(experiment, raw, source.parent, candidate)
        destination = source.parent / "attribution" / f"O2-{candidate}" / "attribution.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        atomic_json(destination, document)
        output_paths.append(destination)
        complete = complete and document["status"] == "complete"
    return output_paths, complete
