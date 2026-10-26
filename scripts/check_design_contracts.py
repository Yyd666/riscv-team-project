"""Validate design fixtures and invariants, not real ELF attribution results."""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import PurePosixPath

from jsonschema import Draft202012Validator, ValidationError

from check_foundation import ROOT, digest, load_json, require


def validate_plan(plan: dict) -> None:
    require(plan["status"] == "planned", "Evaluation targets are not completed measurements")
    require(plan["sample_unit"] == "source_program", "stdin cases cannot count as independent programs")
    require(plan["split_unit"] == "program_family_and_provenance", "Evaluation split policy drift")
    dev, held = plan["development"], plan["held_out"]
    require(len(dev["families"]) == len(set(dev["families"])), "Duplicate development family")
    require(len(held["families"]) == len(set(held["families"])), "Duplicate held-out family")
    require(not set(dev["families"]) & set(held["families"]), "Program family leakage")
    require(all(type(group["minimum_programs_target"]) is int and group["minimum_programs_target"] >= len(group["families"]) for group in [dev, held]), "Invalid corpus construction target")
    require(set(plan["baselines"]) == {"raw_binutils", "fixed_O2", "fixed_Os", "exhaustive_three_profiles"}, "Required evaluation baseline missing")
    require(plan["acceptance"]["supported_case_byte_error"] == 0, "Byte accounting must be exact")
    require(plan["acceptance"]["exhaustive_recommendation_regret_bytes"] == 0, "Fixed-profile selection must match exhaustive result")
    require(plan["acceptance"]["report_coverage_and_abstention"] is True, "Coverage and abstention must be reported")
    require(plan["acceptance"]["mock_counts_as_measurement"] is False, "Mock cannot count as measurement")
    require(plan["acceptance"]["independent_reviewers"] >= 2, "Independent review missing")


