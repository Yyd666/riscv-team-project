"""Generate synthetic contract fixtures only; no compiler or ELF parser runs."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "contracts/examples"


def read(name: str) -> dict:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


def write(name: str, data: dict) -> None:
    (EXAMPLES / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def synthetic_hash(label: str) -> str:
    return hashlib.sha256(("MOCK: " + label).encode("utf-8")).hexdigest()


def renamed(source: dict, experiment_id: str) -> dict:
    return json.loads(json.dumps(source).replace(source["experiment_id"], experiment_id))


def snapshot(source: dict, profile: str) -> dict:
    variant = next(item for item in source["variants"] if item["optimization"] == profile)
    metrics = variant["metrics"]
    return {
        "profile": profile,
        "correctness_passed": True,
        "elf_sha256": synthetic_hash(source["experiment_id"] + profile + " ELF"),
        "text_section_bytes": metrics["text_section_bytes"],
        "kernel_code_bytes": metrics["kernel_code_bytes"],
        "instructions_16": metrics["kernel_compressed_instruction_count"],
        "instructions_32": metrics["kernel_static_instruction_count"] - metrics["kernel_compressed_instruction_count"],
        "unclassified_bytes": 0,
        "known_padding_bytes": 0,
        "inside_text": True,
    }


def attribution(source_name: str, mode: str) -> dict:
    source = read(source_name)
    unavailable = mode == "unavailable"
    data = {
        "analysis_version": "0.1.0",
        "policy_sha256": sha(ROOT / "config/attribution-policy.json"),
        "experiment_id": source["experiment_id"],
        "experiment_json_sha256": sha(EXAMPLES / source_name),
        "is_mock": True,
        "status": "unavailable" if unavailable else "complete",
        "reference_profile": "O2",
        "candidate_profile": "Os",
        "reason": "MOCK: synthetic contract example; no ELF was read and no command was executed.",
        "snapshots": None,
        "deltas": None,
        "rules": [],
        "evidence": [],
    }
    if unavailable:
        data["reason"] += " Reference compilation failed in the synthetic experiment."
        data["rules"] = [{"rule_id": rule_id, "status": "abstained", "causal_claim": False, "summary": "MOCK: reference result unavailable.", "evidence_ids": []} for rule_id in ["R001", "R002"]]
        return data

    reference = snapshot(source, "O2")
    if mode == "partial":
        # Candidate experiment intentionally has analysis_error / null metrics.
        candidate = copy.deepcopy(reference)
        candidate.update({"profile": "Os", "elf_sha256": synthetic_hash(source["experiment_id"] + "Os ELF"), "kernel_code_bytes": 40, "unclassified_bytes": 4, "text_section_bytes": 2816})
        data["status"] = "partial"
    else:
        candidate = snapshot(source, "Os")
    if mode == "outside":
        candidate["inside_text"] = False
        data["status"] = "partial"

    data["snapshots"] = {"reference": reference, "candidate": candidate}
    ref_n = reference["instructions_16"] + reference["instructions_32"]
    cand_n = candidate["instructions_16"] + candidate["instructions_32"]
    kernel_delta = candidate["kernel_code_bytes"] - reference["kernel_code_bytes"]
    text_delta = candidate["text_section_bytes"] - reference["text_section_bytes"]
    data["deltas"] = {
        "kernel_delta_bytes": kernel_delta,
        "instruction_count_term_bytes": 4 * (cand_n - ref_n),
        "encoding_width_term_bytes": -2 * (candidate["instructions_16"] - reference["instructions_16"]),
        "unclassified_term_bytes": candidate["unclassified_bytes"] - reference["unclassified_bytes"],
        "text_delta_bytes": text_delta,
        "outside_kernel_delta_bytes": None if mode == "outside" else text_delta - kernel_delta,
    }
    names = {"raw_encoding": "program.elf", "disassembly": "kernel.asm", "symbol_table": "symbols.txt", "section_table": "sections.txt"}
    for item in [reference, candidate]:
        for kind, filename in names.items():
            profile = item["profile"]
            data["evidence"].append({
                "id": profile + "_" + kind,
                "profile": profile,
                "kind": kind,
                "artifact_path": profile + "/" + filename,
                "artifact_sha256": item["elf_sha256"] if kind == "raw_encoding" else synthetic_hash(source["experiment_id"] + profile + kind),
                "locator": "MOCK kernel or .text location; no real artifact exists.",
            })
    for rule_id, kinds, status in [
        ("R001", ["raw_encoding", "symbol_table", "disassembly"], "abstained" if mode == "partial" else "verified"),
        ("R002", ["symbol_table", "section_table"], "not_applicable" if mode == "outside" else "verified"),
    ]:
        data["rules"].append({
            "rule_id": rule_id,
            "status": status,
            "causal_claim": False,
            "summary": "MOCK: byte accounting only; partial and inapplicable rules do not establish complete attribution.",
            "evidence_ids": [item["id"] for item in data["evidence"] if item["kind"] in kinds],
        })
    return data


def main() -> None:
    original = read("experiment.mock.json")
    if original["is_mock"] is not True:
        raise ValueError("Generator accepts only explicitly synthetic source experiments")
    scope = renamed(original, "mock-scope-mismatch-001")
    scope["variants"][2]["metrics"].update({"kernel_code_bytes": 40, "kernel_static_instruction_count": 14, "kernel_compressed_instruction_count": 8})
    scope["variants"][2]["diagnostics"] = "MOCK: complete .text shrinks while kernel grows; not a measured result."
    write("experiment.scope-mismatch.mock.json", scope)

    partial = renamed(original, "mock-analysis-partial-001")
    partial["variants"][2].update({"status": "analysis_error", "metrics": None, "kernel_disassembly": None, "diagnostics": "MOCK: unknown bytes prevent complete baseline analysis."})
    partial["selection"]["optimization"] = "O2"
    write("experiment.analysis-partial.mock.json", partial)

    for name, source, mode in [
        ("attribution.complete.mock.json", "experiment.mock.json", "complete"),
        ("attribution.scope-mismatch.mock.json", "experiment.scope-mismatch.mock.json", "complete"),
        ("attribution.partial.mock.json", "experiment.analysis-partial.mock.json", "partial"),
        ("attribution.outside.mock.json", "experiment.mock.json", "outside"),
        ("attribution.unavailable.mock.json", "experiment.failed.mock.json", "unavailable"),
    ]:
        write(name, attribution(source, mode))
    print("Generated 2 experiment and 5 attribution fixtures; all are synthetic.")


if __name__ == "__main__":
    main()
