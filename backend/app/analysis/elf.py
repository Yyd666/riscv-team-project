"""Independent RV64GC ELF static analysis for the ENG-03 boundary."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Literal

Status = Literal["passed", "analysis_error"]


class AnalysisError(RuntimeError):
    def __init__(self, code: str, message: str, **details: object):
        super().__init__(message)
        self.code = code
        self.details = details


@dataclass(frozen=True)
class AnalysisResult:
    status: Status
    reason: str | None
    metrics: dict[str, int | None] | None
    kernel_disassembly: str | None
    evidence: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "reason": self.reason,
            "metrics": self.metrics,
            "kernel_disassembly": self.kernel_disassembly,
            "evidence": self.evidence,
        }


@dataclass(frozen=True)
class InstructionRow:
    address: int
    encoding: str
    text: str

    @property
    def width(self) -> int:
        return len(self.encoding) // 2

    @property
    def is_compressed(self) -> bool:
        return self.width == 2 and (int(self.encoding, 16) & 3) != 3


_SIZE_RE = re.compile(r"^\s*\.text\s+(\d+)\s+", re.MULTILINE)
_SYMBOL_RE = re.compile(
    r"^\s*\d+:\s+([0-9a-fA-F]+)\s+(\d+)\s+\S+\s+\S+\s+\S+\s+(\d+)\s+(\S+)\s*$",
    re.MULTILINE,
)
_INSTRUCTION_RE = re.compile(
    r"^\s*([0-9a-fA-F]+):\s+([0-9a-fA-F]{4}|[0-9a-fA-F]{8})\s+(\S[^\n]*)$",
    re.MULTILINE,
)


def parse_text_size(size_output: str) -> int:
    matches = _SIZE_RE.findall(size_output)
    if len(matches) != 1 or int(matches[0]) <= 0:
        raise AnalysisError("ANALYSIS_ERROR", "Missing or ambiguous .text section")
    return int(matches[0])


def parse_kernel_symbol(symbol_output: str, symbol: str = "kernel") -> tuple[int, int, int]:
    matches = [(int(address, 16), int(length), int(section), name)
               for address, length, section, name in _SYMBOL_RE.findall(symbol_output)
               if name == symbol]
    if len(matches) != 1 or matches[0][1] <= 0:
        raise AnalysisError("ANALYSIS_ERROR", "Missing or ambiguous kernel symbol", symbol=symbol)
    address, length, section, _ = matches[0]
    return address, length, section


def parse_instruction_rows(disassembly: str) -> list[InstructionRow]:
    return [InstructionRow(int(address, 16), encoding.lower(), text.strip())
            for address, encoding, text in _INSTRUCTION_RE.findall(disassembly)]


def validate_target_header(header_output: str) -> None:
    required = (
        (r"Class:\s+ELF64", "ELF is not 64-bit"),
        (r"Data:\s+.*little endian", "ELF is not little-endian"),
        (r"Machine:\s+RISC-V", "ELF machine is not RISC-V"),
    )
    for pattern, message in required:
        if not re.search(pattern, header_output, re.IGNORECASE):
            raise AnalysisError("ANALYSIS_ERROR", message)
    arch = re.search(r'Tag_RISCV_arch:\s+"([^"\n]+)"', header_output)
    if arch and not arch.group(1).lower().startswith("rv64i"):
        raise AnalysisError("ANALYSIS_ERROR", "ELF ISA is not RV64")


def _validate_instruction_span(rows: list[InstructionRow], start: int, length: int) -> tuple[int, int]:
    if not rows:
        raise AnalysisError("ANALYSIS_ERROR", "Kernel disassembly contains no instructions")
    cursor = start
    compressed = 0
    for row in rows:
        if row.address != cursor:
            raise AnalysisError("ANALYSIS_ERROR", "Kernel disassembly has a gap or overlap")
        if row.width not in (2, 4):
            raise AnalysisError("ANALYSIS_ERROR", "Unsupported instruction width")
        value = int(row.encoding, 16)
        if row.width == 2 and (value & 3) == 3:
            raise AnalysisError("ANALYSIS_ERROR", "Invalid compressed instruction encoding")
        if row.width == 4 and ((value & 3) != 3 or (value & 31) == 31):
            raise AnalysisError("ANALYSIS_ERROR", "Unsupported 32-bit instruction encoding")
        cursor += row.width
        compressed += int(row.is_compressed)
    if cursor != start + length:
        raise AnalysisError("ANALYSIS_ERROR", "Disassembly does not cover kernel symbol range")
    return len(rows), compressed


def analyze_text(header_output: str, size_output: str, symbol_output: str,
                 disassembly: str, elf_file_bytes: int, *, symbol: str = "kernel",
                 elf_sha256: str | None = None) -> AnalysisResult:
    try:
        validate_target_header(header_output)
        text_bytes = parse_text_size(size_output)
        start, kernel_bytes, _section = parse_kernel_symbol(symbol_output, symbol)
        rows = parse_instruction_rows(disassembly)
        instruction_count, compressed_count = _validate_instruction_span(rows, start, kernel_bytes)
        if kernel_bytes > text_bytes:
            raise AnalysisError("ANALYSIS_ERROR", "Kernel exceeds .text section")
        metrics = {
            "elf_file_bytes": elf_file_bytes,
            "text_section_bytes": text_bytes,
            "kernel_code_bytes": kernel_bytes,
            "kernel_static_instruction_count": instruction_count,
            "kernel_compressed_instruction_count": compressed_count,
            "dynamic_instruction_count": None,
            "target_cycles": None,
        }
        evidence = {
            "symbol": symbol,
            "kernel_start": start,
            "kernel_end": start + kernel_bytes,
            "known_padding_bytes": 0,
            "elf_sha256": elf_sha256,
            "analysis_scope": "kernel_and_text_static_metrics",
        }
        return AnalysisResult("passed", None, metrics, disassembly, evidence)
    except AnalysisError as exc:
        return AnalysisResult("analysis_error", str(exc), None, disassembly,
                              {"analysis_scope": "kernel_and_text_static_metrics",
                               "error_code": exc.code, **exc.details})


def _tool(name: str, explicit: str | None = None) -> str:
    if explicit:
        return explicit
    path = shutil.which("riscv64-linux-gnu-" + name, path=os.defpath)
    if path is None:
        raise AnalysisError("TOOLCHAIN_UNAVAILABLE", "Missing analysis tool", tool=name)
    return path


def _run(argv: list[str], *, timeout_s: float = 5.0) -> str:
    try:
        completed = subprocess.run(
            argv, shell=False, check=False, capture_output=True, timeout=timeout_s,
            env={"PATH": os.defpath, "LC_ALL": "C", "LANG": "C"},
        )
    except FileNotFoundError as exc:
        raise AnalysisError("TOOLCHAIN_UNAVAILABLE", "Analysis tool could not start", tool=argv[0]) from exc
    except subprocess.TimeoutExpired as exc:
        raise AnalysisError("ANALYSIS_ERROR", "Analysis tool timed out", tool=argv[0]) from exc
    if completed.returncode != 0:
        raise AnalysisError("ANALYSIS_ERROR", "Analysis tool failed", tool=argv[0],
                            exit_code=completed.returncode)
    return completed.stdout.decode("utf-8", errors="strict")


def analyze_elf(elf_path: Path, *, symbol: str = "kernel",
                tools: dict[str, str] | None = None, timeout_s: float = 5.0) -> AnalysisResult:
    elf = Path(elf_path).resolve(strict=True)
    if not elf.is_file():
        raise AnalysisError("INVALID_REQUEST", "ELF path is not a regular file")
    tool_map = tools or {}
    readelf = _tool("readelf", tool_map.get("readelf"))
    size = _tool("size", tool_map.get("size"))
    objdump = _tool("objdump", tool_map.get("objdump"))
    header = _run([readelf, "-h", "-A" , str(elf)], timeout_s=timeout_s)
    size_output = _run([size, "-A", str(elf)], timeout_s=timeout_s)
    symbols = _run([readelf, "-sW", str(elf)], timeout_s=timeout_s)
    disassembly = _run([objdump, "-d", "-M", "no-aliases,numeric",
                        "--disassemble=" + symbol, str(elf)], timeout_s=timeout_s)
    return analyze_text(header, size_output, symbols, disassembly,
                        elf.stat().st_size, symbol=symbol,
                        elf_sha256=hashlib.sha256(elf.read_bytes()).hexdigest())