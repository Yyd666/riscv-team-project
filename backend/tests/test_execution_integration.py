"""Consumer boundary and evidence tamper checks; no SJS analysis implementation."""

import copy
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

from backend.app.execution import execute, experiment_session
from backend.app.execution_types import ExecutionRequest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("execution_integration", ROOT / "scripts/check_execution_integration.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


@unittest.skipUnless(sys.platform == "linux" and shutil.which("riscv64-linux-gnu-gcc")
                     and shutil.which("qemu-riscv64"), "Real RV64GC tools required")
class IntegrationBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.folder = Path(cls.temporary.name)
        with experiment_session(ROOT, cls.folder) as context:
            execute(ExecutionRequest("sum_u32", ("O2",)), repo_root=ROOT, context=context)
            cls.execution = context.workspace / "execution.json"
            cls.record = json.loads(cls.execution.read_bytes())

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_real_evidence_and_relocated_archive(self):
        gate.validate(self.execution)
        relocated = self.folder / "relocated"
        shutil.copytree(self.execution.parent, relocated)
        gate.validate(relocated / "execution.json")

    def test_modified_raw_output_is_rejected(self):
        path = self.execution.parent / "O2/runs/empty/stdout.bin"
        original = path.read_bytes()
        try:
            path.write_bytes(b"modified\n")
            with self.assertRaises(ValueError):
                gate.validate(self.execution)
        finally:
            path.write_bytes(original)

    def test_projection_preserves_runs_and_never_invents_analysis(self):
        try:
            import jsonschema
        except ImportError:
            self.skipTest("Install requirements-foundation.txt for experiment Schema projection")
        record = self.record
        fields = ("experiment_id", "created_at", "baseline_version", "baseline_config_sha256",
                  "corpus_version", "benchmark_id", "source_sha256", "environment", "is_mock")
        result = {field: copy.deepcopy(record[field]) for field in fields}
        result.update(schema_version="0.1.0", selection=None,
                      inputs=[{key: value for key, value in item.items() if key in
                              ("case_id", "stdin_sha256", "expected_stdout_sha256")}
                              for item in record["inputs"]])
        result["variants"] = [{
            "optimization": item["optimization"], "status": "analysis_error",
            "compile_argv": item["compilation"]["argv"], "run_argv": item["run_argv"],
            "analysis_argv": [], "diagnostics": "Projection test only; analysis intentionally absent",
            "kernel_disassembly": None, "metrics": None,
            "runs": [{"case_id": run["case_id"], "status": run["status"], **{
                field: run["process"][field] for field in
                ("exit_code", "stdout", "stderr", "wall_time_ms")}} for run in item["runs"]],
        } for item in record["variants"]]
        path = self.folder / "projection-test.json"
        path.write_text(json.dumps(result))
        gate.validate(self.execution, path)
        result["variants"][0]["runs"][0]["stdout"] = "invented\n"
        path.write_text(json.dumps(result))
        with self.assertRaises(ValueError):
            gate.validate(self.execution, path)


if __name__ == "__main__":
    unittest.main()
