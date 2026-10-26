import json
from pathlib import Path
import shutil
import tempfile
import unittest

from scripts.evaluate_attribution import evaluate, _corpus_issues

ROOT = Path(__file__).resolve().parents[2]


class EvaluationTests(unittest.TestCase):
    def corpus(self, folder):
        result = json.loads((ROOT / "contracts/examples/experiment.mock.json").read_text())
        source = ROOT / "benchmarks/sum_u32/main.c"
        import hashlib
        entry = {"program_id": "sum_u32", "split": "development", "family": "sum_reduction",
                 "source": str(source.relative_to(ROOT)).replace("\\", "/"),
                 "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "provenance": "test",
                 "source_origin": "fixture", "license": "fixture"}
        corpus = folder / "corpus.json"
        corpus.write_text(json.dumps({"status": "under_review", "development_target": 6,
                                     "held_out_target": 6, "entries": [entry]}))
        return corpus

    def test_mock_is_rejected_and_missing_profiles_stay_in_denominator(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "artifacts/run-1"
            artifact.mkdir(parents=True)
            shutil.copyfile(ROOT / "contracts/examples/experiment.mock.json", artifact / "result.json")
            summary = evaluate(self.corpus(root), root / "artifacts")
            self.assertEqual(summary["metrics"]["comparison_count"], 2)
            self.assertEqual(summary["metrics"]["program_count"], 0)
            self.assertIsNone(summary["metrics"]["byte_error_exact_rate"])
            self.assertEqual(summary["metrics"]["status_counts"], {"invalid_result": 2})
            self.assertFalse(summary["automated_checks_passed"])
            self.assertFalse(summary["acceptance_ready"])

    def test_duplicate_runs_cannot_inflate_sample_count(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("run-1", "run-2"):
                artifact = root / "artifacts" / name
                artifact.mkdir(parents=True)
                shutil.copyfile(ROOT / "contracts/examples/experiment.mock.json", artifact / "result.json")
            summary = evaluate(self.corpus(root), root / "artifacts")
            self.assertEqual(summary["metrics"]["comparison_count"], 2)
            self.assertEqual(summary["metrics"]["status_counts"], {"duplicate_result": 2})

    def test_missing_results_are_counted_as_missing_not_zero_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            summary = evaluate(self.corpus(root), root / "artifacts")
            self.assertEqual(summary["missing_programs"], ["sum_u32"])
            self.assertEqual(summary["metrics"]["comparison_count"], 2)
            self.assertEqual(summary["metrics"]["status_counts"], {"missing_result": 2})
            self.assertIsNone(summary["metrics"]["byte_error_exact_rate"])
            self.assertEqual(summary["metrics"]["rejection_rate"], 1)

    def test_empty_corpus_never_passes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            corpus = root / "corpus.json"
            corpus.write_text(json.dumps({"entries": [], "status": "incomplete"}))
            summary = evaluate(corpus, root / "artifacts")
            self.assertIsNone(summary["metrics"]["byte_error_exact_rate"])
            self.assertIsNone(summary["metrics"]["rejection_rate"])
            self.assertFalse(summary["automated_checks_passed"])

    def test_current_corpus_has_machine_isolated_provenance_but_not_human_review(self):
        corpus = json.loads((ROOT / "evaluation/corpus.json").read_text())
        issues = _corpus_issues(corpus)
        self.assertEqual(issues, [])

    def test_family_leakage_and_hash_drift_are_explicit(self):
        corpus = {"entries": [{"program_id": "one", "split": "development", "family": "same",
                              "source": "README.md", "source_sha256": "0" * 64, "provenance": "dev",
                              "source_origin": "dev", "license": "fixture"},
                             {"program_id": "two", "split": "held_out", "family": "same",
                              "source": "README.md", "source_sha256": "0" * 64, "provenance": "held",
                              "source_origin": "held", "license": "fixture"}]}
        issues = _corpus_issues(corpus)
        self.assertTrue(any("family leakage" in issue for issue in issues))
        self.assertTrue(any("hash mismatch" in issue for issue in issues))


if __name__ == "__main__":
    unittest.main()
