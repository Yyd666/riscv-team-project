import json
from pathlib import Path
import tempfile
import unittest

from backend.app.reporting import ReportInputError, load_result, render_report, write_report


def document():
    return {
        "schema_version": "0.1.0",
        "experiment_id": "exec-report-test",
        "is_mock": False,
        "created_at": "2026-10-26T00:00:00Z",
        "baseline_version": "0.1.0",
        "baseline_config_sha256": "a" * 64,
        "corpus_version": "0.1.0",
        "benchmark_id": "sum_u32",
        "source_sha256": "b" * 64,
        "inputs": [{"case_id": "empty", "stdin_sha256": "c" * 64,
                    "expected_stdout_sha256": "d" * 64}],
        "environment": {"os": "test", "kernel": "test", "python_version": "3.12",\n                       "compiler_version": "gcc", "binutils_version": "binutils",\n                       "qemu_version": "qemu", "qemu_cpu": "rv64",\n                       "libc_version": "libc", "locale": "C"},
        "variants": [
            {
                "optimization": "O2", "status": "passed",
                "compile_argv": ["gcc", "-O2"], "run_argv": ["qemu-riscv64"],
                "analysis_argv": [["readelf", "-h"]],
                "diagnostics": "compile_status=completed compile_exit_code=0",
                "kernel_disassembly": "1000: instruction",
                "metrics": {
                    "elf_file_bytes": 1000, "text_section_bytes": 80, "kernel_code_bytes": 20,
                    "kernel_static_instruction_count": 5,
                    "kernel_compressed_instruction_count": 2,\n                    "dynamic_instruction_count": None, "target_cycles": None,
                },
                "runs": [{"case_id": "empty", "status": "passed",
                          "exit_code": 0, "stdout": "0\n", "stderr": "",
                          "wall_time_ms": 1.0}],
            },
            {
                "optimization": "Os", "status": "analysis_error",
                "compile_argv": ["gcc", "-Os"], "run_argv": None,
                "analysis_argv": [["readelf", "-h"]],
                "diagnostics": "analysis failed", "kernel_disassembly": None,
                "metrics": None, "runs": [],
            },
        ],
        "selection": {
            "objective": "min_text_section_bytes",
            "optimization": "O2",
            "evidence": "static_size_only",
        },
    }


class ReportingTests(unittest.TestCase):
    def test_render_contains_provenance_selection_diagnostics_and_limits(self):
        output = render_report(document())
        self.assertIn("真实实验记录", output)
        self.assertIn("O2", output)
        self.assertIn("analysis failed", output)
        self.assertIn("wall_time_ms", output)
        self.assertIn("R001/R002", output)

    def test_write_report_is_readable_and_atomic_target_is_used(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "result.json"
            target = Path(folder) / "nested" / "report.md"
            source.write_text(json.dumps(document()), encoding="utf-8")
            report = write_report(load_result(source), target, source_path=source)
            self.assertEqual(report, target.resolve())
            self.assertIn("OptiPilot 实验报告", target.read_text(encoding="utf-8"))
            self.assertFalse(list(target.parent.glob(".report-*")))

    def test_invalid_result_is_rejected(self):
        bad = document()
        del bad["selection"]
        with self.assertRaises(ReportInputError):
            render_report(bad)

    def test_same_input_output_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "result.json"
            source.write_text(json.dumps(document()), encoding="utf-8")
            with self.assertRaises(ReportInputError):
                write_report(load_result(source), source, source_path=source)


if __name__ == "__main__":
    unittest.main()
