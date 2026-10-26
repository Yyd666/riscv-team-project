"""Execution-registry gates and real diagnostic runs, not independent samples."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

from backend.app.execution_types import ExecutionError
from scripts.check_execution_integration import validate
from scripts.evaluate_attribution import _formal_provenance, evaluate
from scripts.evaluation_registry import digest, prepare_program, read_registry
from scripts.run_evaluation_corpus import CorpusNotReady, run_batch

ROOT = Path(__file__).resolve().parents[2]


def repository(folder: Path, *, registered_cases=True):
    root = folder / "fixture-repository"
    root.mkdir()
    shutil.copytree(ROOT / "config", root / "config")
    shutil.copytree(ROOT / "benchmarks", root / "benchmarks")
    (root / "evaluation").mkdir()
    source = root / "benchmarks/sum_u32/main.c"
    entry = {"program_id": "sum_u32", "split": "development", "family": "sum_reduction",
             "provenance": "runner_test_fixture", "source": "benchmarks/sum_u32/main.c",
             "source_sha256": digest(source.read_bytes())}
    if registered_cases:
        entry["cases"] = [{"case_id": case.stem, "stdin": case.relative_to(root).as_posix(),
                           "expected_stdout": case.with_suffix(".out").relative_to(root).as_posix(),
                           "stdin_sha256": digest(case.read_bytes()),
                           "expected_stdout_sha256": digest(case.with_suffix(".out").read_bytes())}
                          for case in sorted((source.parent / "cases").glob("*.in"))]
    corpus = {"corpus_version": "runner-test", "status": "under_review", "development_target": 6,
              "held_out_target": 6, "entries": [entry]}
    path = root / "evaluation/corpus.json"
    path.write_text(json.dumps(corpus), encoding="utf-8")
    return root, path, corpus


class EvaluationRegistryTests(unittest.TestCase):
    def test_draft_is_not_run_as_formal_evaluation(self):
        with tempfile.TemporaryDirectory() as directory:
            root, path, _ = repository(Path(directory))
            output = Path(directory) / "output"
            with self.assertRaises(CorpusNotReady):
                run_batch(root, path, output)
            self.assertFalse(output.exists())

    def test_source_and_oracle_drift_are_rejected_before_any_output(self):
        for kind in ("source", "oracle"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                root, path, _ = repository(Path(directory))
                target = root / ("benchmarks/sum_u32/main.c" if kind == "source" else "benchmarks/sum_u32/cases/empty.out")
                target.write_bytes(target.read_bytes() + b"changed")
                output = Path(directory) / "output"
                with self.assertRaisesRegex(ValueError, "hash"):
                    run_batch(root, path, output, diagnostic=True)
                self.assertFalse(output.exists())

    def test_external_registry_cannot_introduce_another_program(self):
        with tempfile.TemporaryDirectory() as directory:
            root, path, _ = repository(Path(directory))
            external = Path(directory) / "arbitrary.json"
            external.write_bytes(path.read_bytes())
            with self.assertRaisesRegex(ValueError, "registered evaluation/corpus.json"):
                read_registry(root, external)

    def test_legacy_inputs_can_only_be_discovered_as_diagnostic(self):
        with tempfile.TemporaryDirectory() as directory:
            root, _, corpus = repository(Path(directory), registered_cases=False)
            entry = corpus["entries"][0]
            with self.assertRaisesRegex(ValueError, "Frozen input"):
                prepare_program(root, entry, diagnostic=False)
            program = prepare_program(root, entry, diagnostic=True)
            self.assertEqual(program.case_binding_origin, "discovered_diagnostic")
            self.assertEqual(len(program.cases), 3)

    def test_registry_omission_or_duplicate_case_cannot_pass(self):
        for kind in ("omission", "duplicate"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                root, _, corpus = repository(Path(directory))
                entry = corpus["entries"][0]
                if kind == "omission":
                    entry["cases"].pop()
                else:
                    entry["cases"].append(entry["cases"][0])
                with self.assertRaises(ValueError):
                    prepare_program(root, entry, diagnostic=False)

    @unittest.skipUnless(sys.platform == "linux", "Linux artifact lock")
    def test_busy_artifact_root_cannot_start_another_batch(self):
        import fcntl
        with tempfile.TemporaryDirectory() as directory:
            root, path, _ = repository(Path(directory))
            output = Path(directory) / "output"
            output.mkdir()
            with (output / ".evaluation.lock").open("a+b") as lock:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                with self.assertRaises(ExecutionError) as caught:
                    run_batch(root, path, output, diagnostic=True)
                self.assertEqual(caught.exception.code, "EXPERIMENT_BUSY")
                self.assertFalse(list(output.glob("evaluation-*")))

    @unittest.skipUnless(sys.platform == "linux", "Linux symlink fixture")
    def test_source_symlink_cannot_escape_registry_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root, path, corpus = repository(Path(directory))
            source = root / "benchmarks/sum_u32/main.c"
            outside = Path(directory) / "external.c"
            outside.write_bytes(source.read_bytes())
            source.unlink()
            source.symlink_to(outside)
            with self.assertRaisesRegex(ValueError, "escapes"):
                prepare_program(root, corpus["entries"][0], diagnostic=True)


@unittest.skipUnless(sys.platform == "linux" and shutil.which("riscv64-linux-gnu-gcc")
                     and shutil.which("qemu-riscv64"), "Real RV64GC tools required")
class RealEvaluationRunnerTests(unittest.TestCase):
    def test_runs_are_traceable_non_overwriting_and_explicitly_diagnostic(self):
        with tempfile.TemporaryDirectory() as directory:
            root, corpus_path, corpus = repository(Path(directory))
            with redirect_stdout(io.StringIO()):
                first, code = run_batch(root, corpus_path, Path(directory) / "output", diagnostic=True)
            self.assertEqual(code, 0)
            batch = json.loads(first.read_bytes())
            self.assertTrue(batch["completed"] and batch["all_passed"])
            self.assertEqual(batch["mode"], "diagnostic")
            self.assertFalse(batch["acceptance_ready"])
            source = Path(batch["programs"][0]["result_path"])
            result = json.loads(source.read_bytes())
            self.assertIn("gcc", result["environment"]["compiler_version"].lower())
            validate(source.parent / "execution.json", source, registry_root=first.parent / "registry-repository")
            for relative, expected in batch["artifact_sha256"].items():
                self.assertEqual(digest((first.parent / relative).read_bytes()), expected)
            self.assertIn("Diagnostic", _formal_provenance(source, result, corpus, digest(corpus_path.read_bytes())))
            evaluation = evaluate(corpus_path, first.parent / "experiments")
            self.assertEqual(evaluation["metrics"]["independent_byte_error_denominator"], 2)
            self.assertEqual(evaluation["metrics"]["byte_error_exact_rate"], 1)
            self.assertEqual(len(evaluation["formal_ineligible_programs"]), 1)
            self.assertFalse(evaluation["automated_checks_passed"])
            old_result_hash = digest(source.read_bytes())
            with redirect_stdout(io.StringIO()):
                second, code = run_batch(root, corpus_path, Path(directory) / "output", diagnostic=True)
            self.assertEqual(code, 0)
            self.assertNotEqual(first, second)
            self.assertEqual(digest(source.read_bytes()), old_result_hash)

    def test_compile_failure_retains_raw_diagnostics_and_never_prints_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            root, path, corpus = repository(Path(directory))
            source = root / "benchmarks/sum_u32/main.c"
            source.write_text("this is not valid C\n", encoding="utf-8")
            corpus["entries"][0]["source_sha256"] = digest(source.read_bytes())
            path.write_text(json.dumps(corpus), encoding="utf-8")
            display = io.StringIO()
            with redirect_stdout(display):
                summary_path, code = run_batch(root, path, Path(directory) / "output", diagnostic=True)
            self.assertEqual(code, 3)
            self.assertNotIn("PASS:", display.getvalue())
            batch = json.loads(summary_path.read_bytes())
            self.assertTrue(batch["completed"])
            self.assertFalse(batch["all_passed"])
            result_path = Path(batch["programs"][0]["result_path"])
            validate(result_path.parent / "execution.json", result_path,
                     registry_root=summary_path.parent / "registry-repository")
            for profile in ("O0", "O2", "Os"):
                self.assertTrue((result_path.parent / profile / "compile/stderr.bin").read_bytes())
                self.assertFalse((result_path.parent / profile / "runs").exists())

    def test_wrong_oracle_preserves_failure_and_runs_remaining_cases(self):
        with tempfile.TemporaryDirectory() as directory:
            root, path, corpus = repository(Path(directory))
            target = root / "benchmarks/sum_u32/cases/empty.out"
            target.write_bytes(b"999\n")
            corpus["entries"][0]["cases"][0]["expected_stdout_sha256"] = digest(target.read_bytes())
            path.write_text(json.dumps(corpus), encoding="utf-8")
            with redirect_stdout(io.StringIO()):
                summary_path, code = run_batch(root, path, Path(directory) / "output", diagnostic=True)
            self.assertEqual(code, 3)
            result = json.loads(Path(json.loads(summary_path.read_bytes())["programs"][0]["result_path"]).read_bytes())
            self.assertTrue(all(v["status"] == "wrong_answer" and len(v["runs"]) == 3 for v in result["variants"]))
            self.assertIsNone(result["selection"])

    def test_tool_failure_is_incomplete_and_keeps_error_package(self):
        with tempfile.TemporaryDirectory() as directory:
            root, path, _ = repository(Path(directory))
            with patch("backend.app.execution.engine._environment", side_effect=ExecutionError(
                "TOOLCHAIN_UNAVAILABLE", "Injected missing tool")):
                summary_path, code = run_batch(root, path, Path(directory) / "output", diagnostic=True)
            self.assertEqual(code, 5)
            batch = json.loads(summary_path.read_bytes())
            self.assertFalse(batch["completed"] or batch["all_passed"])
            self.assertEqual(batch["active_program"], "sum_u32")
            self.assertEqual(batch["error"]["code"], "TOOLCHAIN_UNAVAILABLE")
            self.assertEqual(len(list(summary_path.parent.glob("experiments/*/error.json"))), 1)


if __name__ == "__main__":
    unittest.main()
