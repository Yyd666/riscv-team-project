"""Real compiler/QEMU fixtures test partial attribution after analysis rejection."""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

from backend.app.pipeline import load_baseline, run_experiment

ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(sys.platform == "linux" and shutil.which("riscv64-linux-gnu-gcc")
                     and shutil.which("qemu-riscv64"), "Real RV64GC tools required")
class RealPartialAttributionTests(unittest.TestCase):
    def run_fixture(self, transform):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "fixture-repository"
            root.mkdir()
            shutil.copytree(ROOT / "config", root / "config")
            shutil.copytree(ROOT / "benchmarks", root / "benchmarks")
            source = root / "benchmarks/sum_u32/main.c"
            source.write_text(transform(source.read_text()), encoding="utf-8")
            result, path, code = run_experiment(root, Path(directory) / "evidence", "sum_u32",
                                                ("O2", "Os"), load_baseline(root), require_attribution=True)
            self.assertEqual(code, 3)  # Static analysis failed; correctness still passed.
            self.assertTrue(all(run["status"] == "passed" for v in result["variants"] for run in v["runs"]))
            self.assertTrue(all(v["status"] == "analysis_error" for v in result["variants"]))
            attribution = json.loads((path.parent / "attribution/O2-Os/attribution.json").read_bytes())
            self.assertEqual(attribution["status"], "partial", attribution["reason"])
            return attribution

    def test_executed_function_outside_text_is_not_applicable(self):
        attribution = self.run_fixture(lambda source: source.replace(
            "__attribute__((noinline))", '__attribute__((noinline, section(".kernel_extra")))'))
        self.assertFalse(attribution["snapshots"]["reference"]["inside_text"])
        self.assertEqual(attribution["rules"][0]["status"], "verified")
        self.assertEqual(attribution["rules"][1]["status"], "not_applicable")
        self.assertIsNone(attribution["deltas"]["outside_kernel_delta_bytes"])

    def test_unreachable_unknown_bytes_are_not_counted_as_instructions(self):
        def transform(source):
            source = source.replace("uint32_t kernel(", "uint32_t kernel_impl(", 1)
            wrapper = r'''
extern uint32_t kernel(const uint32_t *, unsigned int);
__asm__(".text\n.option rvc\n.globl kernel\n.type kernel,@function\n"
        "kernel:\ntail kernel_impl\n.2byte 0\n.size kernel,.-kernel\n");
'''
            return source.replace("int main(void)", wrapper + "\nint main(void)")
        attribution = self.run_fixture(transform)
        self.assertGreater(attribution["snapshots"]["candidate"]["unclassified_bytes"], 0)
        self.assertEqual(attribution["rules"][0]["status"], "abstained")
        self.assertEqual(attribution["rules"][1]["status"], "verified")


if __name__ == "__main__":
    unittest.main()
