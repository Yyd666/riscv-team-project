import unittest
from backend.app.analysis.elf import AnalysisError, analyze_text, parse_instruction_rows, parse_kernel_symbol, parse_text_size, validate_target_header

HEADER = '''
Class: ELF64
Data: 2's complement, little endian
Machine: RISC-V
Type: EXEC
Flags: RVC, double-float ABI
Tag_RISCV_arch: "rv64i2p1_m2p0_a2p1_f2p2_d2p2_c2p0_zicsr2p0"
'''
SIZE = '.text 8 0x1000\n'
SYMBOLS = '12: 0000000000001000     4 FUNC    GLOBAL DEFAULT   1 kernel\n'
DISASSEMBLY = '1000: 1141 c.addi16sp -16\n1002: 8082 c.jr ra\n'
RAW = bytes.fromhex('41118280')

class AnalysisTests(unittest.TestCase):
    def test_metrics_and_raw_encoding(self):
        self.assertEqual(parse_text_size(SIZE), 8); self.assertEqual(parse_kernel_symbol(SYMBOLS), (0x1000, 4, 1))
        self.assertEqual([(r.address, r.width, r.is_compressed) for r in parse_instruction_rows(DISASSEMBLY)], [(0x1000, 2, True), (0x1002, 2, True)])
        result = analyze_text(HEADER, SIZE, SYMBOLS, DISASSEMBLY, 4096, RAW, elf_sha256='a'*64)
        self.assertEqual(result.status, 'passed'); self.assertEqual(result.metrics['kernel_code_bytes'], 4)
    def test_pseudo_instruction_is_rejected(self):
        bad = DISASSEMBLY.replace('c.addi16sp -16', '.2byte 0x0000')
        self.assertEqual(analyze_text(HEADER, SIZE, SYMBOLS, bad, 4096, RAW).status, 'analysis_error')

    def test_bad_raw_bytes_rejected(self):
        result = analyze_text(HEADER, SIZE, SYMBOLS, DISASSEMBLY, 4096, b'\x00'*4)
        self.assertEqual(result.status, 'analysis_error')
    def test_bad_header_rejected(self):
        with self.assertRaises(AnalysisError): validate_target_header(HEADER.replace('RISC-V', 'x86-64'))
    def test_missing_symbol_and_gap_rejected(self):
        self.assertEqual(analyze_text(HEADER, SIZE, SYMBOLS.replace('kernel','other'), DISASSEMBLY, 4096, RAW).status, 'analysis_error')
        self.assertEqual(analyze_text(HEADER, SIZE, SYMBOLS, DISASSEMBLY.replace('1002:', '1004:'), 4096, RAW).status, 'analysis_error')
    def test_non_text_rejected(self):
        self.assertEqual(analyze_text(HEADER, SIZE, SYMBOLS, DISASSEMBLY, 4096, RAW, section_name='.init').status, 'analysis_error')
    def test_isa_abi_static_checks(self):
        for bad in (HEADER.replace('rv64i2p1_m2p0_a2p1_f2p2_d2p2_c2p0', 'rv64i2p1_m2p0'), HEADER.replace('double-float ABI','single-float ABI'), HEADER.replace('Type: EXEC','Type: DYN'), HEADER + '\n INTERP'):

            self.assertEqual(analyze_text(bad, SIZE, SYMBOLS, DISASSEMBLY, 4096, RAW).status, 'analysis_error')

if __name__ == '__main__': unittest.main()