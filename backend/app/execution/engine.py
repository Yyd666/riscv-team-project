"""Execution records for trusted registered programs, prior to static analysis."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import struct
import sys
import tempfile
from threading import Lock, get_ident
import time
from typing import Iterator
import uuid

from ..execution_types import (
    CaseExecution, ExecutionBundle, ExecutionContext, ExecutionError, ExecutionRequest,
    InputRecord, ProcessResult, VariantExecution,
)
from .process import ProcessRunner

_LOCK = Lock()
_ACTIVE_CONTEXT: ExecutionContext | None = None
_OWNER_THREAD: int | None = None
_FLAGS = ["-std=c11", "-Wall", "-Wextra", "-Werror", "-static", "-fno-pie",
          "-no-pie", "-march=rv64gc", "-mabi=lp64d"]
_TOOLS = {"cc": "riscv64-linux-gnu-gcc", "objdump": "riscv64-linux-gnu-objdump",
          "readelf": "riscv64-linux-gnu-readelf", "size": "riscv64-linux-gnu-size",
          "qemu": "qemu-riscv64"}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic_json(path: Path, value: object) -> None:
    """No partial JSON may be mistaken for a complete record."""
    data = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    fd, temporary = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _plain(value: object) -> object:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, bytes):
        # JSON text is for display; exact evidence is always in the raw files.
        return value.decode("utf-8", errors="replace")
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    return value


def _asset(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or Path(relative).is_absolute():
        raise ExecutionError("INVALID_REQUEST", "Registered asset path must be relative")
    try:
        result = (root / relative).resolve(strict=True)
    except OSError as exc:
        raise ExecutionError("INVALID_REQUEST", "Missing registered asset", path=relative) from exc
    if not result.is_relative_to(root) or not result.is_file():
        raise ExecutionError("INVALID_REQUEST", "Asset escapes repository", path=relative)
    return result


def _load_assets(root: Path) -> tuple[dict, dict, bytes, bytes]:
    try:
        raw_config = _asset(root, "config/baseline.json").read_bytes()
        raw_manifest = _asset(root, "benchmarks/manifest.json").read_bytes()
        config, manifest = json.loads(raw_config), json.loads(raw_manifest)
        if (config["schema_version"] != "0.1.0" or config["baseline_version"] != "0.1.0"
                or config["target"] != {"isa": "rv64gc", "abi": "lp64d",
                                        "triplet": "riscv64-linux-gnu", "qemu_cpu": "rv64"}
                or config["common_compile_flags"] != _FLAGS or config["tools"] != _TOOLS
                or config["profiles"] != {"O0": ["-O0"], "O2": ["-O2"], "Os": ["-Os"]}):
            raise ValueError("Baseline target, flags, profiles or tools changed")
        limits = config["limits"]
        if limits != {"compile_timeout_s": 20, "analysis_tool_timeout_s": 5,
                      "run_timeout_s": 3, "experiment_timeout_s": 120,
                      "max_output_bytes_per_stream": 1048576, "max_concurrent_experiments": 1}:
            raise ValueError("Execution limits changed; review baseline and adapter together")
        programs = manifest["benchmarks"]
        if not programs or len({p["id"] for p in programs}) != len(programs):
            raise ValueError("Empty corpus or duplicate benchmark IDs")
        for program in programs:
            if (not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", program["id"])
                    or program["kernel_symbol"] != "kernel"
                    or program["expected_exit_code"] != 0 or program["expected_stderr"] != ""
                    or not program["cases"]):
                raise ValueError("Invalid registered program")
            cases = program["cases"]
            if len({case["id"] for case in cases}) != len(cases):
                raise ValueError("Duplicate case IDs")
            if any(not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", case["id"]) for case in cases):
                raise ValueError("Invalid case ID")
        return config, manifest, raw_config, raw_manifest
    except (KeyError, TypeError, ValueError) as exc:
        raise ExecutionError("INVALID_REQUEST", "Invalid repository baseline or registry",
                             reason=str(exc)) from exc


def validate_request(request: ExecutionRequest, manifest: dict) -> dict:
    if (not isinstance(request, ExecutionRequest)
            or not isinstance(request.benchmark_id, str)
            or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", request.benchmark_id)
            or not isinstance(request.optimizations, tuple) or not 1 <= len(request.optimizations) <= 3
            or any(profile not in ("O0", "O2", "Os") for profile in request.optimizations)
            or len(set(request.optimizations)) != len(request.optimizations)):
        raise ExecutionError("INVALID_REQUEST", "Invalid benchmark or optimization IDs")
    for program in manifest["benchmarks"]:
        if program["id"] == request.benchmark_id:
            return program
    raise ExecutionError("UNKNOWN_BENCHMARK", "Unknown benchmark ID", benchmark_id=request.benchmark_id)


def new_context(repo_root: Path, output_root: Path) -> ExecutionContext:
    if sys.platform != "linux":
        raise ExecutionError("TOOLCHAIN_UNAVAILABLE", "Execution requires Linux or WSL2")
    config, _, _, _ = _load_assets(Path(repo_root).resolve(strict=True))
    started = time.monotonic()
    output = Path(output_root).resolve()
    output.mkdir(parents=True, exist_ok=True)
    workspace = output / ("exec-" + uuid.uuid4().hex)
    workspace.mkdir(mode=0o700)
    return ExecutionContext(workspace, started + config["limits"]["experiment_timeout_s"])


@contextmanager
def experiment_session(repo_root: Path, output_root: Path) -> Iterator[ExecutionContext]:
    """Keep this session open through analysis/reporting to serialize whole experiments."""
    global _ACTIVE_CONTEXT, _OWNER_THREAD
    if sys.platform != "linux":
        raise ExecutionError("TOOLCHAIN_UNAVAILABLE", "Execution requires Linux or WSL2")
    import fcntl
    if not _LOCK.acquire(blocking=False):
        raise ExecutionError("EXPERIMENT_BUSY", "An experiment is already running")
    try:
        output = Path(output_root).resolve()
        output.mkdir(parents=True, exist_ok=True)
        with (output / ".execution.lock").open("a+b") as lockfile:
            try:
                fcntl.flock(lockfile, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ExecutionError("EXPERIMENT_BUSY", "Artifact root is in use") from exc
            try:
                context = new_context(repo_root, output)
                _ACTIVE_CONTEXT, _OWNER_THREAD = context, get_ident()
                yield context
            finally:
                _ACTIVE_CONTEXT, _OWNER_THREAD = None, None
                fcntl.flock(lockfile, fcntl.LOCK_UN)
    finally:
        _LOCK.release()


def _record_process(directory: Path, result: ProcessResult) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "stdout.bin").write_bytes(result.stdout)
    (directory / "stderr.bin").write_bytes(result.stderr)
    atomic_json(directory / "process.json", {
        "argv": list(result.argv), "status": result.status, "exit_code": result.exit_code,
        "wall_time_ms": result.wall_time_ms, "stdout_sha256": sha256(result.stdout),
        "stderr_sha256": sha256(result.stderr), "stdout_bytes": len(result.stdout),
        "stderr_bytes": len(result.stderr),
    })


def _run(runner: ProcessRunner, argv: list[str], directory: Path, timeout: float,
         limit: int, stdin: bytes = b"") -> ProcessResult:
    directory.mkdir(parents=True, exist_ok=True)
    try:
        result = runner.run(argv, cwd=directory, timeout_s=timeout,
                            max_output_bytes=limit, stdin=stdin)
    except ExecutionError as exc:
        if hasattr(exc, "process_result"):
            _record_process(directory, exc.process_result)
        raise
    _record_process(directory, result)
    return result


def _environment(runner: ProcessRunner, workspace: Path, config: dict) -> tuple[dict, dict]:
    tools = {key: shutil.which(name, path=os.defpath) for key, name in config["tools"].items()}
    missing = [config["tools"][key] for key, path in tools.items() if path is None]
    if missing:
        raise ExecutionError("TOOLCHAIN_UNAVAILABLE", "Required tools are missing", missing_tools=missing)
    versions = {}
    limit = config["limits"]["max_output_bytes_per_stream"]
    timeout = config["limits"]["analysis_tool_timeout_s"]

    def probe(name: str, argv: list[str]) -> str:
        result = _run(runner, argv, workspace / "environment" / name, timeout, limit)
        text = (result.stdout + result.stderr).decode("utf-8", errors="replace").strip()
        if result.status != "completed" or result.exit_code != 0 or not text:
            raise ExecutionError("TOOLCHAIN_UNAVAILABLE", "Tool version probe failed", tool=argv[0])
        return text

    for key, executable in tools.items():
        versions[key] = probe(key, [executable, "--version"])
    machine = probe("target", [tools["cc"], "-dumpmachine"])
    if machine != "riscv64-linux-gnu":
        raise ExecutionError("TOOLCHAIN_UNAVAILABLE", "Compiler target mismatch", target=machine)
    probe("gcc_verbose", [tools["cc"], "-v"])
    libc = probe("libc", [tools["cc"], "-print-file-name=libc.a"])
    if not Path(libc).is_file():
        raise ExecutionError("TOOLCHAIN_UNAVAILABLE", "RISC-V static libc is missing")
    cross_libc = probe("cross_libc", ["/usr/bin/dpkg-query", "-W", "-f=${Version}",
                                      "libc6-dev-riscv64-cross"])
    packages = ["gcc-riscv64-linux-gnu", "binutils-riscv64-linux-gnu", "qemu-user",
                "libc6-dev-riscv64-cross", "libc6-riscv64-cross"]
    probe("packages", ["/usr/bin/dpkg-query", "-W", "-f=${Package}=${Version}\n", *packages])
    environment = {
        "os": platform.freedesktop_os_release().get("PRETTY_NAME", platform.system()),
        "kernel": platform.release(), "python_version": platform.python_version(),
        "compiler_version": versions["cc"], "binutils_version": versions["objdump"],
        "qemu_version": versions["qemu"], "qemu_cpu": "rv64",
        "libc_version": "riscv64-cross " + cross_libc,
        "locale": "C",
    }
    atomic_json(workspace / "environment.json", environment)
    return environment, tools


def _verify_elf(path: Path) -> None:
    """Minimal target guard, not SJS's symbols/sections/instruction analyzer."""
    raw = path.read_bytes()
    if len(raw) < 64 or raw[:7] != b"\x7fELF\x02\x01\x01":
        raise ExecutionError("TOOLCHAIN_UNAVAILABLE", "Compiler produced a non-RV64 ELF")
    kind, machine = struct.unpack_from("<HH", raw, 16)
    flags = struct.unpack_from("<I", raw, 48)[0]
    if kind != 2 or machine != 243 or flags & 6 != 4:
        raise ExecutionError("TOOLCHAIN_UNAVAILABLE", "ELF target/type/LP64D ABI mismatch")


