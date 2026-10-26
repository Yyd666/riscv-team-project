"""Command line entry point for the real OptiPilot experiment path."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from backend.app.execution_types import ExecutionError
from backend.app.selection import SelectionInputError, validate_baseline_policy
from backend.app.pipeline import load_baseline, run_experiment

REPO_ROOT = Path(__file__).resolve().parents[1]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="optipilot")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="compile, execute, analyze and select")
    run.add_argument("--benchmark", required=True)
    run.add_argument("--optimizations", nargs="+", choices=("O0", "O2", "Os"), required=True)
    run.add_argument("--output", type=Path, default=Path("artifacts"))
    run.add_argument("--require-attribution", action="store_true")
    report = commands.add_parser("report", help="reserved for REPORT-01")
    report.add_argument("--experiment", required=True)
    report.add_argument("--output", required=True)
    return parser


def _error_code(code: str) -> int:
    if code in {"INVALID_REQUEST", "UNKNOWN_BENCHMARK"}:
        return 2
    if code in {"TOOLCHAIN_UNAVAILABLE", "EXPERIMENT_BUSY", "REQUEST_TIMEOUT",
                "INTERNAL_ERROR", "EXPERIMENT_CANCELLED"}:
        return 5
    return 5


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "report":
        print("REPORT-01 is not implemented yet; no report was generated.", file=sys.stderr)
        return 2
    if args.require_attribution:
        print("ATTR-01 is not implemented; --require-attribution is unavailable.", file=sys.stderr)
        return 2
    try:
        baseline = load_baseline(REPO_ROOT)
        validate_baseline_policy(baseline)
        if len(set(args.optimizations)) != len(args.optimizations):
            raise ExecutionError("INVALID_REQUEST", "Duplicate optimization profile")
        result, result_path, code = run_experiment(
            REPO_ROOT, args.output, args.benchmark,
            tuple(args.optimizations), baseline,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print(f"result_path={result_path}", file=sys.stderr)
        return code
    except (ExecutionError, SelectionInputError) as error:
        document = {
            "error": {
                "code": getattr(error, "code", "INVALID_REQUEST"),
                "message": str(error),
                "details": getattr(error, "details", {}),
            }
        }
        print(json.dumps(document, ensure_ascii=False), file=sys.stderr)
        return _error_code(document["error"]["code"])
    except KeyboardInterrupt:
        print(json.dumps({"error": {"code": "EXPERIMENT_CANCELLED",
                                     "message": "Experiment cancelled",
                                     "details": {}}}), file=sys.stderr)
        return 5
    except Exception as error:
        print(json.dumps({"error": {"code": "INTERNAL_ERROR",
                                     "message": str(error),
                                     "details": {}}}), file=sys.stderr)
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
