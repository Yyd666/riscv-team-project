import copy
import json
from pathlib import Path
import tempfile
import unittest

from scripts.validate_reviews import ReviewError, _validate_adjudication, _validate_shape


IDS = [f"program_{index:02d}" for index in range(12)]


def review(reviewer):
    profiles = {
        profile: {
            "elf_sha256": "a" * 64, "text_section_bytes": 100,
            "kernel_start": 4096, "kernel_end": 4100, "section_index": 1,
            "instructions_16": 0, "instructions_32": 1, "unclassified_bytes": 0,
            "r001": "verified", "r002": "verified", "evidence": ["O2/program.elf"]
        }
        for profile in ("O0", "O2", "Os")
    }
    return {"schema_version": "0.1.0", "reviewer_id": reviewer,
            "review_date": "2026-10-26", "independent_from": ["other"],
            "batch_id": "evaluation-test", "programs": [
                {"program_id": program, "profiles": copy.deepcopy(profiles)} for program in IDS
            ]}


class ReviewGateTests(unittest.TestCase):
    def test_complete_independent_shapes_pass(self):
        first, second = review("alice"), review("bob")
        _validate_shape(first, IDS, "a")
        _validate_shape(second, IDS, "b")
        decisions = [{"program_id": program, "profile": profile,
                      "final_r001": "verified", "final_r002": "verified", "reason": "same bytes"}
                     for program in IDS for profile in ("O0", "O2", "Os")]
        _validate_adjudication({"schema_version": "0.1.0", "reviewer_ids": ["alice", "bob"],
                                "decisions": decisions, "signoffs": ["alice", "bob"]}, IDS, {"alice", "bob"})

    def test_same_reviewer_or_missing_program_is_rejected(self):
        first = review("alice")
        with self.assertRaises(ReviewError):
            second = review("alice")
            _validate_shape(second, IDS, "b")
            if first["reviewer_id"] == second["reviewer_id"]:
                raise ReviewError("same reviewer")
        missing = review("bob")
        missing["programs"].pop()
        with self.assertRaises(ReviewError):
            _validate_shape(missing, IDS, "b")

    def test_adjudication_requires_every_profile_and_reason(self):
        decisions = [{"program_id": program, "profile": profile,
                      "final_r001": "verified", "final_r002": "verified", "reason": "ok"}
                     for program in IDS for profile in ("O0", "O2", "Os")]
        decisions.pop()
        with self.assertRaises(ReviewError):
            _validate_adjudication({"schema_version": "0.1.0", "reviewer_ids": ["a", "b"],
                                    "decisions": decisions, "signoffs": ["a", "b"]}, IDS, {"a", "b"})


if __name__ == "__main__":
    unittest.main()
