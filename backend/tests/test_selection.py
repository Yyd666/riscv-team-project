import unittest

from backend.app.selection import (
    SelectionInputError, select_candidate, validate_baseline_policy,
)


BASELINE = {
    "profiles": {"O0": ["-O0"], "O2": ["-O2"], "Os": ["-Os"]},
    "selection": {
        "objective": "min_text_section_bytes",
        "require_all_cases_pass": True,
        "tie_break_order": ["O2", "Os", "O0"],
    },
}


def variant(profile, status="passed", text_bytes=100, **extra):
    item = {"optimization": profile, "status": status}
    if text_bytes is not None:
        item["metrics"] = {"text_section_bytes": text_bytes, **extra}
    return item


class SelectionTests(unittest.TestCase):
    def test_smallest_text_section_wins(self):
        decision = select_candidate([
            variant("O0", text_bytes=240), variant("O2", text_bytes=180),
            variant("Os", text_bytes=160)])
        self.assertEqual(decision.status, "recommended")
        self.assertEqual(decision.optimization, "Os")
        self.assertEqual(decision.selection, {
            "objective": "min_text_section_bytes",
            "optimization": "Os",
            "evidence": "static_size_only"})

    def test_tie_uses_registered_order(self):
        decision = select_candidate([
            variant("O0", text_bytes=100), variant("Os", text_bytes=80),
            variant("O2", text_bytes=80)])
        self.assertEqual(decision.optimization, "O2")

    def test_failed_and_incomplete_are_excluded(self):
        decision = select_candidate([
            variant("O0", status="wrong_answer", text_bytes=10),
            variant("O2", status="analysis_error", text_bytes=1),
            variant("Os", text_bytes=None)])
        self.assertEqual(decision.status, "unavailable")
        self.assertIsNone(decision.selection)
        self.assertEqual(dict(decision.rejected), {
            "O0": "status:wrong_answer", "O2": "status:analysis_error",
            "Os": "invalid_or_missing_metrics"})

    def test_invalid_metric_is_excluded_without_aborting_other_candidates(self):
        decision = select_candidate([
            variant("O2", text_bytes=0), variant("Os", text_bytes=50)])
        self.assertEqual(decision.optimization, "Os")
        self.assertEqual(dict(decision.rejected), {"O2": "invalid_or_missing_metrics"})

    def test_host_time_is_ignored(self):
        decision = select_candidate([
            variant("O2", text_bytes=100, wall_time_ms=1),
            variant("Os", text_bytes=120, wall_time_ms=999999)])
        self.assertEqual(decision.optimization, "O2")

    def test_duplicate_or_invalid_profile_is_rejected(self):
        with self.assertRaises(SelectionInputError):
            select_candidate([variant("O2"), variant("O2")])
        with self.assertRaises(SelectionInputError):
            select_candidate([variant("O3")])

    def test_partial_candidate_set_is_supported(self):
        self.assertEqual(select_candidate([variant("Os", text_bytes=50)]).optimization, "Os")

    def test_baseline_policy_must_match(self):
        validate_baseline_policy(BASELINE)
        bad = {**BASELINE, "selection": {**BASELINE["selection"], "tie_break_order": ["Os", "O2", "O0"]}}
        with self.assertRaises(SelectionInputError):
            validate_baseline_policy(bad)


if __name__ == "__main__":
    unittest.main()
