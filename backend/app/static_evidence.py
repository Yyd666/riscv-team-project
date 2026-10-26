"""Read ELF boundaries and reconcile archived GNU evidence without running tools.

The ELF is authoritative. A filename, reported metric, or internally consistent
equation is never sufficient evidence for a verified attribution rule.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import struct


class EvidenceError(ValueError):
    """Missing, unsupported, or contradictory static evidence."""


@dataclass(frozen=True)
class ElfView:
    raw: bytes
    text_bytes: int
    start: int
    length: int
    section_index: int
    section_name: str
    section_address: int
    section_offset: int
    section_size: int
    file_offset: int
    inside_text: bool


def read_elf(path: Path) -> ElfView:
    raw = path.read_bytes()

    def unpack(fmt: str, offset: int):
        size = struct.calcsize(fmt)
        if offset < 0 or offset + size > len(raw):
            raise EvidenceError("ELF table exceeds file bounds")
        return struct.unpack_from(fmt, raw, offset)

    if raw[:7] != b"\x7fELF\x02\x01\x01":
        raise EvidenceError("Expected little-endian ELF64")
    header = unpack("<HHIQQQIHHHHHH", 16)
    kind, machine, version, _, phoff, shoff, flags, ehsize, phsize, phnum, shsize, shnum, names_index = header
    if (kind, machine, version, ehsize, shsize) != (2, 243, 1, 64, 64):
        raise EvidenceError("Expected a RISC-V executable with standard ELF64 tables")
    if flags & 7 != 5 or not shnum or names_index >= shnum:
        raise EvidenceError("Unsupported ABI, RVC flag, or extended section numbering")
    if phnum and phsize != 56:
        raise EvidenceError("Unsupported ELF program-header layout")
    for index in range(phnum):
        if unpack("<I", phoff + index * phsize)[0] == 3:
            raise EvidenceError("Dynamically linked ELF is outside the baseline")
    sections = [unpack("<IIQQQQIIQQ", shoff + index * shsize) for index in range(shnum)]

    def content(section):
        offset, size = section[4:6]
        if section[1] == 8 or offset + size > len(raw):
            raise EvidenceError("Section is not backed by complete ELF bytes")
        return raw[offset:offset + size]

    def cstring(data: bytes, offset: int) -> str:
        end = data.find(b"\0", offset)
        if offset < 0 or end < offset:
            raise EvidenceError("Invalid ELF string table")
        try:
            return data[offset:end].decode("ascii")
        except UnicodeDecodeError as error:
            raise EvidenceError("Non-ASCII ELF name") from error

    names = content(sections[names_index])
    named = [(cstring(names, section[0]), section) for section in sections]
    text = [section for name, section in named if name == ".text"]
    if len(text) != 1 or text[0][5] <= 0 or text[0][2] & 6 != 6:
        raise EvidenceError("Missing, ambiguous, or non-executable .text section")
    content(text[0])
    attributes = [content(section) for name, section in named if name == ".riscv.attributes"]
    architectures = set(re.findall(rb"rv64[a-z0-9_]+(?=\0)", b"".join(attributes)))
    if len(architectures) != 1:
        raise EvidenceError("Missing or ambiguous RISC-V ISA attributes")
    arch = next(iter(architectures)).decode("ascii")
    normalized = re.sub(r"\d+p\d+|\d+", "", arch)
    extensions = set(normalized.split("_")[0][2:]) | set(normalized.split("_")[1:])
    if not arch.startswith("rv64i") or not set("imafdc") <= extensions:
        raise EvidenceError("ELF ISA attributes do not establish RV64GC")
    functions = set()
    for _, table in named:
        if table[1] != 2:  # Require the full symbol table, not a dynsym guess.
            continue
        if table[9] != 24 or table[5] % 24 or table[6] >= shnum:
            raise EvidenceError("Invalid ELF symbol table")
        strings = content(sections[table[6]])
        table_data = content(table)
        for offset in range(0, len(table_data), 24):
            name, info, _, section_index, address, length = struct.unpack_from("<IBBHQQ", table_data, offset)
            if cstring(strings, name) == "kernel":
                if info & 15 != 2:
                    raise EvidenceError("kernel symbol is not a function")
                functions.add((address, length, section_index))
    if len(functions) != 1:
        raise EvidenceError("Missing or ambiguous kernel function")
    start, length, index = next(iter(functions))
    if not length or not 0 < index < shnum:
        raise EvidenceError("Invalid kernel bounds or section index")
    section = sections[index]
    name = named[index][0]
    address, offset, size = section[3:6]
    if section[2] & 6 != 6 or not address <= start < start + length <= address + size:
        raise EvidenceError("kernel bounds exceed its executable section")
    content(section)
    return ElfView(raw, text[0][5], start, length, index, name, address, offset, size,
                   offset + start - address, section == text[0])


def check_symbol_table(text: str, view: ElfView) -> None:
    matches = set((int(address, 16), int(size), int(index))
                  for address, size, index in re.findall(
                      r"^\s*\d+:\s+([\da-fA-F]+)\s+(\d+)\s+FUNC\s+\S+\s+\S+\s+(\d+)\s+kernel\s*$",
                      text, re.MULTILINE))
    if matches != {(view.start, view.length, view.section_index)}:
        raise EvidenceError("Archived symbol table conflicts with ELF kernel bounds")


def check_section_table(text: str, view: ElfView) -> None:
    rows = [(int(index), name, int(address, 16), int(offset, 16), int(size, 16))
            for index, name, address, offset, size in re.findall(
                r"^\s*\[\s*(\d+)\]\s+(\S+)\s+\S+\s+([\da-fA-F]+)\s+([\da-fA-F]+)\s+([\da-fA-F]+)\s+",
                text, re.MULTILINE)]
    own = [row for row in rows if row[0] == view.section_index]
    texts = [row for row in rows if row[1] == ".text"]
    if own != [(view.section_index, view.section_name, view.section_address, view.section_offset, view.section_size)]:
        raise EvidenceError("Archived section table conflicts with kernel's ELF section")
    if len(texts) != 1 or texts[0][4] != view.text_bytes:
        raise EvidenceError("Archived .text section conflicts with ELF")


def count_encodings(text: str, view: ElfView) -> tuple[int, int, int]:
    """Count only recognized, byte-matched rows; gaps and pseudo-ops remain U."""
    rows = re.findall(r"^\s*([\da-fA-F]+):\s+([\da-fA-F]+)\s+(\S[^\n]*)$", text, re.MULTILINE)
    end = view.start + view.length
    cursor = view.start
    n16 = n32 = 0
    for address_text, encoding, instruction in rows:
        address = int(address_text, 16)
        width = len(encoding) // 2
        if len(encoding) % 2 or width not in (1, 2, 4, 6, 8):
            raise EvidenceError("Unsupported archived encoding row")
        if not cursor <= address < address + width <= end:
            raise EvidenceError("Disassembly overlaps or exceeds ELF kernel bounds")
        value = int(encoding, 16)
        offset = view.file_offset + address - view.start
        if value.to_bytes(width, "little") != view.raw[offset:offset + width]:
            raise EvidenceError("Archived disassembly encoding conflicts with ELF bytes")
        mnemonic = instruction.split()[0]
        known = not mnemonic.startswith((".", "unimp", "c.unimp", "0x"))
        if known and width == 2 and value & 3 != 3:
            n16 += 1
        elif known and width == 4 and value & 3 == 3 and value & 31 != 31:
            n32 += 1
        cursor = address + width
    return n16, n32, view.length - 2 * n16 - 4 * n32
