"""Strict RV64GC/LP64D ELF static analysis for ENG-03."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Literal

from ..execution import ProcessRunner
from ..execution_types import ExecutionContext
from ..execution.engine import atomic_json

Status = Literal["passed", "analysis_error"]

class AnalysisError(RuntimeError):
    def __init__(self, code: str, message: str, **details: object):
        super().__init__(message); self.code = code; self.details = details

@dataclass(frozen=True)
class AnalysisResult:
    status: Status
    reason: str | None
    metrics: dict[str, int | None] | None
    kernel_disassembly: str | None
    evidence: dict[str, object]
    def to_dict(self) -> dict[str, object]:
        return {"status": self.status, "reason": self.reason, "metrics": self.metrics,
                "kernel_disassembly": self.kernel_disassembly, "evidence": self.evidence}

@dataclass(frozen=True)
class InstructionRow:
    address: int
    encoding: str
    text: str
    @property
    def width(self) -> int: return len(self.encoding) // 2
    @property
    def is_compressed(self) -> bool:
        return self.width == 2 and (int(self.encoding, 16) & 3) != 3

_SIZE_RE = re.compile(r"^\s*\.text\s+(\d+)\s+", re.MULTILINE)
_SYMBOL_RE = re.compile(r"^\s*\d+:\s+([0-9a-fA-F]+)\s+(\d+)\s+\S+\s+\S+\s+\S+\s+(\d+)\s+(\S+)\s*$", re.MULTILINE)
_ROW_RE = re.compile(r"^\s*([0-9a-fA-F]+):\s+([0-9a-fA-F]{4}|[0-9a-fA-F]{8})\s+(\S[^\n]*)$", re.MULTILINE)
_SECTION_RE = re.compile(r"^\s*\[\s*(\d+)\]\s+(\S+)\s+\S+\s+([0-9a-fA-F]+)\s+([0-9a-fA-F]+)\s+([0-9a-fA-F]+)\s+", re.MULTILINE)

def parse_text_size(text: str) -> int:
    matches = _SIZE_RE.findall(text)
    if len(matches) != 1 or int(matches[0]) <= 0: raise AnalysisError("ANALYSIS_ERROR", "Missing or ambiguous .text")
    return int(matches[0])

def parse_kernel_symbol(text: str, symbol: str = "kernel") -> tuple[int, int, int]:
    matches = [(int(a, 16), int(n), int(s)) for a, n, s, name in _SYMBOL_RE.findall(text) if name == symbol]
    if len(matches) != 1 or matches[0][1] <= 0: raise AnalysisError("ANALYSIS_ERROR", "Missing or ambiguous kernel symbol", symbol=symbol)
    return matches[0]

def parse_instruction_rows(text: str) -> list[InstructionRow]:
    return [InstructionRow(int(a, 16), e.lower(), t.strip()) for a, e, t in _ROW_RE.findall(text)]

def parse_sections(text: str) -> dict[int, tuple[str, int, int, int]]:
    return {int(i): (name, int(addr, 16), int(off, 16), int(size, 16)) for i, name, addr, off, size in _SECTION_RE.findall(text)}

def validate_target_header(text: str) -> None:
    checks = [(r"Class:\s+ELF64", "ELF is not 64-bit"),
              (r"Data:\s+.*little endian", "ELF is not little-endian"),
              (r"Machine:\s+RISC-V", "ELF machine is not RISC-V"),
              (r"Type:\s+EXEC\b", "ELF is not a static executable"),
              (r"Flags:.*double-float ABI", "ELF ABI is not LP64D")]
    for pattern, message in checks:
        if not re.search(pattern, text, re.IGNORECASE | re.DOTALL):
            raise AnalysisError("ANALYSIS_ERROR", message)
    arch_match = re.search(r'Tag_RISCV_arch:\s+"([^"\n]+)"', text, re.IGNORECASE)
    if not arch_match:
        raise AnalysisError("ANALYSIS_ERROR", "Missing RV64GC ISA attributes")
    arch = arch_match.group(1).lower()
    if not arch.startswith("rv64i"):
        raise AnalysisError("ANALYSIS_ERROR", "ELF is not RV64")
    normalized = re.sub(r"\d+p\d+|\d+", "", arch)
    parts = normalized.split("_")
    extensions = set(ch for ch in parts[0][5:] if ch in "mafdc")
    extensions.update(part[0] for part in parts[1:] if part and part[0] in "mafdc")
    if not set("mafdc") <= extensions:
        raise AnalysisError("ANALYSIS_ERROR", "ELF is not RV64GC")
    if re.search(r"\bINTERP\b", text):
        raise AnalysisError("ANALYSIS_ERROR", "ELF is dynamically linked")
def _validate_rows(rows: list[InstructionRow], start: int, length: int, raw: bytes) -> tuple[int, int]:
    if not rows or len(raw) != length: raise AnalysisError("ANALYSIS_ERROR", "Kernel bytes/disassembly are incomplete")
    cursor = start; compressed = 0
    for row in rows:
        if row.address != cursor or row.width not in (2, 4): raise AnalysisError("ANALYSIS_ERROR", "Kernel disassembly has a gap or unsupported width")
        value = int(row.encoding, 16)
        if row.text.startswith((".2byte", ".short", ".word", ".4byte", "unimp", "c.unimp")):
            raise AnalysisError("ANALYSIS_ERROR", "Unknown or pseudo-instruction encoding")
        if row.width == 2 and (value & 3) == 3: raise AnalysisError("ANALYSIS_ERROR", "Invalid compressed encoding")
        if row.width == 4 and ((value & 3) != 3 or (value & 31) == 31): raise AnalysisError("ANALYSIS_ERROR", "Unsupported 32-bit encoding")
        expected = value.to_bytes(row.width, "little")
        if expected != raw[cursor - start:cursor - start + row.width]: raise AnalysisError("ANALYSIS_ERROR", "Disassembly encoding differs from ELF bytes")
        cursor += row.width; compressed += int(row.is_compressed)
    if cursor != start + length: raise AnalysisError("ANALYSIS_ERROR", "Disassembly does not cover kernel symbol range")
    return len(rows), compressed

def analyze_text(header: str, size: str, symbols: str, disassembly: str, elf_file_bytes: int,
                 raw_kernel_bytes: bytes, *, symbol: str = "kernel", elf_sha256: str | None = None,
                 section_name: str = ".text") -> AnalysisResult:
    try:
        validate_target_header(header); text_bytes = parse_text_size(size)
        start, kernel_bytes, _ = parse_kernel_symbol(symbols, symbol); rows = parse_instruction_rows(disassembly)
        if section_name != ".text" or kernel_bytes > text_bytes: raise AnalysisError("ANALYSIS_ERROR", "Kernel is not inside .text")
        count, compressed = _validate_rows(rows, start, kernel_bytes, raw_kernel_bytes)
        metrics = {"elf_file_bytes": elf_file_bytes, "text_section_bytes": text_bytes, "kernel_code_bytes": kernel_bytes,
                   "kernel_static_instruction_count": count, "kernel_compressed_instruction_count": compressed,
                   "dynamic_instruction_count": None, "target_cycles": None}
        evidence = {"symbol": symbol, "kernel_start": start, "kernel_end": start + kernel_bytes,
                    "section_name": section_name, "raw_encoding_verified": True, "known_padding_bytes": 0,
                    "elf_sha256": elf_sha256, "analysis_scope": "kernel_and_text_static_metrics"}
        return AnalysisResult("passed", None, metrics, disassembly, evidence)
    except AnalysisError as exc:
        return AnalysisResult("analysis_error", str(exc), None, disassembly, {"error_code": exc.code, **exc.details})

def _tool(name: str, explicit: str | None = None) -> str:
    path = explicit or shutil.which("riscv64-linux-gnu-" + name, path=os.defpath)
    if not path: raise AnalysisError("TOOLCHAIN_UNAVAILABLE", "Missing analysis tool", tool=name)
    return path

def _run(runner: ProcessRunner, argv: list[str], context: ExecutionContext, timeout_s: float,
         artifact_path: Path | None = None) -> str:
    result = runner.run(argv, cwd=context.workspace, timeout_s=timeout_s, max_output_bytes=1048576)
    if result.status != "completed" or result.exit_code != 0: raise AnalysisError("ANALYSIS_ERROR", "Analysis tool failed", tool=argv[0])
    if artifact_path is not None:
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_bytes(result.stdout)
    return result.stdout.decode("utf-8", errors="strict")

def analyze_elf(elf_path: Path, *, context: ExecutionContext, symbol: str = "kernel",
                tools: dict[str, str] | None = None, timeout_s: float = 5.0) -> AnalysisResult:
    elf = Path(elf_path).resolve(strict=True)
    if not elf.is_file(): raise AnalysisError("INVALID_REQUEST", "ELF path is not a regular file")
    if not elf.is_relative_to(context.workspace.resolve(strict=True)): raise AnalysisError("INVALID_REQUEST", "ELF must be inside experiment workspace")
    m = tools or {}; readelf = _tool("readelf", m.get("readelf")); size = _tool("size", m.get("size")); objdump = _tool("objdump", m.get("objdump"))
    runner = ProcessRunner(context)
    analysis_argv = [
        [readelf, "-h", "-A", "-lW", str(elf)],
        [size, "-A", str(elf)],
        [readelf, "-sW", str(elf)],
        [readelf, "-SW", str(elf)],
        [objdump, "-d", "-M", "no-aliases,numeric", "--disassemble=" + symbol, str(elf)],
    ]
    analysis_dir = elf.parent / "analysis"
    artifact_paths = {
        "header": analysis_dir / "readelf-header.txt",
        "size": analysis_dir / "size.txt",
        "symbols": analysis_dir / "readelf-symbols.txt",
        "sections": analysis_dir / "readelf-sections.txt",
        "disassembly": analysis_dir / "objdump-kernel.txt",
    }
    def run_recorded(argv: list[str], artifact_key: str) -> str:
        try:
            return _run(runner, argv, context, timeout_s, artifact_paths[artifact_key])
        except AnalysisError as error:
            raise AnalysisError(
                error.code, str(error),
                **dict(error.details, analysis_argv=analysis_argv),
            ) from error

    header = run_recorded(analysis_argv[0], "header")
    size_out = run_recorded(analysis_argv[1], "size")
    symbols = run_recorded(analysis_argv[2], "symbols")
    sections_out = run_recorded(analysis_argv[3], "sections")
    disassembly = run_recorded(analysis_argv[4], "disassembly")
    # Persist capture-time hashes even when domain checks below reject the
    # function. Attribution may still establish known bounds for a partial result.
    atomic_json(analysis_dir / "record.json", {
        "elf_sha256": hashlib.sha256(elf.read_bytes()).hexdigest(),
        "analysis_argv": analysis_argv,
        "artifact_sha256": {key: hashlib.sha256(path.read_bytes()).hexdigest()
                            for key, path in artifact_paths.items()},
        "status": "captured",
    })
    sections = parse_sections(sections_out); start, length, section_index = parse_kernel_symbol(symbols, symbol)
    section = sections.get(section_index)
    if not section or section[0] != ".text": raise AnalysisError("ANALYSIS_ERROR", "Kernel symbol is not in .text")
    _, section_addr, section_offset, section_size = section
    if not section_addr <= start or start + length > section_addr + section_size: raise AnalysisError("ANALYSIS_ERROR", "Kernel exceeds .text bounds")
    raw = elf.read_bytes(); file_offset = section_offset + start - section_addr
    if file_offset + length > len(raw): raise AnalysisError("ANALYSIS_ERROR", "Kernel bytes exceed ELF file")
    try:
        result = analyze_text(header, size_out, symbols, disassembly, len(raw), raw[file_offset:file_offset + length],
                             symbol=symbol, elf_sha256=hashlib.sha256(raw).hexdigest(), section_name=section[0])
    except AnalysisError as error:
        raise AnalysisError(error.code, str(error), **dict(error.details, analysis_argv=analysis_argv)) from error
    evidence = dict(result.evidence)
    evidence["analysis_argv"] = analysis_argv
    evidence["analysis_artifacts"] = {
        key: str(path.relative_to(context.workspace)).replace("\\", "/")
        for key, path in artifact_paths.items()
    }
    evidence["analysis_artifact_sha256"] = {
        key: hashlib.sha256(path.read_bytes()).hexdigest()
        for key, path in artifact_paths.items()
    }
    atomic_json(analysis_dir / "record.json", {
        "elf_sha256": hashlib.sha256(raw).hexdigest(),
        "analysis_argv": analysis_argv,
        "artifact_sha256": evidence["analysis_artifact_sha256"],
        "status": result.status,
    })
    return AnalysisResult(result.status, result.reason, result.metrics,
                          result.kernel_disassembly, evidence)
