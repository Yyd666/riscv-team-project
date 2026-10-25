"""Check raw execution evidence and, optionally, its projection into SJS's result.

Passed result metrics are checked against independent GNU tools on Linux.
Does not validate attribution correctness, Markdown or M0/M1/M2 as a whole.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_bytes())


def validate(execution_path: Path, experiment_path: Path | None = None) -> dict:
    execution_path = execution_path.resolve(strict=True)
    workspace = execution_path.parent
    record = load(execution_path)
    require(record["is_mock"] is False, "Execution evidence must be real")
    require(not (workspace / "error.json").exists(), "Execution ended with infrastructure failure")
    origin = PurePosixPath(record["workspace"])

    def relocated(path: str) -> Path:
        original = PurePosixPath(path)
        require(".." not in original.parts, "Record path traversal")
        relative = original.relative_to(origin)
        local = (workspace / str(relative)).resolve(strict=True)
        require(local.is_relative_to(workspace), "Record path escapes evidence directory")
        return local

    config = load(workspace / "baseline.json")
    manifest = load(workspace / "manifest.json")
    require(record["baseline_config_sha256"] == digest(workspace / "baseline.json")
            == digest(ROOT / "config/baseline.json"), "Baseline bytes differ")
    require(record["manifest_sha256"] == digest(workspace / "manifest.json")
            == digest(ROOT / "benchmarks/manifest.json"), "Registry bytes differ")
    require(record["baseline_version"] == config["baseline_version"], "Baseline version mismatch")
    require(record["corpus_version"] == manifest["corpus_version"], "Corpus version mismatch")
    program = next(item for item in manifest["benchmarks"] if item["id"] == record["benchmark_id"])
    require(record["source_sha256"] == digest(workspace / "source/main.c")
            == digest(ROOT / program["source"]), "Source bytes differ")
    require(record["experiment_id"] == origin.name, "Experiment ID/workspace mismatch")
    require(record["environment"] == load(workspace / "environment.json"), "Environment mismatch")
    require(record["environment"]["locale"] == "C"
            and record["environment"]["qemu_cpu"] == "rv64", "Environment target mismatch")
    require([item["case_id"] for item in record["inputs"]]
            == [case["id"] for case in program["cases"]], "Missing or reordered input records")
    for item, case in zip(record["inputs"], program["cases"]):
        require(item["stdin_sha256"] == digest(relocated(item["stdin_path"]))
                == digest(ROOT / case["stdin"]), "stdin bytes differ")
        require(item["expected_stdout_sha256"] == digest(relocated(item["expected_stdout_path"]))
                == digest(ROOT / case["stdout"]), "Oracle bytes differ")
    request = load(workspace / "request.json")
    require(request["benchmark_id"] == record["benchmark_id"], "Request benchmark mismatch")
    require([variant["optimization"] for variant in record["variants"]]
            == request["optimizations"], "Missing or reordered profiles")

    def check_process(process: dict, folder: Path) -> tuple[bytes, bytes]:
        metadata = load(folder / "process.json")
        stdout, stderr = (folder / "stdout.bin").read_bytes(), (folder / "stderr.bin").read_bytes()
        for stream, raw in (("stdout", stdout), ("stderr", stderr)):
            require(metadata[stream + "_sha256"] == hashlib.sha256(raw).hexdigest(), "Stream hash drift")
            require(metadata[stream + "_bytes"] == len(raw), "Stream length drift")
            require(process[stream] == raw.decode("utf-8", errors="replace"), "Display/raw mismatch")
        for field in ("argv", "status", "exit_code", "wall_time_ms"):
            require(metadata[field] == process[field], "Process metadata mismatch: " + field)
        return stdout, stderr

    for variant in record["variants"]:
        folder = workspace / variant["optimization"]
        compilation = variant["compilation"]
        check_process(compilation, folder / "compile")
        compiled = compilation["status"] == "completed" and compilation["exit_code"] == 0
        expected_argv = ["/usr/bin/riscv64-linux-gnu-gcc", *config["common_compile_flags"],
                         *config["profiles"][variant["optimization"]],
                         str(origin / "source/main.c"), "-o", str(origin / variant["optimization"] / "program.elf")]
        # Ubuntu may expose equivalent tools under /bin; all remaining argv must be exact.
        require(Path(compilation["argv"][0]).name == "riscv64-linux-gnu-gcc"
                and compilation["argv"][1:] == expected_argv[1:], "Compile command differs from baseline")
        if not compiled:
            require(not variant["runs"] and variant["run_argv"] is None
                    and variant["elf_path"] is None and variant["elf_sha256"] is None,
                    "Failed compilation must not execute or reuse ELF")
            expected_state = ("compile_error" if compilation["status"] == "completed"
                              else compilation["status"])
        else:
            require(relocated(variant["elf_path"]) == folder / "program.elf", "ELF profile path mismatch")
            require(variant["elf_sha256"] == digest(relocated(variant["elf_path"])), "ELF hash drift")
            require([run["case_id"] for run in variant["runs"]]
                    == [case["id"] for case in program["cases"]], "Missing cases after compile")
            expected_run = ["-cpu", "rv64", str(origin / variant["optimization"] / "program.elf")]
            require(Path(variant["run_argv"][0]).name == "qemu-riscv64"
                    and variant["run_argv"][1:] == expected_run, "QEMU target command mismatch")
            expected_state = "execution_passed"
            for run, case in zip(variant["runs"], program["cases"]):
                process = run["process"]
                stdout, stderr = check_process(process, folder / "runs" / case["id"])
                require(process["argv"] == variant["run_argv"], "Per-case command mismatch")
                if process["status"] != "completed":
                    state = process["status"]
                elif process["exit_code"] != program["expected_exit_code"]:
                    state = "runtime_error"
                elif stdout != (ROOT / case["stdout"]).read_bytes() or stderr != b"":
                    state = "wrong_answer"
                else:
                    state = "passed"
                require(run["status"] == state, "Case status contradicts raw evidence")
                require(relocated(run["stdout_path"]) == (folder / "runs" / case["id"] / "stdout.bin")
                        and relocated(run["stderr_path"]) == (folder / "runs" / case["id"] / "stderr.bin"),
                        "Case path mismatch")
                if expected_state == "execution_passed" and state != "passed":
                    expected_state = state
        require(variant["status"] == expected_state, "Variant status contradicts first failing case")

    if experiment_path is not None:
        from jsonschema import Draft202012Validator, FormatChecker
        result = load(experiment_path)
        Draft202012Validator(load(ROOT / "contracts/experiment.schema.json"),
                             format_checker=FormatChecker()).validate(result)
        for field in ("experiment_id", "created_at", "baseline_version", "baseline_config_sha256",
                      "corpus_version", "benchmark_id", "source_sha256", "environment", "is_mock"):
            require(result[field] == record[field], "Result/record mismatch: " + field)
        require(result["inputs"] == [{key: value for key, value in item.items()
                                     if key in ("case_id", "stdin_sha256", "expected_stdout_sha256")}
                                    for item in record["inputs"]], "Result input mismatch")
        require([v["optimization"] for v in result["variants"]] == request["optimizations"],
                "Result dropped or reordered profiles")
        for final, executed in zip(result["variants"], record["variants"]):
            allowed = ["passed", "analysis_error"] if executed["status"] == "execution_passed" else [executed["status"]]
            require(final["status"] in allowed, "Result overwrites execution failure")
            require(final["compile_argv"] == executed["compilation"]["argv"]
                    and final["run_argv"] == executed["run_argv"], "Result command mismatch")
            expected_runs = [{"case_id": run["case_id"], "status": run["status"],
                              **{field: run["process"][field] for field in
                                 ("exit_code", "stdout", "stderr", "wall_time_ms")}}
                             for run in executed["runs"]]
            require(final["runs"] == expected_runs, "Result changed or omitted raw runs")
            if final["status"] == "passed":
                from scripts.elf_reference import inspect_elf, instruction_rows
                metrics, disassembly = inspect_elf(relocated(executed["elf_path"]))
                require(final["metrics"] == metrics, "Result metrics differ from independent ELF reference")
                require(instruction_rows(final["kernel_disassembly"]) == instruction_rows(disassembly),
                        "Result disassembly differs from original ELF")
        eligible = [v for v in result["variants"] if v["status"] == "passed"]
        selected = min(eligible, key=lambda v: (v["metrics"]["text_section_bytes"],
                       config["selection"]["tie_break_order"].index(v["optimization"]))) if eligible else None
        require(result["selection"] == ({"objective": "min_text_section_bytes",
                "optimization": selected["optimization"], "evidence": "static_size_only"} if selected else None),
                "Selection violates correctness gate or tie-break")
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execution", type=Path, required=True)
    parser.add_argument("--experiment", type=Path)
    args = parser.parse_args()
    validate(args.execution, args.experiment)
    print("PASS: execution raw evidence" + (" and result projection" if args.experiment else ""))
    print("Scope: ELF metrics checked only for passed results on Linux; attribution/Markdown/M0/M1/M2 acceptance remain separate.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        sys.exit(1)
