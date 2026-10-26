"""The negative-test harness must fail on infrastructure or fixture failures."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend.app.execution_types import ExecutionError
from scripts.run_attribution_negatives import CASES, assess, run_suite


class NegativeGateTests(unittest.TestCase):
    def test_tool_failure_never_counts_as_valid_domain_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "summary.json"
            with patch("scripts.run_attribution_negatives.run_experiment", side_effect=ExecutionError(
                "TOOLCHAIN_UNAVAILABLE", "Injected missing tool")):
                summary = run_suite(output)
            self.assertFalse(summary["all_rejected"])
            self.assertEqual(len(summary["cases"]), len(CASES))
            self.assertTrue(all(not row["passed"] and row["error_code"] == "TOOLCHAIN_UNAVAILABLE" for row in summary["cases"]))
            self.assertEqual(len(list(Path(summary["evidence_root"]).glob("*/failure.json"))), len(CASES))
            self.assertTrue(output.is_file())

    def test_compile_or_runtime_failure_is_not_successful_abstention(self):
        attribution = {"status": "unavailable"}
        for status, runs in (("compile_error", []), ("runtime_error", [{"status": "runtime_error"}])):
            result = {"variants": [{"status": status, "runs": runs}] * 2}
            for case in CASES:
                self.assertFalse(assess(case, result, attribution)[0])


if __name__ == "__main__":
    unittest.main()
