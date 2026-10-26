import io
import json
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from backend.app.execution_types import ExecutionError
from optipilot.cli import main

ROOT = Path(__file__).resolve().parents[2]
BASELINE = {
    "profiles": {"O0": ["-O0"], "O2": ["-O2"], "Os": ["-Os"]},
    "selection": {
        "objective": "min_text_section_bytes",
        "require_all_cases_pass": True,
        "tie_break_order": ["O2", "Os", "O0"],
    },
}


class CliTests(unittest.TestCase):
    def test_python_module_help_is_runnable(self):
        result = subprocess.run(
            [sys.executable, "-m", "optipilot", "--help"],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("run", result.stdout)
        self.assertNotIn("SyntaxError", result.stderr)

    def test_run_dispatches_to_real_pipeline_and_prints_result(self):
        document = {"is_mock": False, "selection": None, "variants": []}
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch("optipilot.cli.load_baseline", return_value=BASELINE),              patch("optipilot.cli.run_experiment", return_value=(document, Path("result.json"), 0)) as run:
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = main([
                    "run", "--benchmark", "sum_u32",
                    "--optimizations", "O0", "O2", "--output", "artifacts",
                ])
        self.assertEqual(code, 0)
        run.assert_called_once()
        self.assertEqual(json.loads(stdout.getvalue()), document)
        self.assertIn("result_path=result.json", stderr.getvalue())

    def test_missing_linux_toolchain_returns_five(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch("optipilot.cli.load_baseline", return_value=BASELINE),              patch("optipilot.cli.run_experiment", side_effect=ExecutionError(
                 "TOOLCHAIN_UNAVAILABLE", "Linux/RISC-V tools are unavailable")):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = main([
                    "run", "--benchmark", "sum_u32",
                    "--optimizations", "O2", "--output", "artifacts",
                ])
        self.assertEqual(code, 5)
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(json.loads(stderr.getvalue())["error"]["code"],
                         "TOOLCHAIN_UNAVAILABLE")


    def test_report_command_writes_markdown_without_execution(self):
        import json
        import tempfile

        document = {
            "schema_version": "0.1.0",
            "experiment_id": "cli-report",
            "is_mock": True,
            "created_at": "2026-10-26T00:00:00Z",
            "baseline_version": "0.1.0",
            "baseline_config_sha256": "a" * 64,
            "corpus_version": "0.1.0",
            "benchmark_id": "sum_u32",
            "source_sha256": "b" * 64,
            "inputs": [{"case_id": "empty", "stdin_sha256": "c" * 64,
                        "expected_stdout_sha256": "d" * 64}],
            "environment": {\n                "os": "mock", "kernel": "mock", "python_version": "3.12",\n                "compiler_version": "mock", "binutils_version": "mock",\n                "qemu_version": "mock", "qemu_cpu": "rv64",\n                "libc_version": "mock", "locale": "C",\n            },
            "variants": [{
                "optimization": "O2", "status": "analysis_error",
                "compile_argv": ["gcc"], "run_argv": None, "analysis_argv": [],
                "diagnostics": "failed", "kernel_disassembly": None,
                "metrics": None, "runs": [],
            }],
            "selection": None,
        }
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "result.json"
            target = Path(folder) / "report.md"
            source.write_text(json.dumps(document), encoding="utf-8")
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                code = main(["report", "--experiment", str(source), "--output", str(target)])
            self.assertEqual(code, 0)
            self.assertTrue(target.is_file())
            self.assertIn("report_path=", stderr.getvalue())



if __name__ == "__main__":
    unittest.main()
