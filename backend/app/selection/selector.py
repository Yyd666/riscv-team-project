"""Finite O0/O2/Os candidate selection based on validated static size."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

PROFILES = ("O0", "O2", "Os")
OBJECTIVE = "min_text_section_bytes"
EVIDENCE = "static_size_only"
DEFAULT_TIE_BREAK = ("O2", "Os", "O0")


class SelectionInputError(ValueError):
    """Invalid or ambiguous candidate input."""


@dataclass(frozen=True)
class SelectionDecision:
    status: str
    optimization: str | None
    objective: str = OBJECTIVE
    evidence: str = EVIDENCE
    reason: str | None = None
    eligible: tuple[str, ...] = ()
    rejected: tuple[tuple[str, str], ...] = ()

    @property
    def selection(self) -> dict[str, str] | None:
        if self.optimization is None:
            return None
        return {"objective": self.objective, "optimization": self.optimization,
                "evidence": self.evidence}

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status, "selection": self.selection,
            "objective": self.objective, "evidence": self.evidence,
            "reason": self.reason, "eligible": list(self.eligible),
            "rejected": [{"optimization": p, "reason": r} for p, r in self.rejected],
        }


def _text_bytes(variant: Mapping[str, Any]) -> int | None:
    metrics = variant.get("metrics")
    if not isinstance(metrics, Mapping):
        return None
    value = metrics.get("text_section_bytes")
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise SelectionInputError("text_section_bytes must be a positive integer")
    return value


def select_candidate(
    variants: Iterable[Mapping[str, Any]],
    *,
    tie_break_order: Iterable[str] = DEFAULT_TIE_BREAK,
) -> SelectionDecision:
    """Select the smallest correctness-passed candidate with static evidence."""
    order = tuple(tie_break_order)
    if order != DEFAULT_TIE_BREAK or set(order) != set(PROFILES):
        raise SelectionInputError("Tie-break order must remain O2, Os, O0")
    priority = {profile: index for index, profile in enumerate(order)}
    seen: set[str] = set()
    eligible: list[tuple[str, int]] = []
    rejected: list[tuple[str, str]] = []

    for variant in variants:
        if not isinstance(variant, Mapping):
            raise SelectionInputError("Each candidate must be an object")
        profile = variant.get("optimization")
        if profile not in PROFILES:
            raise SelectionInputError(f"Unknown optimization profile: {profile!r}")
        if profile in seen:
            raise SelectionInputError(f"Duplicate optimization profile: {profile}")
        seen.add(profile)
        if variant.get("status") != "passed":
            rejected.append((profile, f"status:{variant.get('status', 'missing')}"))
            continue
        text_bytes = _text_bytes(variant)
        if text_bytes is None:
            rejected.append((profile, "missing_metrics"))
            continue
        eligible.append((profile, text_bytes))

    if not eligible:
        return SelectionDecision("unavailable", None,
                                 reason="no_correctness_passed_candidate",
                                 rejected=tuple(rejected))
    eligible.sort(key=lambda item: (item[1], priority[item[0]]))
    return SelectionDecision(
        "recommended", eligible[0][0],
        reason="minimum_text_section_bytes_with_registered_tie_break",
        eligible=tuple(profile for profile, _ in eligible),
        rejected=tuple(rejected),
    )


def selection_for_experiment(
    experiment: Mapping[str, Any],
    *,
    tie_break_order: Iterable[str] = DEFAULT_TIE_BREAK,
) -> SelectionDecision:
    variants = experiment.get("variants")
    if not isinstance(variants, list):
        raise SelectionInputError("Experiment variants must be a list")
    return select_candidate(variants, tie_break_order=tie_break_order)
