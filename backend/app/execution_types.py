"""Internal execution boundary. No static analysis or final experiment status."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import Event
from typing import Literal

Profile = Literal["O0", "O2", "Os"]
ProcessStatus = Literal["completed", "timeout", "output_limit", "cancelled"]
CaseStatus = Literal["passed", "runtime_error", "wrong_answer", "timeout", "output_limit"]
ExecutionStatus = Literal[
    "execution_passed", "compile_error", "runtime_error", "wrong_answer", "timeout", "output_limit"
]


class ExecutionError(Exception):
    """Infrastructure/request failure, distinct from a benchmark failure."""

    def __init__(self, code: str, message: str, **details: object):
        super().__init__(message)
        self.code = code
        self.details = details


@dataclass(frozen=True)
class ExecutionRequest:
    benchmark_id: str
    optimizations: tuple[Profile, ...]


@dataclass(frozen=True)
class ProcessResult:
    argv: tuple[str, ...]
    status: ProcessStatus
    exit_code: int | None
    stdout: bytes
    stderr: bytes
    wall_time_ms: float


@dataclass(frozen=True)
class InputRecord:
    case_id: str
    stdin_sha256: str
    expected_stdout_sha256: str
    stdin_path: Path
    expected_stdout_path: Path


@dataclass(frozen=True)
class CaseExecution:
    case_id: str
    status: CaseStatus
    process: ProcessResult
    stdout_path: Path
    stderr_path: Path


@dataclass(frozen=True)
class VariantExecution:
    optimization: Profile
    status: ExecutionStatus
    compilation: ProcessResult
    run_argv: tuple[str, ...] | None
    runs: tuple[CaseExecution, ...]
    elf_path: Path | None
    elf_sha256: str | None
    compile_stdout_path: Path
    compile_stderr_path: Path


@dataclass(frozen=True)
class ExecutionBundle:
    experiment_id: str
    created_at: str
    workspace: Path
    baseline_version: str
    baseline_config_sha256: str
    corpus_version: str
    manifest_sha256: str
    benchmark_id: str
    kernel_symbol: str
    source_sha256: str
    inputs: tuple[InputRecord, ...]
    environment: dict[str, str]
    variants: tuple[VariantExecution, ...]
    # Shared with subsequent analysis: use this absolute monotonic deadline.
    deadline: float
    is_mock: Literal[False] = False


@dataclass(frozen=True)
class ExecutionContext:
    """Reuse the same context/deadline across execution, analysis and saving."""

    workspace: Path
    deadline: float
    cancel: Event = field(default_factory=Event)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