def execute(request: ExecutionRequest, *, repo_root: Path,
            context: ExecutionContext) -> ExecutionBundle:
    """Return execution_passed only; caller must still analyze before final passed."""
    if context is not _ACTIVE_CONTEXT or get_ident() != _OWNER_THREAD:
        raise ExecutionError("INVALID_REQUEST", "execute requires an active experiment_session")
    runner = ProcessRunner(context)
    workspace = context.workspace.resolve(strict=True)
    if (workspace / "execution.json").exists() or (workspace / "source").exists():
        raise ExecutionError("INVALID_REQUEST", "Experiment directory cannot be reused")
    try:
        (workspace / ".execution-started").touch(exist_ok=False)
    except FileExistsError as exc:
        raise ExecutionError("INVALID_REQUEST", "Experiment directory cannot be reused") from exc
    try:
        runner.check_budget()
        root = Path(repo_root).resolve(strict=True)
        config, manifest, raw_config, raw_manifest = _load_assets(root)
        program = validate_request(request, manifest)
        source = _asset(root, program["source"]).read_bytes()
        if not 1 <= len(source) <= 1048576:
            raise ExecutionError("INVALID_REQUEST", "Registered source exceeds size limit")
        (workspace / "source").mkdir()
        source_path = workspace / "source" / "main.c"
        source_path.write_bytes(source)
        (workspace / "baseline.json").write_bytes(raw_config)
        (workspace / "manifest.json").write_bytes(raw_manifest)
        records = []
        expected = {}
        for case in program["cases"]:
            data = _asset(root, case["stdin"]).read_bytes()
            oracle = _asset(root, case["stdout"]).read_bytes()
            if max(len(data), len(oracle)) > 1048576:
                raise ExecutionError("INVALID_REQUEST", "Registered fixture exceeds size limit")
            folder = workspace / "inputs" / case["id"]
            folder.mkdir(parents=True)
            inpath, outpath = folder / "stdin.bin", folder / "expected_stdout.bin"
            inpath.write_bytes(data)
            outpath.write_bytes(oracle)
            records.append(InputRecord(case["id"], sha256(data), sha256(oracle), inpath, outpath))
            expected[case["id"]] = (data, oracle)
        atomic_json(workspace / "request.json", asdict(request))
        environment, tools = _environment(runner, workspace, config)
        variants = []
        limits = config["limits"]
        cap = limits["max_output_bytes_per_stream"]
        for profile in request.optimizations:
            runner.check_budget()
            folder = workspace / profile
            folder.mkdir()
            elf = folder / "program.elf"
            argv = [tools["cc"], *config["common_compile_flags"], *config["profiles"][profile],
                    str(source_path), "-o", str(elf)]
            compilation = _run(runner, argv, folder / "compile", limits["compile_timeout_s"], cap)
            run_argv = None
            runs = []
            if compilation.status != "completed":
                state = compilation.status
            elif compilation.exit_code != 0:
                state = "compile_error"
            elif not elf.is_file():
                raise ExecutionError("INTERNAL_ERROR", "Compiler exited without producing ELF")
            else:
                _verify_elf(elf)
                run_argv = (tools["qemu"], "-cpu", config["target"]["qemu_cpu"], str(elf))
                state = "execution_passed"
                for case in program["cases"]:
                    data, oracle = expected[case["id"]]
                    case_folder = folder / "runs" / case["id"]
                    result = _run(runner, list(run_argv), case_folder,
                                  limits["run_timeout_s"], cap, data)
                    if result.status != "completed":
                        case_state = result.status
                    elif result.exit_code != program["expected_exit_code"]:
                        case_state = "runtime_error"
                    elif result.stdout != oracle or result.stderr != program["expected_stderr"].encode():
                        case_state = "wrong_answer"
                    else:
                        case_state = "passed"
                    if state == "execution_passed" and case_state != "passed":
                        state = case_state
                    runs.append(CaseExecution(case["id"], case_state, result,
                                              case_folder / "stdout.bin", case_folder / "stderr.bin"))
            usable_elf = elf if compilation.status == "completed" and compilation.exit_code == 0 else None
            variants.append(VariantExecution(
                profile, state, compilation, run_argv, tuple(runs), usable_elf,
                sha256(usable_elf.read_bytes()) if usable_elf else None,
                folder / "compile" / "stdout.bin", folder / "compile" / "stderr.bin",
            ))
            atomic_json(folder / "execution.json", _plain(asdict(variants[-1])))
        bundle = ExecutionBundle(
            workspace.name, context.created_at,
            workspace, config["baseline_version"], sha256(raw_config), manifest["corpus_version"],
            sha256(raw_manifest), program["id"], program["kernel_symbol"], sha256(source),
            tuple(records), environment, tuple(variants), context.deadline,
        )
        runner.check_budget()
        atomic_json(workspace / "execution.json", _plain(asdict(bundle)))
        return bundle
    except BaseException as exc:
        code = exc.code if isinstance(exc, ExecutionError) else (
            "EXPERIMENT_CANCELLED" if isinstance(exc, KeyboardInterrupt) else "INTERNAL_ERROR")
        atomic_json(workspace / "error.json", {"error": {
            "code": code, "message": str(exc),
            "details": exc.details if isinstance(exc, ExecutionError) else {},
        }})
        raise
