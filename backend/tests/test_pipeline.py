import unittest
from pathlib import Path

from backend.app.analysis import AnalysisResult
from backend.app.execution_types import (
    CaseExecution, ExecutionBundle, InputRecord, ProcessResult, VariantExecution,
)
from backend.app.pipeline import assemble_result


BASELINE = {
    "profiles": {"O0": ["-O0"], "O2": ["-O2"], "Os": ["-Os"]},
    "selection": {
        "objective": "min_text_section_bytes",
        "require_all_cases_pass": True,
        "tie_break_order": ["O2", "Os", "O0"],
    },
}


def process(argv, stdout=b"", stderr=b"", exit_code=0):
    return ProcessResult(tuple(argv), "completed", exit_code, stdout, stderr, 1.0)


class PipelineTests(unittest.TestCase):
    def bundle(self):
        run = CaseExecution(
            "case-a", "passed", process(["qemu-riscv64", "program.elf"], b"ok\n"),
            Path("stdout.bin"), Path("stderr.bin"),
        )
        variants = (
            VariantExecution(
                "O0", "compile_error", process(["gcc", "-O0"], stderr=b"compile failed", exit_code=1),
                None, (), None, None, Path("compile.stdout"), Path("compile.stderr"),
            ),
            VariantExecution(
                "O2", "execution_passed", process(["gcc", "-O2"]),
                ("qemu-riscv64", "program.elf"), (run,), Path("O2/program.elf"),
                "a" * 64, Path("compile.stdout"), Path("compile.stderr"),
            ),
            VariantExecution(
                "Os", "execution_passed", process(["gcc", "-Os"]),
                ("qemu-riscv64", "program.elf"), (run,), Path("Os/program.elf"),
                "b" * 64, Path("compile.stdout"), Path("compile.stderr"),
            ),
        )
        return ExecutionBundle(
            "exec-test", "2026-10-26T00:00:00Z", Path("workspace"),
            "0.1.0", "c" * 64, "0.1.0", "d" * 64, "sum_u32", "kernel",
            "e" * 64,
            (InputRecord("case-a", "f" * 64, "g" * 64, Path("in"), Path("out")),),
            {
                "os": "Ubuntu", "kernel": "test", "python_version": "3.12",
                "compiler_version": "gcc", "binutils_version": "binutils",
                "qemu_version": "qemu", "qemu_cpu": "rv64",
                "libc_version": "libc", "locale": "C",
            },
            variants, 999.0,
        )

    def test_assembles_schema_shape_and_static_selection(self):
        result = assemble_result(self.bundle(), {
            "O2": AnalysisResult(
                "passed", None,
                {
                    "elf_file_bytes": 1000, "text_section_bytes": 80,
                    "kernel_code_bytes": 20,
                    "kernel_static_instruction_count": 5,
                    "kernel_compressed_instruction_count": 2,
                    "dynamic_instruction_count": None, "target_cycles": None,
                },
                "1000: instruction",
                {"analysis_argv": [["readelf", "-h"]]},
            ),
            "Os": AnalysisResult(
                "passed", None,
                {
                    "elf_file_bytes": 900, "text_section_bytes": 100,
                    "kernel_code_bytes": 20,
                    "kernel_static_instruction_count": 5,
                    "kernel_compressed_instruction_count": 2,
                    "dynamic_instruction_count": None, "target_cycles": None,
                },
                "1000: instruction",
                {"analysis_argv": [["readelf", "-h"]]},
            ),
        }, baseline_policy=BASELINE)
        self.assertFalse(result["is_mock"])
        self.assertEqual(result["selection"]["optimization"], "O2")
        self.assertEqual(result["variants"][0]["status"], "compile_error")
        self.assertIsNone(result["variants"][0]["metrics"])
        self.assertEqual(result["variants"][1]["analysis_argv"], [["readelf", "-h"]])
        self.assertEqual(result["variants"][2]["status"], "passed")

    def test_policy_drift_is_rejected(self):
        with self.assertRaises(ValueError):
            assemble_result(self.bundle(), {}, baseline_policy={
                **BASELINE,
                "selection": {**BASELINE["selection"], "tie_break_order": ["Os", "O2", "O0"]},
            })


if __name__ == "__main__":
    unittest.main()
