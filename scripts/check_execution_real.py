"""Reproduce ENV-01/ENG-01/ENG-02 on Linux. Not an OptiPilot CLI substitute."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.execution import execute, experiment_session
from backend.app.execution.engine import atomic_json
from backend.app.execution_types import ExecutionError, ExecutionRequest
from check_execution_integration import validate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts" / "execution-check")
    args = parser.parse_args()
    manifest = json.loads((ROOT / "benchmarks/manifest.json").read_bytes())
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    groups = []
    for program in manifest["benchmarks"]:
        pair = []
        for repeat in range(2):
            with experiment_session(ROOT, output) as context:
                bundle = execute(ExecutionRequest(program["id"], ("O0", "O2", "Os")),
                                 repo_root=ROOT, context=context)
                validate(context.workspace / "execution.json")
                for variant in bundle.variants:
                    if variant.status != "execution_passed":
                        raise RuntimeError(f"{program['id']}/{variant.optimization}: {variant.status}")
                    if len(variant.runs) != len(program["cases"]):
                        raise RuntimeError("Missing registered input execution")
                pair.append(bundle)
                print(f"PASS: {program['id']} repeat={repeat + 1} {bundle.experiment_id}", flush=True)
        for left, right in zip(pair[0].variants, pair[1].variants):
            if left.elf_sha256 != right.elf_sha256:
                raise RuntimeError("ELF is not deterministic across repeat executions")
            if [r.process.stdout for r in left.runs] != [r.process.stdout for r in right.runs]:
                raise RuntimeError("Outputs differ across repeats")
        groups.append({"benchmark_id": program["id"], "experiments": [b.experiment_id for b in pair],
                       "elf_sha256": {v.optimization: v.elf_sha256 for v in pair[0].variants}})
    inventory = {}
    for group in groups:
        for experiment in group["experiments"]:
            for file in sorted((output / experiment).rglob("*")):
                if file.is_file() and not file.name.startswith("."):
                    inventory[str(file.relative_to(output))] = hashlib.sha256(file.read_bytes()).hexdigest()
    summary = {
        "is_mock": False, "scope": "execution_only_not_static_analysis_or_M0_acceptance",
        "programs": len(groups), "repeats": 2,
        "run_count": sum(len(p["cases"]) for p in manifest["benchmarks"]) * 3 * 2,
        "groups": groups, "artifact_sha256": inventory,
        "git_revision": os.environ.get("GITHUB_SHA"),
        "implementation_sha256": {
            str(file.relative_to(ROOT)): hashlib.sha256(file.read_bytes()).hexdigest()
            for file in sorted((ROOT / "backend").rglob("*.py"))
        },
        "checker_sha256": {str(file.relative_to(ROOT)): hashlib.sha256(file.read_bytes()).hexdigest()
                           for file in (Path(__file__).resolve(), ROOT / "scripts/check_execution_integration.py",
                                        ROOT / "scripts/elf_reference.py")},
    }
    atomic_json(output / "summary.json", summary)
    print(f"PASS: {summary['run_count']} QEMU runs, all cases and deterministic ELF repeats")
    print(f"Evidence: {output / 'summary.json'}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ExecutionError as exc:
        print(json.dumps({"error": {"code": exc.code, "message": str(exc), "details": exc.details}}),
              file=sys.stderr)
        raise SystemExit(5)