def validate_analysis(document: dict, validator: Draft202012Validator, experiments: dict, policy: dict) -> None:
    validator.validate(document)
    require(document["policy_sha256"] == digest("config/attribution-policy.json"), "Attribution policy hash drift")
    require(document["analysis_version"] == policy["policy_version"], "Analysis policy version mismatch")
    source = experiments.get(document["experiment_json_sha256"])
    require(source is not None, "Referenced experiment JSON hash is unknown")
    require(source["experiment_id"] == document["experiment_id"], "Experiment ID mismatch")
    require(source["is_mock"] == document["is_mock"], "Mock provenance mismatch")
    rules = {item["rule_id"]: item for item in document["rules"]}
    require(len(rules) == len(document["rules"]) and set(rules) == set(policy["required_rules"]), "Missing or duplicate rule IDs")
    evidence = {item["id"]: item for item in document["evidence"]}
    require(len(evidence) == len(document["evidence"]), "Duplicate evidence ID")
    for item in evidence.values():
        path = PurePosixPath(item["artifact_path"])
        require(bool(path.name) and not path.is_absolute() and ".." not in path.parts and ":" not in item["artifact_path"] and "\\" not in item["artifact_path"], "Evidence path must be relative to experiment")
    for rule in rules.values():
        require(set(rule["evidence_ids"]) <= set(evidence), "Dangling evidence reference")
    if document["status"] == "unavailable":
        return

    snapshots = document["snapshots"]
    ref, cand = snapshots["reference"], snapshots["candidate"]
    require(ref["profile"] == document["reference_profile"] and cand["profile"] == document["candidate_profile"], "Comparison profile mismatch")
    source_variants = {item["optimization"]: item for item in source["variants"]}
    expected_cases = [item["case_id"] for item in source["inputs"]]
    for snapshot in [ref, cand]:
        variant = source_variants.get(snapshot["profile"])
        require(variant is not None, "Comparison profile absent from experiment")
        require([run["case_id"] for run in variant["runs"]] == expected_cases and all(run["status"] == "passed" for run in variant["runs"]), "Comparison requires all registered cases to pass")
        require(variant["status"] in ["passed", "analysis_error"], "Compilation/runtime failure cannot be attributed")
        expected_bytes = 2 * snapshot["instructions_16"] + 4 * snapshot["instructions_32"] + snapshot["unclassified_bytes"]
        require(snapshot["kernel_code_bytes"] == expected_bytes, "Function bytes do not reconcile")
        require(snapshot["known_padding_bytes"] <= snapshot["kernel_code_bytes"], "Padding is a subset, not an additional component")
        if snapshot["inside_text"]:
            require(snapshot["kernel_code_bytes"] <= snapshot["text_section_bytes"], "Kernel cannot exceed containing section")
        if variant["metrics"] is not None:
            metrics = variant["metrics"]
            require(snapshot["kernel_code_bytes"] == metrics["kernel_code_bytes"] and snapshot["text_section_bytes"] == metrics["text_section_bytes"], "Snapshot differs from experiment metrics")
            require(snapshot["instructions_16"] == metrics["kernel_compressed_instruction_count"], "Compressed count differs from experiment")
            require(snapshot["instructions_16"] + snapshot["instructions_32"] == metrics["kernel_static_instruction_count"], "Instruction count differs from experiment")
        if snapshot["known_padding_bytes"]:
            require(any(item["kind"] == "alignment_map" and item["profile"] == snapshot["profile"] for item in evidence.values()), "Positive padding count needs alignment evidence")

    delta = document["deltas"]
    ref_n = ref["instructions_16"] + ref["instructions_32"]
    cand_n = cand["instructions_16"] + cand["instructions_32"]
    expected = {
        "kernel_delta_bytes": cand["kernel_code_bytes"] - ref["kernel_code_bytes"],
        "instruction_count_term_bytes": 4 * (cand_n - ref_n),
        "encoding_width_term_bytes": -2 * (cand["instructions_16"] - ref["instructions_16"]),
        "unclassified_term_bytes": cand["unclassified_bytes"] - ref["unclassified_bytes"],
        "text_delta_bytes": cand["text_section_bytes"] - ref["text_section_bytes"],
    }
    for key, value in expected.items():
        require(delta[key] == value, "Delta mismatch: " + key)
    require(delta["kernel_delta_bytes"] == sum(delta[key] for key in ["instruction_count_term_bytes", "encoding_width_term_bytes", "unclassified_term_bytes"]), "R001 components do not sum to kernel delta")

    r1_verified = ref["unclassified_bytes"] == cand["unclassified_bytes"] == 0
    r2_verified = ref["inside_text"] and cand["inside_text"]
    require(rules["R001"]["status"] == ("verified" if r1_verified else "abstained"), "R001 status must reflect unknown bytes")
    require(rules["R002"]["status"] == ("verified" if r2_verified else "not_applicable"), "R002 status must reflect section membership")
    if r2_verified:
        require(delta["outside_kernel_delta_bytes"] == delta["text_delta_bytes"] - delta["kernel_delta_bytes"], "R002 does not reconcile")
    else:
        require(delta["outside_kernel_delta_bytes"] is None, "Inapplicable outside-kernel attribution must be null")
    require(document["status"] == ("complete" if r1_verified and r2_verified else "partial"), "Overall completeness status inconsistent")

    for rule_id, required_kinds in {"R001": {"raw_encoding", "symbol_table", "disassembly"}, "R002": {"symbol_table", "section_table"}}.items():
        rule = rules[rule_id]
        if rule["status"] != "verified":
            continue
        used = [evidence[key] for key in rule["evidence_ids"]]
        for snapshot in [ref, cand]:
            matching = [item for item in used if item["profile"] == snapshot["profile"]]
            require(required_kinds <= {item["kind"] for item in matching}, "Verified rule lacks evidence for both profiles")
            for item in matching:
                if item["kind"] == "raw_encoding":
                    require(item["artifact_sha256"] == snapshot["elf_sha256"], "Raw encoding evidence does not match ELF hash")


