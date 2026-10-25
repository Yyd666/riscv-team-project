"""Bounded Linux process execution, shared by GCC, QEMU and binutils."""

from __future__ import annotations

import math
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import time

from ..execution_types import ExecutionContext, ExecutionError, ProcessResult


class ProcessRunner:
    def __init__(self, context: ExecutionContext):
        self.context = context

    def run(
        self, argv: list[str] | tuple[str, ...], *, cwd: Path,
        timeout_s: float, max_output_bytes: int, stdin: bytes = b"",
    ) -> ProcessResult:
        if sys.platform != "linux":
            raise ExecutionError("TOOLCHAIN_UNAVAILABLE", "Execution requires Linux or WSL2")
        if not isinstance(argv, (list, tuple)) or not argv or any(
            not isinstance(arg, str) or not arg or "\0" in arg for arg in argv
        ):
            raise ValueError("argv must be a nonempty array of nonempty strings")
        if not math.isfinite(timeout_s) or timeout_s <= 0:
            raise ValueError("timeout_s must be finite and positive")
        if type(max_output_bytes) is not int or max_output_bytes < 1:
            raise ValueError("max_output_bytes must be positive")
        if not isinstance(stdin, bytes):
            raise TypeError("stdin must be bytes")
        workdir = Path(cwd).resolve(strict=True)
        root = self.context.workspace.resolve(strict=True)
        if not workdir.is_dir() or not workdir.is_relative_to(root):
            raise ValueError("Process cwd must be inside the experiment workspace")
        self.check_budget()
        if self.context.cancel.is_set():
            raise ExecutionError("EXPERIMENT_CANCELLED", "Execution was cancelled")
        started = time.monotonic()
        stop_at = min(started + timeout_s, self.context.deadline)
        captured = {"stdout": bytearray(), "stderr": bytearray()}
        status = "completed"
        proc = None
        try:
            proc = subprocess.Popen(
                list(argv), cwd=workdir, stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                shell=False, start_new_session=True,
                env={"PATH": os.defpath, "LC_ALL": "C", "LANG": "C"},
            )
            with selectors.DefaultSelector() as selector:
                for name in ("stdout", "stderr"):
                    stream = getattr(proc, name)
                    os.set_blocking(stream.fileno(), False)
                    selector.register(stream, selectors.EVENT_READ, name)
                remaining_input = memoryview(stdin)
                if remaining_input:
                    os.set_blocking(proc.stdin.fileno(), False)
                    selector.register(proc.stdin, selectors.EVENT_WRITE, "stdin")
                else:
                    proc.stdin.close()
                while selector.get_map() or proc.poll() is None:
                    if self.context.cancel.is_set():
                        status = "cancelled"
                        break
                    now = time.monotonic()
                    if now >= stop_at:
                        status = "timeout"
                        break
                    for key, _ in selector.select(min(0.05, stop_at - now)):
                        stream, name = key.fileobj, key.data
                        if name == "stdin":
                            try:
                                count = os.write(stream.fileno(), remaining_input[:65536])
                                remaining_input = remaining_input[count:]
                            except BrokenPipeError:
                                remaining_input = memoryview(b"")
                            except BlockingIOError:
                                continue
                            if not remaining_input:
                                selector.unregister(stream)
                                stream.close()
                            continue
                        try:
                            chunk = os.read(stream.fileno(), 65536)
                        except BlockingIOError:
                            continue
                        if not chunk:
                            selector.unregister(stream)
                            stream.close()
                            continue
                        room = max_output_bytes - len(captured[name])
                        captured[name].extend(chunk[:room])
                        if len(captured[name]) >= max_output_bytes:
                            status = "output_limit"
                            break
                    if status != "completed":
                        break
        except OSError as exc:
            raise ExecutionError(
                "TOOLCHAIN_UNAVAILABLE", "Could not start or communicate with tool",
                tool=argv[0], reason=str(exc),
            ) from exc
        finally:
            if proc is not None:
                # Kill descendants even when the direct child already exited or closed its pipes.
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                finally:
                    for stream in (proc.stdin, proc.stdout, proc.stderr):
                        if stream is not None and not stream.closed:
                            stream.close()
                    proc.wait()
        elapsed = (time.monotonic() - started) * 1000
        result = ProcessResult(
            tuple(argv), status, proc.returncode if status == "completed" else None,
            bytes(captured["stdout"]), bytes(captured["stderr"]), elapsed,
        )
        if time.monotonic() >= self.context.deadline or status == "cancelled":
            code = "EXPERIMENT_CANCELLED" if status == "cancelled" else "REQUEST_TIMEOUT"
            error = ExecutionError(code, "Execution cancelled" if status == "cancelled"
                                   else "Experiment total budget exhausted")
            error.process_result = result
            raise error
        return result

    def check_budget(self) -> None:
        if time.monotonic() >= self.context.deadline:
            raise ExecutionError("REQUEST_TIMEOUT", "Experiment total budget exhausted")
