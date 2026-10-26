import json
from pathlib import Path
import tempfile
import unittest

from scripts.evaluate_attribution import evaluate


ROOT = Path(__file__).resolve().parents[2]


class EvaluationTests(unittest.TestCase):
    def test_counts_real_sidecar_rows_and_preserves_zero_denominators(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            artifacts = folder / "artifacts" / "exec-1"
            sidecar = artifacts / "attribution" / "O2-O0"
            sidecar.mkdir(parents=True)
            result = ROOT / "contracts/examples/experiment.mock.json"
            attribution = ROOT / "contracts/examples/attribution.complete.mock.json"
            (artifacts / "result.json").write_bytes(result.read_bytes())
            (sidecar / "attribution.json").write_bytes(attribution.read_bytes())
            corpus = folder / "corpus.json"
            corpus.write_text(json.dumps({
                "corpus_version": "0.1.0", "status": "incomplete",
                "development_target": 6, "held_out_target": 6,
                "entries": [{"program_id": "sum_u32", "split": "development", "family": "sum_reduction", "source": "benchmarks/sum_u32/main.c", "provenance": "test"}],
            }), encoding="utf-8")
            summary = evaluate(corpus, folder / "artifacts")
            self.assertEqual(summary["metrics"]["comparison_count"], 2)
            self.assertEqual(summary["metrics"]["byte_error_exact_rate"], 1.0)
            self.assertEqual(summary["metrics"]["r001_verified_rate"], 0.5)

    def test_no_results_have_missing_denominators(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            corpus = folder / "corpus.json"
            corpus.write_text(json.dumps({"entries": [], "status": "incomplete"}), encoding="utf-8")
            summary = evaluate(corpus, folder / "artifacts")
            self.assertIsNone(summary["metrics"]["byte_error_exact_rate"])
            self.assertIsNone(summary["metrics"]["rejection_rate"])


if __name__ == "__main__":
    unittest.main()
