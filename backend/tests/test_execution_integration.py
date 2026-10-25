"""Consumer boundary and evidence tamper checks; no SJS analysis implementation."""

import copy
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import time
import unittest

from backend.app.execution import execute, experiment_session, ProcessRunner
from backend.app.execution_types import ExecutionContext, ExecutionRequest
from scripts.elf_reference import inspect_elf

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

    def projection(self):
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
        return result

    def test_projection_preserves_runs_and_never_invents_analysis(self):
        result = self.projection()
        path = self.folder / "projection-test.json"
        path.write_text(json.dumps(result))
        gate.validate(self.execution, path)
        result["variants"][0]["runs"][0]["stdout"] = "invented\n"
        path.write_text(json.dumps(result))
        with self.assertRaises(ValueError):
            gate.validate(self.execution, path)

    def test_passed_projection_metrics_are_checked_independently(self):
        result = self.projection()
        elf = self.execution.parent / "O2/program.elf"
        metrics, disassembly = inspect_elf(elf)
        variant = result["variants"][0]
        variant.update(status="passed", metrics=metrics, kernel_disassembly=disassembly,
                       diagnostics="Integration test projection, not product pipeline output",
                       analysis_argv=[[shutil.which("riscv64-linux-gnu-objdump"), "-d", "-M",
                                       "no-aliases,numeric", "--disassemble=kernel", str(elf)]])
        result["selection"] = {"objective": "min_text_section_bytes", "optimization": "O2",
                               "evidence": "static_size_only"}
        path = self.folder / "passed-projection-test.json"
        path.write_text(json.dumps(result))
        gate.validate(self.execution, path)
        for field in ("elf_file_bytes", "text_section_bytes", "kernel_code_bytes",
                      "kernel_static_instruction_count", "kernel_compressed_instruction_count"):
            with self.subTest(field=field):
                changed = copy.deepcopy(result)
                changed["variants"][0]["metrics"][field] += 1
                path.write_text(json.dumps(changed))
                with self.assertRaisesRegex(ValueError, "independent ELF reference"):
                    gate.validate(self.execution, path)
        changed = copy.deepcopy(result)
        changed["variants"][0]["kernel_disassembly"] = "0: 0001 c.addi\n"
        path.write_text(json.dumps(changed))
        with self.assertRaisesRegex(ValueError, "disassembly differs"):
            gate.validate(self.execution, path)
        changed = copy.deepcopy(result)
        changed["variants"][0]["kernel_disassembly"] = disassembly.replace("x10", "x11", 1)
        self.assertNotEqual(changed["variants"][0]["kernel_disassembly"], disassembly)
        path.write_text(json.dumps(changed))
        with self.assertRaisesRegex(ValueError, "disassembly differs"):
            gate.validate(self.execution, path)


@unittest.skipUnless(sys.platform == "linux" and shutil.which("riscv64-linux-gnu-gcc"),
                     "GNU RISC-V reference tools required")
class ELFReferenceTests(unittest.TestCase):
    def compile_fixture(self, folder, *, unknown=False, symbol="kernel"):
        source = folder / "reference.S"
        source.write_text(
            f".text\n.globl {symbol}\n.type {symbol},@function\n{symbol}:\n"
            + (".2byte 0x0000\n" if unknown else
               ".option rvc\nli a0,0\n.option norvc\naddi a0,a0,1\n.option rvc\nret\n")
            + f".size {symbol},.-{symbol}\n")
        elf = folder / "reference.elf"
        context = ExecutionContext(folder, time.monotonic() + 20)
        result = ProcessRunner(context).run([
            shutil.which("riscv64-linux-gnu-gcc"), "-march=rv64gc", "-mabi=lp64d",
            "-nostdlib", "-static", "-no-pie", "-Wl,-e," + symbol,
            str(source), "-o", str(elf)], cwd=folder, timeout_s=10, max_output_bytes=1048576)
        self.assertEqual(result.exit_code, 0, result.stderr)
        return elf

    def test_reference_matches_handwritten_three_instruction_kernel(self):
        with tempfile.TemporaryDirectory() as directory:
            elf = self.compile_fixture(Path(directory))
            metrics, _ = inspect_elf(elf)
            self.assertEqual(metrics, {"elf_file_bytes": elf.stat().st_size,
                "text_section_bytes": 8, "kernel_code_bytes": 8,
                "kernel_static_instruction_count": 3, "kernel_compressed_instruction_count": 2,
                "dynamic_instruction_count": None, "target_cycles": None})

    def test_reference_rejects_missing_symbol_and_unknown_encoding(self):
        for unknown, symbol in ((False, "other"), (True, "kernel")):
            with self.subTest(unknown=unknown, symbol=symbol), tempfile.TemporaryDirectory() as directory:
                elf = self.compile_fixture(Path(directory), unknown=unknown, symbol=symbol)
                with self.assertRaises(ValueError):
                    inspect_elf(elf)


if __name__ == "__main__":
    unittest.main()
