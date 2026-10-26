"""Evidence-backed R001/R002 attribution sidecars for real experiments."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from backend.app.execution.engine import atomic_json
from backend.app.reporting import load_result


class AttributionError(ValueError):
    """An attribution input or evidence boundary is invalid."""


ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "config" / "attribution-policy.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _policy_hash() -> str:
    return _sha256(POLICY_PATH)


def _all_runs_passed(variant: Mapping[str, Any]) -> bool:
    runs = variant.get("runs")
    return isinstance(runs, list) and bool(runs) and all(
        isinstance(run, Mapping) and run.get("status") == "passed" for run in runs
    )


def _variant_map(result: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    variants = result.get("variants")
    if not isinstance(variants, list):
        raise AttributionError("Experiment variants must be a list")
    return {str(item["optimization"]): item for item in variants if isinstance(item, Mapping)}


def _artifact_evidence(
    profile: str,
    variant: Mapping[str, Any],
    workspace: Path,
) -> tuple[list[dict[str, Any]], bool]:
    evidence = variant.get("analysis_artifacts")
    # Real result.json intentionally keeps the public schema stable. The analyzer
    # records these paths in the execution workspace; attribution reconstructs
    # the same paths from the profile directory when older results lack metadata.
    analysis_dir = workspace / profile / "analysis"
    candidates = {
        "raw_encoding": workspace / profile / "program.elf",
        "disassembly": analysis_dir / "objdump-kernel.txt",
        "symbol_table": analysis_dir / "readelf-symbols.txt",
        "section_table": analysis_dir / "readelf-sections.txt",
    }
    if isinstance(evidence, Mapping):
        names = {
            "raw_encoding": None,
            "disassembly": evidence.get("disassembly"),
            "symbol_table": evidence.get("symbols"),
            "section_table": evidence.get("sections"),
        }
        for kind, relative in names.items():
            if isinstance(relative, str):
                path = (workspace / relative).resolve()
                if path.is_relative_to(workspace.resolve()):
                    candidates[kind] = path
    rows: list[dict[str, Any]] = []
    complete = bool(candidates)
    for kind, path in candidates.items():
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


def _snapshot(profile: str, variant: Mapping[str, Any], workspace: Path) -> tuple[dict[str, Any] | None, list[dict[str, Any]], str | None]:
    if variant.get("status") != "passed" or not _all_runs_passed(variant):
        return None, [], f"{profile} did not pass all registered cases"
    metrics = variant.get("metrics")
    if not isinstance(metrics, Mapping):
        return None, [], f"{profile} has no static metrics"
    required = ("text_section_bytes", "kernel_code_bytes", "kernel_static_instruction_count",
                "kernel_compressed_instruction_count")
    if any(not isinstance(metrics.get(key), int) for key in required):
        return None, [], f"{profile} has incomplete static metrics"
    static = int(metrics["kernel_static_instruction_count"])
    instructions_16 = int(metrics["kernel_compressed_instruction_count"])
    instructions_32 = static - instructions_16
    kernel_bytes = int(metrics["kernel_code_bytes"])
    expected = 2 * instructions_16 + 4 * instructions_32
    unknown = kernel_bytes - expected
    if instructions_16 < 0 or instructions_32 < 0 or unknown < 0:
        return None, [], f"{profile} metrics do not reconcile with RV64GC widths"
    elf = workspace / profile / "program.elf"
    if not elf.is_file():
        return None, [], f"{profile} ELF artifact is missing"
    evidence, evidence_complete = _artifact_evidence(profile, variant, workspace)
    snapshot = {
        "profile": profile,
        "correctness_passed": True,
        "elf_sha256": _sha256(elf),
        "text_section_bytes": int(metrics["text_section_bytes"]),
        "kernel_code_bytes": kernel_bytes,
        "instructions_16": instructions_16,
        "instructions_32": instructions_32,
        "unclassified_bytes": unknown,
        "known_padding_bytes": 0,
        "inside_text": kernel_bytes <= int(metrics["text_section_bytes"]),
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
    reference = variants.get("O2")
    candidate_variant = variants.get(candidate)
    if reference is None:
        return _unavailable(experiment, raw, candidate, "O2 reference profile was not requested")
    if candidate_variant is None:
        return _unavailable(experiment, raw, candidate, "Candidate profile was not requested")
    ref_snapshot, ref_evidence, ref_reason = _snapshot("O2", reference, workspace)
    cand_snapshot, cand_evidence, cand_reason = _snapshot(candidate, candidate_variant, workspace)
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
    experiment = result if result is not None else load_result(source)
    variants = _variant_map(experiment)
    candidates = [profile for profile in ("O0", "Os") if profile in variants]
    output_paths: list[Path] = []
    complete = True
    for candidate in candidates:
        document = build_attribution(experiment, raw, source.parent, candidate)
        destination = source.parent / "attribution" / f"O2-{candidate}" / "attribution.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        atomic_json(destination, document)
        output_paths.append(destination)
        complete = complete and document["status"] == "complete"
    return output_paths, complete
