"""Independent GNU-binutils reference for integration checks, not product analysis."""

from __future__ import annotations

from pathlib import Path
import re
import shutil
import tempfile
import time

from backend.app.execution import ProcessRunner
from backend.app.execution_types import ExecutionContext


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def instruction_rows(text: str) -> list[tuple[int, str, str]]:
    return [(int(address, 16), encoding.lower(), " ".join(instruction.split()))
            for address, encoding, instruction in re.findall(
                r"^\s*([0-9a-fA-F]+):\s+([0-9a-fA-F]{8}|[0-9a-fA-F]{4})\s+(\S[^\n]*)",
                text, re.MULTILINE)]


def inspect_elf(elf: Path, *, include_boundaries: bool = False) -> tuple[dict, str]:
    """Reject unsupported/ambiguous output instead of manufacturing reference metrics."""
    elf = elf.resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="optipilot-elf-audit-") as directory:
        context = ExecutionContext(Path(directory), time.monotonic() + 120)
        runner = ProcessRunner(context)

        def tool(name: str, *options: str) -> str:
            executable = shutil.which("riscv64-linux-gnu-" + name, path="/usr/bin:/bin")
            require(executable is not None, "Missing independent reference tool: " + name)
            result = runner.run([executable, *options, str(elf)], cwd=context.workspace,
                                timeout_s=5, max_output_bytes=1048576)
            require(result.status == "completed" and result.exit_code == 0,
                    "Independent reference command failed: " + name)
            return result.stdout.decode("utf-8", errors="strict")

        header = tool("readelf", "-h", "-A", "-lW")
        require(bool(re.search(r"Class:\s+ELF64", header))
                and bool(re.search(r"Data:.*little endian", header))
                and bool(re.search(r"Machine:\s+RISC-V", header))
                and bool(re.search(r"Type:\s+EXEC\b", header)), "Reference ELF target/type mismatch")
        require(bool(re.search(r"Flags:.*RVC.*double-float ABI", header)), "Reference ABI mismatch")
        require(not re.search(r"^\s*INTERP\s", header, re.MULTILINE), "Reference ELF is not static")
        arch = re.search(r'Tag_RISCV_arch:\s+"([^"\n]+)"', header)
        require(arch is not None and arch[1].startswith("rv64i")
                and set("mafdc") <= set(re.findall(r"_([mafdc])(?:\d|_)", arch[1])),
                "RV64GC attributes missing or unsupported")

        sizes = tool("size", "-A")
        text_sizes = re.findall(r"^\.text\s+(\d+)\s+", sizes, re.MULTILINE)
        require(len(text_sizes) == 1 and int(text_sizes[0]) > 0, "Ambiguous or missing .text")
        symbols = tool("readelf", "-sW")
        kernels = set((int(address, 16), int(size), int(section))
                      for address, size, section in re.findall(
                          r"^\s*\d+:\s+([0-9a-fA-F]+)\s+(\d+)\s+FUNC\s+\S+\s+\S+\s+(\d+)\s+kernel\s*$",
                          symbols, re.MULTILINE))
        require(len(kernels) == 1, "Ambiguous or missing kernel function")
        start, length, section_index = next(iter(kernels))
        require(length > 0, "Empty kernel function")
        sections = tool("readelf", "-SW")
        section_rows = {int(index): (name, int(address, 16), int(offset, 16), int(size, 16))
                        for index, name, address, offset, size in re.findall(
                            r"^\s*\[\s*(\d+)\]\s+(\S+)\s+\S+\s+([0-9a-fA-F]+)\s+([0-9a-fA-F]+)\s+([0-9a-fA-F]+)\s+",
                            sections, re.MULTILINE)}
        require(section_index in section_rows, "Kernel section missing")
        name, address, offset, size = section_rows[section_index]
        require(name == ".text", "Reference kernel is not in .text")
        require(address <= start and start + length <= address + size, "Kernel crosses section bounds")
        raw = elf.read_bytes()
        file_offset = offset + start - address
        require(file_offset + length <= len(raw), "Kernel bytes outside ELF file")
        kernel_bytes = raw[file_offset:file_offset + length]

        disassembly = tool("objdump", "-d", "-M", "no-aliases,numeric", "--disassemble=kernel")
        rows = instruction_rows(disassembly)
        cursor = start
        compressed = 0
        for instruction_address, encoding, mnemonic in rows:
            width = len(encoding) // 2
            value = int(encoding, 16)
            require(instruction_address == cursor, "Reference disassembly has a gap or overlap")
            require(not mnemonic.startswith((".", "unimp", "c.unimp", "0x")),
                    "Unclassified kernel bytes cannot support complete static metrics")
            require((width == 2 and value & 3 != 3)
                    or (width == 4 and value & 3 == 3 and value & 31 != 31),
                    "Unsupported reference instruction width")
            require(value.to_bytes(width, "little") == kernel_bytes[cursor - start:cursor - start + width],
                    "Disassembly encoding differs from original ELF")
            cursor += width
            compressed += width == 2
        require(bool(rows) and cursor == start + length, "Reference instructions do not cover kernel bytes")
        metrics = {
            "elf_file_bytes": len(raw), "text_section_bytes": int(text_sizes[0]),
            "kernel_code_bytes": length, "kernel_static_instruction_count": len(rows),
            "kernel_compressed_instruction_count": compressed,
            "dynamic_instruction_count": None, "target_cycles": None,
        }
        if include_boundaries:
            metrics.update(kernel_start=start, kernel_end=start + length,
                           section_index=section_index, unclassified_bytes=0)
        return metrics, disassembly
