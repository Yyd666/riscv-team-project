"""Exercise execution -> candidate analysis with real ELF evidence.

Development gate only: loads one trusted local Git module at a resolved commit.
It never fetches, merges, alters the candidate branch, or emits product result.json.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import time
import types
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.execution import execute, experiment_session, ProcessRunner
from backend.app.execution.engine import atomic_json
from backend.app.execution_types import ExecutionContext, ExecutionError, ExecutionRequest
from scripts.check_execution_integration import validate
from scripts.elf_reference import inspect_elf

MODULE_PATH = "backend/app/analysis/elf.py"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def record_process(folder: Path, process) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "stdout.bin").write_bytes(process.stdout)
    (folder / "stderr.bin").write_bytes(process.stderr)
    atomic_json(folder / "process.json", {
        "argv": list(process.argv), "status": process.status, "exit_code": process.exit_code,
        "wall_time_ms": process.wall_time_ms,
        "stdout_sha256": digest(process.stdout), "stderr_sha256": digest(process.stderr),
    })


def run_recorded(runner: ProcessRunner, argv: list[str], folder: Path, timeout: float = 5):
    try:
        result = runner.run(argv, cwd=runner.context.workspace, timeout_s=timeout,
                            max_output_bytes=1048576)
    except ExecutionError as error:
        if hasattr(error, "process_result"):
            record_process(folder, error.process_result)
        raise
    record_process(folder, result)
    if result.status != "completed" or result.exit_code != 0:
        raise ExecutionError("INTEGRATION_SETUP_FAILED", "Command failed", argv=argv)
    return result.stdout


def load_candidate(repo: Path, revision: str, audit: Path):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_./-]*", revision):
        raise ValueError("Use a local Git ref or full commit ID")
    git = shutil.which("git", path=os.defpath)
    if git is None:
        raise ExecutionError("TOOLCHAIN_UNAVAILABLE", "Git is required for source pinning")
    context = ExecutionContext(audit, time.monotonic() + 30)
    runner = ProcessRunner(context)
    commit = run_recorded(runner, [git, "-C", str(repo), "rev-parse", "--verify",
                                  revision + "^{commit}"], audit / "resolve").decode().strip()
    if not re.fullmatch(r"[a-f0-9]{40,64}", commit):
        raise ValueError("Invalid resolved commit")
    source = run_recorded(runner, [git, "-C", str(repo), "show", commit + ":" + MODULE_PATH],
                          audit / "source")
    consumer_commit = run_recorded(runner, [git, "-C", str(repo), "rev-parse", "HEAD"],
                                   audit / "consumer").decode().strip()
    (audit / "analysis.snapshot.py").write_bytes(source)
    name = "backend.app._candidate_" + commit
    module = types.ModuleType(name)
    module.__package__ = "backend.app.analysis"
    module.__file__ = str(audit / "analysis.snapshot.py")
    sys.modules[name] = module
    try:
        exec(compile(source, module.__file__, "exec"), module.__dict__)
        if not callable(getattr(module, "analyze_elf", None)):
            raise ValueError("Candidate has no analyze_elf entry point")
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module, {"candidate_commit": commit, "candidate_module": MODULE_PATH,
                    "candidate_source_sha256": digest(source), "consumer_commit": consumer_commit}


def analyze_recorded(module, elf: Path, context: ExecutionContext, folder: Path) -> dict:
    folder.mkdir(parents=True, exist_ok=True)
    original = module.ProcessRunner

    class AuditRunner(ProcessRunner):
        def run(self, argv, **kwargs):
            number = len(list(folder.glob("command-*")))
            try:
                result = super().run(argv, **kwargs)
            except ExecutionError as error:
                if hasattr(error, "process_result"):
                    record_process(folder / f"command-{number:02d}", error.process_result)
                raise
            record_process(folder / f"command-{number:02d}", result)
            return result

    # Record actual calls without changing argv, streams, limits or statuses.
    module.ProcessRunner = AuditRunner
    try:
        try:
            result = module.analyze_elf(elf, context=context)
            document = result.to_dict()
            document["failure_mode"] = None
        except module.AnalysisError as error:
            if error.code != "ANALYSIS_ERROR":
                raise ExecutionError(error.code, str(error), **error.details) from error
            document = {"status": "analysis_error", "reason": str(error), "metrics": None,
                        "evidence": error.details, "failure_mode": "AnalysisError"}
        for process_path in folder.glob("command-*/process.json"):
            process = json.loads(process_path.read_bytes())
            if process["status"] != "completed" or process["exit_code"] != 0:
                raise ExecutionError("INTEGRATION_TOOL_FAILED", "Analysis subprocess failed",
                                     argv=process["argv"], status=process["status"],
                                     exit_code=process["exit_code"])
        atomic_json(folder / "analysis.json", document)
        return document
    finally:
        module.ProcessRunner = original


def compare_positive(module, variant, context: ExecutionContext) -> dict:
    folder = context.workspace / "analysis" / variant.optimization
    observed = analyze_recorded(module, variant.elf_path, context, folder)
    expected, _ = inspect_elf(variant.elf_path)
    atomic_json(folder / "independent_metrics.json", expected)
    passed = (observed["status"] == "passed" and observed["metrics"] == expected
              and observed["evidence"].get("elf_sha256") == variant.elf_sha256)
    return {"kind": "registered_program", "profile": variant.optimization,
            "elf_sha256": variant.elf_sha256, "qemu_runs": len(variant.runs),
            "expected": "passed_with_exact_metrics", "observed": observed["status"],
            "passed": passed, "reason": observed.get("reason")}


def negative_source(case: str) -> tuple[str, str, str]:
    symbol = "other" if case == "missing_symbol" else "kernel"
    section = ".init" if case == "outside_text" else ".text"
    body = {"unknown_16": ".2byte 0x0000\n", "unknown_32": ".4byte 0x0000000b\n"}.get(
        case, "addi a0,zero,0\nret\n")
    if case == "outside_text":
        body = "c.nop\nc.jr ra\n"
    length = ".-" + symbol + ("+128" if case == "symbol_overflow" else "")
    assembly = (f'.section {section},"ax"\n.globl {symbol}\n.type {symbol},@function\n'
                f'{symbol}:\n{body}.size {symbol},{length}\n')
    if section != ".text":
        assembly += '.section .text,"ax"\nnop\nnop\nnop\nnop\n'
    return assembly, symbol, "rv64im" if case == "wrong_isa_abi" else "rv64gc"


def check_negative(module, case: str, repo: Path, output: Path, config: dict) -> dict:
    with experiment_session(repo, output) as context:
        runner = ProcessRunner(context)
        cc = shutil.which(config["tools"]["cc"], path=os.defpath)
        if cc is None:
            raise ExecutionError("TOOLCHAIN_UNAVAILABLE", "Missing RISC-V compiler")
        elf = context.workspace / "fixture.elf"
        if case == "dynamic_elf":
            source = repo / "benchmarks/sum_u32/main.c"
            argv = [cc, *[flag for flag in config["common_compile_flags"] if flag != "-static"],
                    "-O2", str(source), "-o", str(elf)]
        else:
            assembly, symbol, isa = negative_source(case)
            source = context.workspace / "fixture.S"
            source.write_text(assembly, encoding="utf-8")
            argv = [cc, "-march=" + isa, "-mabi=" + ("lp64" if isa == "rv64im" else "lp64d"),
                    "-nostdlib", "-static", "-no-pie", "-Wl,-e," + symbol,
                    str(source), "-o", str(elf)]
        run_recorded(runner, argv, context.workspace / "fixture_compile", 20)
        observed = analyze_recorded(module, elf, context, context.workspace / "analysis")
        # A thrown infrastructure error must never be treated as a successful rejection.
        passed = observed["status"] == "analysis_error" and observed["metrics"] is None
        record = {"case": case, "kind": "handwritten_negative_fixture",
                  "counts_as_evaluation_sample": False,
                  "experiment_id": context.workspace.name, "expected": "analysis_error",
                  "observed": observed["status"], "passed": passed,
                  "reason": observed.get("reason"), "elf_sha256": digest(elf.read_bytes())}
        atomic_json(context.workspace / "case.json", record)
        return record


def run_gate(repo: Path, revision: str, output: Path) -> tuple[dict, Path]:
    output = output.resolve() / ("integration-" + uuid.uuid4().hex)
    output.mkdir(parents=True, exist_ok=False)
    summary = {"is_mock": False, "scope": "execution_analysis_boundary_not_M0_M1_M2_acceptance",
               "status": "running", "positive_cases": [], "negative_cases": [],
               "baseline_sha256": digest((repo / "config/baseline.json").read_bytes())}
    module = None
    try:
        source_dir = output / "candidate"
        source_dir.mkdir()
        module, provenance = load_candidate(repo, revision, source_dir)
        summary.update(provenance)
        config = json.loads((repo / "config/baseline.json").read_bytes())
        manifest = json.loads((repo / "benchmarks/manifest.json").read_bytes())
        for program in manifest["benchmarks"]:
            with experiment_session(repo, output) as context:
                bundle = execute(ExecutionRequest(program["id"], ("O0", "O2", "Os")),
                                 repo_root=repo, context=context)
                validate(context.workspace / "execution.json")
                for variant in bundle.variants:
                    if variant.status != "execution_passed":
                        raise ExecutionError("INTEGRATION_SETUP_FAILED", "Execution failed before analysis")
                    check = compare_positive(module, variant, context)
                    check.update(benchmark_id=program["id"], experiment_id=bundle.experiment_id)
                    summary["positive_cases"].append(check)
                    print(("PASS" if check["passed"] else "FAIL") + ": " + program["id"]
                          + "/" + variant.optimization, flush=True)
        for case in ("unknown_16", "unknown_32", "missing_symbol", "outside_text",
                     "symbol_overflow", "dynamic_elf", "wrong_isa_abi"):
            check = check_negative(module, case, repo, output, config)
            summary["negative_cases"].append(check)
            print(("PASS" if check["passed"] else "FAIL") + ": " + case, flush=True)
        checks = summary["positive_cases"] + summary["negative_cases"]
        summary["status"] = "passed" if all(case["passed"] for case in checks) else "failed"
    except Exception as error:
        summary["status"] = "infrastructure_error"
        summary["error"] = {"code": getattr(error, "code", "INTERNAL_ERROR"), "message": str(error)}
        raise
    finally:
        if module is not None:
            sys.modules.pop(module.__name__, None)
        summary["implementation_sha256"] = {
            str(path.relative_to(repo)): digest(path.read_bytes()) for path in
            [Path(__file__).resolve(), repo / "scripts/elf_reference.py",
             repo / "backend/app/execution_types.py", *sorted((repo / "backend/app/execution").glob("*.py"))]}
        summary["artifact_sha256"] = {
            path.relative_to(output).as_posix(): digest(path.read_bytes())
            for path in sorted(output.rglob("*")) if path.is_file() and not path.name.startswith(".")}
        atomic_json(output / "summary.json", summary)
        print("Evidence: " + str(output / "summary.json"), flush=True)
    return summary, output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis-ref", required=True, help="Trusted local Git ref; run git fetch first")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary, _ = run_gate(ROOT, args.analysis_ref, args.output)
    print("Integration status: " + summary["status"])
    return 0 if summary["status"] == "passed" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ExecutionError, ValueError) as error:
        print("Infrastructure/setup failure: " + str(error), file=sys.stderr)
        raise SystemExit(5)
