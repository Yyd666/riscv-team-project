import unittest

from backend.app.analysis.elf import (
    AnalysisError, analyze_text, parse_instruction_rows, parse_kernel_symbol,
    parse_text_size, validate_target_header,
)


HEADER = """
ELF Header:
  Class:                             ELF64
  Data:                              2's complement, little endian
  Machine:                           RISC-V
Attribute:
  Tag_RISCV_arch: "rv64imafdc"
"""
SIZE = """
section              size      addr
.text                 8   0x0000000000001000
"""
SYMBOLS = """
   12: 0000000000001000     8 FUNC    GLOBAL DEFAULT   1 kernel
"""
DISASSEMBLY = """
0000000000001000 <kernel>:
    1000: 1141 c.addi16sp -16
    1002: 8082 c.jr ra
"""


class AnalysisTests(unittest.TestCase):
    def test_parsers_and_metrics(self):
        self.assertEqual(parse_text_size(SIZE), 8)
        self.assertEqual(parse_kernel_symbol(SYMBOLS), (0x1000, 8, 1))
        rows = parse_instruction_rows(DISASSEMBLY)
        self.assertEqual([(row.address, row.width, row.is_compressed) for row in rows],
                         [(0x1000, 2, True), (0x1002, 2, True)])
        result = analyze_text(HEADER, SIZE, SYMBOLS, DISASSEMBLY, 4096, elf_sha256="a" * 64)
        self.assertEqual(result.status, "passed")
        self.assertEqual(result.metrics["text_section_bytes"], 8)
        self.assertEqual(result.metrics["kernel_static_instruction_count"], 2)
        self.assertEqual(result.metrics["kernel_compressed_instruction_count"], 2)
        self.assertEqual(result.evidence["known_padding_bytes"], 0)

    def test_header_rejects_non_riscv(self):
        with self.assertRaises(AnalysisError):
            validate_target_header(HEADER.replace("RISC-V", "x86-64"))

    def test_unknown_symbol_is_refused(self):
        result = analyze_text(HEADER, SIZE, SYMBOLS.replace("kernel", "other"),
                              DISASSEMBLY, 4096)
        self.assertEqual(result.status, "analysis_error")
        self.assertEqual(result.metrics, None)

    def test_gap_is_refused(self):
        bad = DISASSEMBLY.replace("1002:", "1004:")
        result = analyze_text(HEADER, SIZE, SYMBOLS, bad, 4096)
        self.assertEqual(result.status, "analysis_error")

    def test_unknown_encoding_is_refused(self):
        bad = DISASSEMBLY.replace("1141 c.addi16sp -16", "ffff .word 0xffff")
        result = analyze_text(HEADER, SIZE, SYMBOLS, bad, 4096)
        self.assertEqual(result.status, "analysis_error")

    def test_kernel_cannot_exceed_text(self):
        result = analyze_text(HEADER, SIZE.replace(" 8 ", " 4 "), SYMBOLS,
                              DISASSEMBLY, 4096)
        self.assertEqual(result.status, "analysis_error")

    def test_invalid_encoding_width_is_refused(self):
        bad = DISASSEMBLY.replace("1141", "00000000")
        result = analyze_text(HEADER, SIZE, SYMBOLS, bad, 4096)
        self.assertEqual(result.status, "analysis_error")

if __name__ == "__main__":
    unittest.main()