"""Run the frozen evaluation corpus with the fixed RV64GC toolchain."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import time
from typing import Any

from backend.app.analysis import analyze_elf
from backend.app.attribution import generate_attributions
from backend.app.execution import ProcessRunner
from backend.app.execution.engine import atomic_json
from backend.app.execution_types import ExecutionContext


FLAGS = ["-std=c11", "-Wall", "-Wextra", "-Werror", "-static", "-fno-pie", "-no-pie", "-march=rv64gc", "-mabi=lp64d"]


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _run_case(runner: ProcessRunner, argv: list[str], cwd: Path, stdin: bytes, deadline: float):
    return runner.run(argv, cwd=cwd, timeout_s=min(20.0, max(0.1, deadline - time.monotonic())), max_output_bytes=1048576, stdin=stdin)


def run_program(root: Path, entry: dict[str, Any], output_root: Path) -> Path:
    program_id = entry["program_id"]
    source = root / entry["source"]
    workspace = output_root / program_id
    workspace.mkdir(parents=True, exist_ok=True)
    context = ExecutionContext(workspace, time.monotonic() + 600)
    runner = ProcessRunner(context)
    cases = sorted((source.parent / "cases").glob("*.in"))
    case_data = [(case.stem, case.read_bytes(), case.with_suffix(".out").read_bytes()) for case in cases]
    variants = []
    cc = shutil.which("riscv64-linux-gnu-gcc") or "/usr/bin/riscv64-linux-gnu-gcc"
    qemu = shutil.which("qemu-riscv64") or "/usr/bin/qemu-riscv64"
    readelf = shutil.which("riscv64-linux-gnu-readelf") or "/usr/bin/riscv64-linux-gnu-readelf"
    size = shutil.which("riscv64-linux-gnu-size") or "/usr/bin/riscv64-linux-gnu-size"
    objdump = shutil.which("riscv64-linux-gnu-objdump") or "/usr/bin/riscv64-linux-gnu-objdump"
    for profile, flag in (("O0", "-O0"), ("O2", "-O2"), ("Os", "-Os")):
        folder = workspace / profile
        folder.mkdir(exist_ok=True)
        elf = folder / "program.elf"
        compile_argv = [cc, *FLAGS, flag, str(source.resolve()), "-o", str(elf)]
        compile_result = _run_case(runner, compile_argv, folder, b"", context.deadline)
        (folder / "compile.stdout.bin").write_bytes(compile_result.stdout)
        (folder / "compile.stderr.bin").write_bytes(compile_result.stderr)
        runs = []
        status = "passed"
        run_argv = [qemu, "-cpu", "rv64", str(elf)]
        if compile_result.status != "completed" or compile_result.exit_code != 0 or not elf.is_file():
            status = "compile_error"
            run_argv = None
        else:
            for case_id, stdin, expected in case_data:
                result = _run_case(runner, run_argv, folder, stdin, context.deadline)
                case_status = "passed" if result.status == "completed" and result.exit_code == 0 and result.stdout == expected and result.stderr == b"" else "wrong_answer"
                if result.status != "completed": case_status = result.status
                if case_status != "passed" and status == "passed": status = case_status
                runs.append({"case_id": case_id, "status": case_status, "exit_code": result.exit_code,
                             "stdout": result.stdout.decode("utf-8", errors="replace"),
                             "stderr": result.stderr.decode("utf-8", errors="replace"),
                             "wall_time_ms": result.wall_time_ms})
        analysis = None
        if status == "passed":
            analysis = analyze_elf(elf, context=context, tools={"readelf": readelf, "size": size, "objdump": objdump})
            if analysis.status != "passed": status = "analysis_error"
        metrics = analysis.metrics if analysis and analysis.status == "passed" else None
        evidence = analysis.evidence if analysis else {}
        variants.append({
            "optimization": profile, "status": status,
            "compile_argv": compile_argv, "run_argv": run_argv,
            "analysis_argv": evidence.get("analysis_argv", []),
            "diagnostics": (compile_result.stderr.decode("utf-8", errors="replace") + ("\n" + (analysis.reason or "") if analysis and analysis.reason else "")).strip(),
            "kernel_disassembly": analysis.kernel_disassembly if analysis and analysis.status == "passed" else None,
            "metrics": metrics, "runs": runs,
        })
    passed = [v for v in variants if v["status"] == "passed" and v["metrics"]]
    selection = None
    if passed:
        selection = {"objective": "min_text_section_bytes", "optimization": min(passed, key=lambda item: (item["metrics"]["text_section_bytes"], ("O2", "Os", "O0").index(item["optimization"]))) ["optimization"], "evidence": "static_size_only"}
    result = {
        "schema_version": "0.1.0", "experiment_id": f"eval-{program_id}", "is_mock": False,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "baseline_version": "0.1.0", "baseline_config_sha256": _sha((root / "config/baseline.json").read_bytes()),
        "corpus_version": "evaluation-0.1.0", "benchmark_id": program_id,
        "source_sha256": _sha(source.read_bytes()),
        "inputs": [{"case_id": case_id, "stdin_sha256": _sha(stdin), "expected_stdout_sha256": _sha(expected)} for case_id, stdin, expected in case_data],
        "environment": {"os": "Linux evaluation runner", "kernel": "recorded by WSL2", "python_version": "3.12", "compiler_version": cc, "binutils_version": objdump, "qemu_version": qemu, "qemu_cpu": "rv64", "libc_version": "cross", "locale": "C"},
        "variants": variants, "selection": selection,
    }
    result_path = workspace / "result.json"
    atomic_json(result_path, result)
    generate_attributions(result_path, result)
    return result_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    corpus = json.loads(args.corpus.read_text(encoding="utf-8"))
    args.output.mkdir(parents=True, exist_ok=True)
    for entry in corpus["entries"]:
        path = run_program(root, entry, args.output)
        print(f"PASS: {entry['program_id']} {path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