def must_reject(callback, label: str) -> None:
    try:
        callback()
    except (ValueError, ValidationError):
        return
    raise ValueError("Invalid fixture was accepted: " + label)


def main() -> None:
    policy = load_json("config/attribution-policy.json")
    baseline = load_json("config/baseline.json")
    require(policy["implementation_status"] == "implemented", "Attribution engine implementation status drift")
    require(policy["recommendation_metric"] == "text_section_bytes" and baseline["selection"]["objective"] == "min_text_section_bytes", "Recommendation and analysis scope drift")
    require(policy["reference_profile"] == "O2" and policy["candidate_profiles"] == ["O0", "Os"], "Profile scope drift")
    require(all(rule["causal_claim"] is False for rule in policy["rules"]), "Accounting rules are not causal claims")
    require([rule["id"] for rule in policy["rules"]] == policy["required_rules"] == ["R001", "R002"], "Rule catalog drift")
    plan = load_json("evaluation/plan.json")
    require(plan["analysis_policy_version"] == policy["policy_version"], "Evaluation policy version mismatch")
    validate_plan(plan)
    schema = load_json("contracts/attribution.schema.json")
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    experiments = {}
    for path in (ROOT / "contracts/examples").glob("experiment*.mock.json"):
        experiments[hashlib.sha256(path.read_bytes()).hexdigest()] = json.loads(path.read_text(encoding="utf-8"))
    fixtures = sorted((ROOT / "contracts/examples").glob("attribution*.mock.json"))
    require(len(fixtures) == 5, "Expected complete, scope mismatch, partial, outside and unavailable cases")
    for path in fixtures:
        document = json.loads(path.read_text(encoding="utf-8"))
        require(document["is_mock"] is True, "Design examples must remain synthetic")
        validate_analysis(document, validator, experiments, policy)

    good = load_json("contracts/examples/attribution.complete.mock.json")
    mutations = []
    replacements = [
        (("deltas", "kernel_delta_bytes"), good["deltas"]["kernel_delta_bytes"] + 2, "incorrect byte delta"),
        (("is_mock",), False, "false real provenance"),
        (("rules", 0, "causal_claim"), True, "unsupported causal claim"),
        (("rules", 0, "evidence_ids"), ["missing"], "dangling evidence"),
        (("snapshots", "candidate", "known_padding_bytes"), 9999, "padding double counting"),
        (("rules", 1, "rule_id"), "R001", "duplicate rule"),
        (("evidence", 0, "artifact_path"), "../outside", "escaping evidence path"),
        (("evidence", 0, "artifact_sha256"), "0" * 64, "ELF evidence hash mismatch"),
    ]
    for path, value, label in replacements:
        bad = copy.deepcopy(good)
        parent = bad
        for part in path[:-1]:
            parent = parent[part]
        parent[path[-1]] = value
        mutations.append((bad, label))
    bad = load_json("contracts/examples/attribution.partial.mock.json")
    bad["status"] = "complete"
    mutations.append((bad, "unknown bytes claimed complete"))
    for document, label in mutations:
        must_reject(lambda d=document: validate_analysis(d, validator, experiments, policy), label)
    leaked = copy.deepcopy(plan)
    leaked["held_out"]["families"].append(plan["development"]["families"][0])
    must_reject(lambda: validate_plan(leaked), "evaluation family leakage")
    scope = load_json("contracts/examples/attribution.scope-mismatch.mock.json")
    require(scope["deltas"]["text_delta_bytes"] < 0 < scope["deltas"]["kernel_delta_bytes"], "Scope mismatch fixture must exercise opposite directions")
    print(f"PASS: {len(fixtures)} attribution fixtures, {len(mutations) + 1} rejection guards, byte/evidence/provenance checks and evaluation split policy")
    print("Scope: synthetic contract consistency only; no ELF parsing, RISC-V execution or measured algorithm accuracy.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        sys.exit(1)
