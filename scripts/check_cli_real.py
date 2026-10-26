"""Real CLI/report/attribution integration with independent GNU ELF checks."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.execution import ProcessRunner
from backend.app.execution.engine import atomic_json
from backend.app.execution_types import ExecutionContext
from backend.app.reporting import load_attribution
from scripts.check_execution_integration import validate
from scripts.elf_reference import inspect_elf


def check(output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    runner = ProcessRunner(ExecutionContext(ROOT, time.monotonic() + 600))
    comparisons = []
    commands = []

    def cli(label, args, expected):
        argv = [sys.executable, "-B", "-m", "optipilot", *args]
        process = runner.run(argv, cwd=ROOT, timeout_s=140, max_output_bytes=1048576)
        (output / (label + ".stdout.bin")).write_bytes(process.stdout)
        (output / (label + ".stderr.bin")).write_bytes(process.stderr)
        commands.append({"argv": argv, "status": process.status, "exit_code": process.exit_code,
                         "expected_exit_code": expected})
        atomic_json(output / "commands.json", commands)
        if process.status != "completed" or process.exit_code != expected:
            raise ValueError(f"{label}: expected {expected}, got {process.status}/{process.exit_code}")
        return process

    for program in ("sum_u32", "dot_i32", "threshold_count"):
        process = cli(program, ["run", "--benchmark", program, "--optimizations", "O0", "O2", "Os",
                               "--require-attribution", "--output", str(output / "experiments")], 0)
        result = json.loads(process.stdout)
        source = output / "experiments" / result["experiment_id"] / "result.json"
        validate(source.parent / "execution.json", source)
        measured = {profile: inspect_elf(source.parent / profile / "program.elf")[0] for profile in ("O0", "O2", "Os")}
        for candidate in ("O0", "Os"):
            path = source.parent / "attribution" / f"O2-{candidate}" / "attribution.json"
            attribution = load_attribution(path, result, source.read_bytes(), workspace=source.parent)
            if attribution["status"] != "complete":
                raise ValueError(attribution["reason"])
            ref, cand = measured["O2"], measured[candidate]
            delta = attribution["deltas"]
            expected = {
                "kernel_delta_bytes": cand["kernel_code_bytes"] - ref["kernel_code_bytes"],
                "instruction_count_term_bytes": 4 * (cand["kernel_static_instruction_count"] - ref["kernel_static_instruction_count"]),
                "encoding_width_term_bytes": -2 * (cand["kernel_compressed_instruction_count"] - ref["kernel_compressed_instruction_count"]),
                "unclassified_term_bytes": 0,
                "text_delta_bytes": cand["text_section_bytes"] - ref["text_section_bytes"],
            }
            expected["outside_kernel_delta_bytes"] = expected["text_delta_bytes"] - expected["kernel_delta_bytes"]
            if delta != expected:
                raise ValueError(f"{program}/{candidate}: sidecar differs from independent GNU measurements")
            for role, profile in (("reference", "O2"), ("candidate", candidate)):
                snapshot, actual = attribution["snapshots"][role], measured[profile]
                if snapshot["instructions_16"] != actual["kernel_compressed_instruction_count"] or (
                    snapshot["instructions_16"] + snapshot["instructions_32"] != actual["kernel_static_instruction_count"]
                ):
                    raise ValueError("Sidecar absolute encoding counts differ from independent reference")
            comparisons.append({"program_id": program, "candidate": candidate, **expected})
        cli(program + "-report", ["report", "--experiment", str(source), "--attribution", str(path),
                                  "--output", str(source.parent / "report.md")], 0)
    cli("reference-only", ["run", "--benchmark", "sum_u32", "--optimizations", "O2", "--require-attribution",
                           "--output", str(output / "reference-only")], 4)
    rejected = cli("missing-reference", ["run", "--benchmark", "sum_u32", "--optimizations", "O0",
                                       "--require-attribution", "--output", str(output / "missing-reference")], 4)
    result = json.loads(rejected.stdout)
    sidecar = output / "missing-reference" / result["experiment_id"] / "attribution/O2-O0/attribution.json"
    if json.loads(sidecar.read_bytes())["status"] != "unavailable":
        raise ValueError("Missing reference did not produce unavailable attribution")
    cli("unknown-program", ["run", "--benchmark", "unregistered_program", "--optimizations", "O2",
                            "--output", str(output / "unknown-program")], 2)
    inventory = {str(path.relative_to(output)): hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in sorted(output.rglob("*"))
                 if path.is_file() and path.name not in {".execution.lock", ".execution-started"}}
    summary = {"is_mock": False, "passed": True, "programs": 3, "profiles": 9, "primary_case_runs": 27,
               "comparisons": comparisons, "commands": commands, "artifact_sha256": inventory,
               "scope": "Registered CLI integration and GNU cross-checks; not M2 corpus or human annotation"}
    atomic_json(output / "summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/cli-check")
    args = parser.parse_args()
    output = args.output.resolve() / ("check-" + uuid.uuid4().hex)
    try:
        summary = check(output)
        print(f"PASS: {summary['primary_case_runs']} primary case runs, {len(summary['comparisons'])} independent comparisons; {output}")
        return 0
    except Exception as error:
        output.mkdir(parents=True, exist_ok=True)
        atomic_json(output / "failure.json", {"passed": False, "error": str(error)})
        print(f"FAIL: {error}; {output}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
