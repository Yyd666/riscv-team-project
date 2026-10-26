"""Execute trusted derived fixtures and audit actual attribution rejection states.

These are adversarial integration fixtures, never independent corpus samples.
Compilation, tool, or oracle failures cannot count as a successful rejection.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.attribution import generate_attributions
from backend.app.execution.engine import atomic_json
from backend.app.pipeline import load_baseline, run_experiment
from backend.app.reporting import ReportInputError, load_attribution

CASES = ("unknown_16", "unknown_32", "missing_symbol", "symbol_outside_text", "truncated_encoding", "conflicting_evidence")


def source_for(case: str, original: str) -> str:
    if case == "symbol_outside_text":
        return original.replace("__attribute__((noinline))", '__attribute__((noinline, section(".kernel_extra")))')
    if case == "missing_symbol":
        return re.sub(r"\bkernel\b", "hidden_kernel", original)
    if case == "conflicting_evidence":
        return original
    body = {"unknown_16": ".2byte 0", "unknown_32": ".4byte 0x0000000b",
            "truncated_encoding": ".byte 0x13"}[case]
    wrapper = ('extern uint32_t kernel(const uint32_t *, unsigned int);\n'
               '__asm__(".text\\n.option rvc\\n.globl kernel\\n.type kernel,@function\\n"\n'
               '        "kernel:\\ntail kernel_impl\\n' + body + '\\n.size kernel,.-kernel\\n'
               + ('.byte 0\\n' if case == "truncated_encoding" else '') + '");\n')
    return original.replace("uint32_t kernel(", "uint32_t kernel_impl(", 1).replace("int main(void)", wrapper + "\nint main(void)")


def assess(case: str, result: dict, attribution: dict, *, report_rejected=False) -> tuple[bool, str]:
    if len(result["variants"]) != 2 or any(not v["runs"] or any(run["status"] != "passed" for run in v["runs"]) for v in result["variants"]):
        return False, "Fixture did not compile and pass every oracle case"
    r1, r2 = ({rule["rule_id"]: rule["status"] for rule in attribution["rules"]}[rule] for rule in ("R001", "R002"))
    if case == "conflicting_evidence":
        passed = (all(v["status"] == "passed" for v in result["variants"])
                  and attribution["status"] == "unavailable" and (r1, r2) == ("abstained", "abstained")
                  and report_rejected and "changed after analysis" in attribution["reason"])
    elif any(v["status"] != "analysis_error" for v in result["variants"]):
        passed = False
    elif case == "missing_symbol":
        passed = attribution["status"] == "unavailable" and "kernel function" in attribution["reason"] and (r1, r2) == ("abstained", "abstained")
    elif case == "symbol_outside_text":
        passed = attribution["status"] == "partial" and (r1, r2) == ("verified", "not_applicable") and attribution["deltas"]["outside_kernel_delta_bytes"] is None
    else:
        passed = attribution["status"] == "partial" and (r1, r2) == ("abstained", "verified") and all(
            snapshot["unclassified_bytes"] > 0 for snapshot in attribution["snapshots"].values())
    return passed, "Expected domain rejection verified" if passed else "Attribution state or evidence rejection differs from the fixture expectation"


def run_case(case: str, folder: Path) -> dict:
    fixture = folder / "fixture-repository"
    fixture.mkdir(parents=True)
    shutil.copytree(ROOT / "config", fixture / "config")
    shutil.copytree(ROOT / "benchmarks", fixture / "benchmarks")
    source = fixture / "benchmarks/sum_u32/main.c"
    source.write_text(source_for(case, source.read_text(encoding="utf-8")), encoding="utf-8", newline="\n")
    result, path, code = run_experiment(fixture, folder / "execution", "sum_u32", ("O2", "Os"),
                                        load_baseline(fixture), require_attribution=True)
    attribution_path = path.parent / "attribution/O2-Os/attribution.json"
    report_rejected = False
    if case == "conflicting_evidence":
        if code != 0:
            return {"case": case, "passed": False, "reason": "Conflict control experiment failed", "result_path": str(path)}
        saved = attribution_path.read_bytes()
        (folder / "original-attribution.json").write_bytes(saved)
        target = path.parent / "Os/analysis/readelf-symbols.txt"
        (folder / "original-readelf-symbols.txt").write_bytes(target.read_bytes())
        text = target.read_text(encoding="utf-8")
        changed, count = re.subn(r"(\s)([0-9a-fA-F]+)(\s+\d+\s+FUNC\s+\S+\s+\S+\s+\d+\s+kernel\s*$)",
                                lambda m: m[1] + f"{int(m[2],16)+2:016x}" + m[3], text, flags=re.MULTILINE)
        if count != 1:
            raise ValueError("Unable to construct a contradictory symbol-boundary artifact")
        target.write_text(changed, encoding="utf-8", newline="\n")
        try:
            load_attribution(attribution_path, result, path.read_bytes(), workspace=path.parent)
        except ReportInputError:
            report_rejected = True
        _, complete = generate_attributions(path)
        if complete:
            raise ValueError("Conflicting evidence unexpectedly yielded complete attribution")
    attribution = load_attribution(attribution_path, result, path.read_bytes(), workspace=path.parent)
    passed, reason = assess(case, result, attribution, report_rejected=report_rejected)
    if case != "conflicting_evidence" and code != 3:
        passed, reason = False, f"Expected analysis failure exit 3, got {code}"
    return {"case": case, "passed": passed, "reason": reason, "cli_exit_code": code,
            "variant_statuses": [v["status"] for v in result["variants"]],
            "attribution_status": attribution["status"], "attribution_reason": attribution["reason"],
            "rules": attribution["rules"], "result_path": str(path), "report_rejected_conflict": report_rejected}


def run_suite(output: Path) -> dict:
    evidence = output.parent / (output.stem + "-evidence-" + uuid.uuid4().hex)
    evidence.mkdir(parents=True, exist_ok=False)
    rows = []
    for case in CASES:
        folder = evidence / case
        try:
            row = run_case(case, folder)
        except Exception as error:
            folder.mkdir(parents=True, exist_ok=True)
            row = {"case": case, "passed": False, "reason": str(error),
                   "error_code": getattr(error, "code", "INTERNAL_ERROR"),
                   "failure_kind": "infrastructure_or_fixture_error"}
            atomic_json(folder / "failure.json", row)
        rows.append(row)
    inventory = {str(path.relative_to(evidence)): hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in sorted(evidence.rglob("*"))
                 if path.is_file() and path.name not in {".execution.lock", ".execution-started"}}
    document = {"is_mock": False, "scope": "Adversarial derived integration fixtures; not independent evaluation samples",
                "evidence_root": str(evidence), "cases": rows,
                "all_rejected": len(rows) == len(CASES) and all(row["passed"] for row in rows),
                "artifact_sha256": inventory}
    atomic_json(output, document)
    return document


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        parser.error("Output already exists; choose a new summary path to preserve previous evidence")
    output.parent.mkdir(parents=True, exist_ok=True)
    document = run_suite(output)
    print(json.dumps({"cases": len(document["cases"]), "all_rejected": document["all_rejected"],
                      "evidence_root": document["evidence_root"]}, ensure_ascii=False))
    return 0 if document["all_rejected"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
