"""Audit experiments against fresh GNU ELF reference measurements.

Producer-side algebra is reported separately from independent byte error. Missing
samples, duplicated experiments, mocks, and invalid corpus splits fail the gate.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.execution.engine import atomic_json
from backend.app.reporting import load_attribution, load_result
from scripts.elf_reference import inspect_elf
from scripts.check_execution_integration import validate as validate_execution
from scripts.evaluation_registry import prepare_program


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fraction(numerator, denominator):
    return numerator / denominator if denominator else None


def _corpus_issues(corpus, *, root=ROOT):
    if not isinstance(corpus, dict) or not isinstance(corpus.get("entries"), list):
        raise ValueError("Corpus must contain an entries list")
    entries = corpus.get("entries", [])
    for entry in entries:
        if not isinstance(entry, dict) or any(not isinstance(entry.get(key), str) or not entry[key]
                                               for key in ("program_id", "split", "source")):
            raise ValueError("Corpus entries require program_id, split and source strings")
        if any(not isinstance(entry.get(key), str) or not entry[key]
               for key in ("family", "provenance", "source_origin", "license")):
            raise ValueError("Corpus family, provenance, source_origin and license are required")
        if "cases" in entry:
            if not isinstance(entry["cases"], list) or not entry["cases"]:
                raise ValueError("Registered input cases must be a non-empty list")
            for case in entry["cases"]:
                if not isinstance(case, dict) or any(not isinstance(case.get(key), str) or not case[key]
                                                    for key in ("case_id", "stdin", "expected_stdout")):
                    raise ValueError("Case IDs and input/oracle paths are required")
                if any(not re.fullmatch(r"[a-f0-9]{64}", str(case.get(key, "")))
                       for key in ("stdin_sha256", "expected_stdout_sha256")):
                    raise ValueError("Case input/oracle SHA-256 hashes are required")
    issues = []
    ids = [entry["program_id"] for entry in entries]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate corpus program IDs")
    if corpus.get("status") != "frozen":
        issues.append("Corpus is not frozen")
    for key in ("family", "provenance", "source_origin"):
        development = {entry.get(key) for entry in entries if entry["split"] == "development"}
        held_out = {entry.get(key) for entry in entries if entry["split"] == "held_out"}
        if development & held_out:
            issues.append(f"Development/held-out {key} leakage: {sorted(development & held_out, key=str)}")
        if None in development | held_out:
            issues.append(f"Missing corpus {key}")
    counts = Counter(entry["split"] for entry in entries)
    for split in ("development", "held_out"):
        target = corpus.get(split + "_target")
        if not isinstance(target, int) or target < 6 or counts[split] < target:
            issues.append(f"{split} program target not met: {counts[split]}/{target}")
    for entry in entries:
        if entry["split"] not in {"development", "held_out"}:
            issues.append(f"Invalid split for {entry['program_id']}")
        source = (root / entry["source"]).resolve()
        if not source.is_relative_to(root) or not source.is_file() or _sha(source) != entry.get("source_sha256"):
            issues.append(f"Source missing or hash mismatch: {entry['program_id']}")
        if "cases" not in entry:
            issues.append(f"Input/oracle hashes are not frozen: {entry['program_id']}")
        elif source.is_relative_to(root) and source.is_file():
            try:
                prepare_program(root, entry, diagnostic=False)
            except (OSError, ValueError) as error:
                issues.append(f"Input/source binding invalid: {entry['program_id']}: {error}")
    return issues


def _formal_provenance(source, result, corpus, corpus_sha256):
    """Diagnostic measurements remain useful, but cannot satisfy a frozen run."""
    try:
        workspace = source.parent
        capture = json.loads((workspace / "evaluation.json").read_bytes())
        if capture.get("mode") != "formal" or capture.get("case_binding_origin") != "registered_hashes":
            return "Diagnostic run or inputs were discovered instead of frozen"
        if corpus.get("status") != "frozen":
            return "Formal evaluation requires a frozen corpus"
        if capture.get("corpus_sha256") != corpus_sha256 or _sha(workspace / "evaluation-corpus.json") != corpus_sha256:
            return "Captured corpus differs from the evaluated frozen registry"
        if result["corpus_version"] != "evaluation-" + corpus["corpus_version"]:
            return "Experiment corpus version is not the formal evaluation version"
        batch = workspace.parent.parent
        if capture.get("batch_id") != batch.name:
            return "Evaluation batch identity does not match the evidence directory"
        registry = batch / "registry-repository"
        if capture.get("manifest_sha256") != _sha(registry / "benchmarks/manifest.json"):
            return "Evaluation registry snapshot hash mismatch"
        implementation_path = workspace / "evaluation-implementation.json"
        if capture.get("implementation_sha256") != _sha(implementation_path):
            return "Implementation record hash mismatch"
        implementation = json.loads(implementation_path.read_bytes())
        if implementation.get("modified_files") != [] or not re.fullmatch(r"[a-f0-9]{40}", str(implementation.get("git_commit", ""))):
            return "Formal evaluation implementation is not a committed revision"
        source_hashes = implementation.get("file_sha256")
        required = {"backend/app/execution/engine.py", "backend/app/analysis/elf.py", "backend/app/attribution.py",
                    "backend/app/pipeline.py", "scripts/run_evaluation_corpus.py", "scripts/evaluate_attribution.py",
                    "scripts/evaluation_registry.py", "contracts/experiment.schema.json", "contracts/attribution.schema.json",
                    "config/baseline.json", "config/attribution-policy.json", "evaluation/corpus.json"}
        if not isinstance(source_hashes, dict) or not required <= source_hashes.keys():
            return "Implementation source inventory is incomplete"
        for name, expected in source_hashes.items():
            path = (batch / "implementation" / name).resolve(strict=True)
            if not path.is_relative_to((batch / "implementation").resolve()) or _sha(path) != expected:
                return "Implementation source snapshot hash mismatch"
        validate_execution(workspace / "execution.json", source, registry_root=registry)
        return None
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        return f"Formal execution provenance unavailable or inconsistent: {error}"


def evaluate(corpus_path: Path, artifacts_root: Path) -> dict[str, Any]:
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    corpus_sha256 = _sha(corpus_path)
    corpus_issues = _corpus_issues(corpus)
    entries = corpus.get("entries", [])
    by_id = {entry["program_id"]: entry for entry in entries}
    located = {program: [] for program in by_id}
    input_errors = []
    for source in sorted(artifacts_root.glob("**/result.json")):
        try:
            result = load_result(source)
            if result["benchmark_id"] not in by_id:
                input_errors.append({"path": str(source), "error": "Unregistered evaluation program"})
                continue
            located[result["benchmark_id"]].append((source, result))
        except (OSError, ValueError) as error:
            input_errors.append({"path": str(source), "error": str(error)})
    comparisons, programs, observed = [], [], []
    ineligible = []
    totals = Counter()
    for program, entry in by_id.items():
        candidates = located[program]
        records = {}
        rejected = "missing_result" if not candidates else "duplicate_result"
        reason = "Exactly one result.json per source program is required"
        if len(candidates) == 1:
            source, result = candidates[0]
            rejected = None
            if result["is_mock"]:
                rejected, reason = "invalid_result", "Mock cannot be counted as a real measurement"
            elif result["source_sha256"] != entry.get("source_sha256"):
                rejected, reason = "invalid_result", "Experiment source hash differs from corpus"
            elif isinstance(entry.get("cases"), list) and result["inputs"] != [
                {key: item[key] for key in ("case_id", "stdin_sha256", "expected_stdout_sha256")}
                for item in entry["cases"]
            ]:
                rejected, reason = "invalid_result", "Experiment input/oracle hashes differ from corpus"
            elif set(v["optimization"] for v in result["variants"]) != {"O0", "O2", "Os"}:
                rejected, reason = "invalid_result", "All three profiles are required for the fixed-profile evaluation"
            if not rejected:
                observed.append(program)
                provenance_error = _formal_provenance(source, result, corpus, corpus_sha256)
                if provenance_error:
                    ineligible.append({"program_id": program, "reason": provenance_error})
                for variant in result["variants"]:
                    totals["attempted_variants"] += 1
                    totals["compile_failures"] += variant["status"] == "compile_error"
                    totals["passed_variants"] += variant["status"] == "passed"
                    for run in variant["runs"]:
                        totals["executed_cases"] += 1
                        totals["failed_cases"] += run["status"] in {"wrong_answer", "runtime_error", "output_limit"}
                        totals["timeout_cases"] += run["status"] == "timeout"
                    profile = variant["optimization"]
                    try:
                        if variant["status"] != "passed":
                            raise ValueError(f"{profile} is {variant['status']}")
                        measured, _ = inspect_elf(source.parent / profile / "program.elf")
                        if measured != variant["metrics"]:
                            raise ValueError("Reported metrics differ from independent GNU reference")
                        records[profile] = measured
                    except (ValueError, OSError) as error:
                        input_errors.append({"program_id": program, "profile": profile, "error": str(error)})
                sizes = {profile: metrics["text_section_bytes"] for profile, metrics in records.items()}
                best = min(sizes, key=lambda p: (sizes[p], ["O2", "Os", "O0"].index(p))) if sizes else None
                chosen = result["selection"]["optimization"] if result["selection"] else None
                regret = sizes[chosen] - sizes[best] if chosen in sizes and best else None
                baseline = {profile: sizes.get(profile) for profile in ("O2", "Os")}
                program_row = {"program_id": program, "split": entry["split"],
                               "fixed_O2_bytes": baseline["O2"], "fixed_Os_bytes": baseline["Os"],
                               "exhaustive_profile": best, "exhaustive_text_bytes": sizes.get(best),
                               "selected_profile": chosen, "regret_bytes": regret}
                for profile in ("O2", "Os"):
                    delta = sizes[chosen] - sizes[profile] if chosen in sizes and profile in sizes else None
                    program_row[f"delta_vs_{profile}_bytes"] = delta
                    program_row[f"relative_change_vs_{profile}"] = delta / sizes[profile] if delta is not None and sizes[profile] else None
                programs.append(program_row)
        for candidate in ("O0", "Os"):
            row = {"program_id": program, "split": entry["split"], "family": entry.get("family"),
                   "candidate_profile": candidate, "status": rejected or "missing_attribution",
                   "byte_error": None, "internal_identity_error": None,
                   "r001_status": None, "r002_status": None,
                   "independent_reference_available": "O2" in records and candidate in records,
                   "independently_correct_rules": []}
            if rejected:
                row["reason"] = reason
            else:
                row["result_path"] = str(source)
                sidecar = source.parent / "attribution" / f"O2-{candidate}" / "attribution.json"
                try:
                    attribution = load_attribution(sidecar, result, source.read_bytes(), workspace=source.parent)
                    if attribution["candidate_profile"] != candidate:
                        raise ValueError("Sidecar candidate profile differs from its comparison directory")
                    row["status"] = attribution["status"]
                    for rule in attribution["rules"]:
                        row[rule["rule_id"].lower() + "_status"] = rule["status"]
                    delta = attribution["deltas"]
                    if delta is not None:
                        predicted = sum(delta[key] for key in ("instruction_count_term_bytes", "encoding_width_term_bytes", "unclassified_term_bytes"))
                        row["internal_identity_error"] = predicted - delta["kernel_delta_bytes"]
                        if row["independent_reference_available"]:
                            ref, cand = records["O2"], records[candidate]
                            actual = cand["kernel_code_bytes"] - ref["kernel_code_bytes"]
                            row["byte_error"] = predicted - actual
                            text_delta = cand["text_section_bytes"] - ref["text_section_bytes"]
                            n_delta = cand["kernel_static_instruction_count"] - ref["kernel_static_instruction_count"]
                            c_delta = cand["kernel_compressed_instruction_count"] - ref["kernel_compressed_instruction_count"]
                            if (delta["kernel_delta_bytes"] == actual and delta["instruction_count_term_bytes"] == 4 * n_delta
                                and delta["encoding_width_term_bytes"] == -2 * c_delta and delta["unclassified_term_bytes"] == 0):
                                row["independently_correct_rules"].append("R001")
                            if delta["text_delta_bytes"] == text_delta and delta["outside_kernel_delta_bytes"] == text_delta - actual:
                                row["independently_correct_rules"].append("R002")
                except (ValueError, OSError) as error:
                    row["status"], row["reason"] = "invalid_attribution", str(error)
                    # Invalid evidence cannot erase the denominator of a producer's
                    # claimed verified rules. Count the claim, never its correctness.
                    try:
                        claimed_rules = json.loads(sidecar.read_text(encoding="utf-8")).get("rules", [])
                        for rule_id in ("R001", "R002"):
                            if any(rule.get("rule_id") == rule_id and rule.get("status") == "verified" for rule in claimed_rules):
                                row[rule_id.lower() + "_status"] = "verified"
                    except (OSError, UnicodeError, ValueError, AttributeError):
                        pass
            comparisons.append(row)
    applicable = [row for row in comparisons if row["independent_reference_available"]]
    measured_rows = [row for row in comparisons if row["byte_error"] is not None]
    claimed = sum(row[key] == "verified" for row in comparisons for key in ("r001_status", "r002_status"))
    correct = sum(row[rule.lower() + "_status"] == "verified" and rule in row["independently_correct_rules"]
                  for row in comparisons for rule in ("R001", "R002"))
    rejected_count = sum(row["status"] != "complete" for row in comparisons)
    metrics = {
        "comparison_count": len(comparisons), "program_count": len(observed),
        "independent_byte_error_denominator": len(measured_rows),
        "byte_error_exact_rate": _fraction(sum(row["byte_error"] == 0 for row in measured_rows), len(measured_rows)),
        "claimed_verified_rules": claimed, "independently_correct_verified_rules": correct,
        "rule_validity_rate": _fraction(correct, claimed),
        "independently_applicable_comparisons": len(applicable),
        "r001_verified_rate": _fraction(sum(row["r001_status"] == "verified" and "R001" in row["independently_correct_rules"] for row in comparisons), len(applicable)),
        "r002_coverage": _fraction(sum(row["r002_status"] == "verified" and "R002" in row["independently_correct_rules"] for row in comparisons), len(applicable)),
        "rejection_rate": _fraction(rejected_count, len(comparisons)),
        "configuration_pass_rate": _fraction(totals["passed_variants"], totals["attempted_variants"]),
        "compile_failure_rate": _fraction(totals["compile_failures"], totals["attempted_variants"]),
        "case_failure_rate": _fraction(totals["failed_cases"], totals["executed_cases"]),
        "zero_gain_vs_O2_programs": sum(row["delta_vs_O2_bytes"] == 0 for row in programs),
        "zero_gain_vs_Os_programs": sum(row["delta_vs_Os_bytes"] == 0 for row in programs),
        "status_counts": dict(Counter(row["status"] for row in comparisons)), **dict(totals),
    }
    return {
        "schema_version": "0.2.0", "is_mock": False, "corpus_sha256": corpus_sha256,
        "corpus_status": corpus.get("status"), "corpus_issues": corpus_issues, "input_errors": input_errors,
        "automated_checks_passed": bool(entries) and not corpus_issues and not input_errors and not rejected_count and not ineligible
            and len(measured_rows) == len(comparisons) and correct == claimed == 2 * len(comparisons)
            and all(row["regret_bytes"] == 0 for row in programs),
        "independent_human_review": "not_assessed", "acceptance_ready": False,
        "formal_ineligible_programs": ineligible,
        "targets": {"development": corpus.get("development_target"), "held_out": corpus.get("held_out_target")},
        "observed_programs": sorted(observed), "missing_programs": sorted(set(by_id) - set(observed)),
        "comparisons": comparisons, "programs": programs, "metrics": metrics,
        "limitations": [
            "Independent GNU checks are automated cross-checks, not the required two-member annotation.",
            "Corpus provenance/family review and numerical-range/oracle review remain separate requirements.",
            "Mock, duplicate and missing programs cannot satisfy sample counts; missing metrics are null.",
            "B0 is fresh GNU ELF inspection; B1/B2/B3 sizes and regret are reported per program.",
            "R001 and R002 are checked separately; no causal optimization-pass or performance claim is computed.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output == args.corpus.resolve() or output.name == "result.json" or output.is_relative_to(args.artifacts.resolve()):
        parser.error("Output must be outside the input experiment tree and differ from the corpus")
    try:
        result = evaluate(args.corpus.resolve(), args.artifacts.resolve())
        output.parent.mkdir(parents=True, exist_ok=True)
        atomic_json(output, result)
    except (OSError, ValueError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result["metrics"], ensure_ascii=False))
    return 0 if result["automated_checks_passed"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
