"""Independent oracle audit must reject internally consistent, incorrect fixtures."""

import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from scripts.check_corpus_oracles import ROOT, audit, reference


class CorpusOracleTests(unittest.TestCase):
    def test_registered_assets_and_oracles(self):
        report = audit(ROOT / "evaluation/corpus.json", ROOT)
        self.assertEqual((report["program_count"], report["case_count"], report["asset_count"]),
                         (12, 36, 85))

    def test_numeric_edges_and_c_signed_division(self):
        self.assertEqual(reference("sum_u32", b"3 4294967295 4294967295 2\n"), 0)
        self.assertEqual(reference("fixed_point_filter", b"-3 3 -3 -1 1\n"), -4)
        self.assertEqual(reference("state_machine", b"2 0 4294967295\n"), 1)
        self.assertEqual(reference("dot_i32", ("64 " + " ".join(["10000"] * 128)).encode()),
                         6400000000)
        self.assertEqual(reference("bounded_parser", b"7 9 9 9 9 9 9 9\n"), 999972)
        self.assertEqual(reference("rolling_hash", b"6 255 0 1 128 7 42\n"), 521158983)

    def test_invalid_shape_range_and_signed_intermediates(self):
        for program, data in (
            ("sum_u32", b"2 1"), ("sum_u32", b"0 9"),
            ("sum_u32", b"1 4294967296"), ("histogram_count", b"1 8"),
            ("threshold_count", b"0 10001"), ("dot_i32", b"1 10001 1"),
            ("bounded_parser", b"1 10"), ("call_chain", b"1 46341"),
            ("call_chain", b"2 46340 46340"),
        ):
            with self.subTest(program=program, data=data), self.assertRaises(ValueError):
                reference(program, data)

    def test_changed_source_and_rehashed_wrong_oracle_are_rejected(self):
        corpus = json.loads((ROOT / "evaluation/corpus.json").read_bytes())
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = {corpus["license_file"]}
            for entry in corpus["entries"]:
                paths.add(entry["source"])
                for case in entry["cases"]:
                    paths.update((case["stdin"], case["expected_stdout"]))
            for relative in paths:
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / relative, target)
            source = root / corpus["entries"][0]["source"]
            original = source.read_bytes()
            source.write_bytes(original + b"\n")
            path = root / "evaluation/corpus.json"
            path.write_text(json.dumps(corpus), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "asset hash mismatch"):
                audit(path, root)
            source.write_bytes(original)
            case = corpus["entries"][0]["cases"][0]
            wrong = b"123\n"
            (root / case["expected_stdout"]).write_bytes(wrong)
            case["expected_stdout_sha256"] = hashlib.sha256(wrong).hexdigest()
            path.write_text(json.dumps(corpus), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "oracle mismatch"):
                audit(path, root)


if __name__ == "__main__":
    unittest.main()
