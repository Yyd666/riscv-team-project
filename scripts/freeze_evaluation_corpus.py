"""Validate and freeze the independent evaluation corpus and oracle hashes."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.evaluate_attribution import _corpus_issues
PROGRAMS = {
    "sum_u32": ("development", "sum_reduction", "sum_u32"),
    "dot_i32": ("development", "dot_product", "dot_i32"),
    "threshold_count": ("development", "threshold_filter", "threshold_count"),
    "histogram_count": ("development", "histogram", "histogram_count"),
    "run_length": ("development", "run_length", "run_length"),
    "rolling_hash": ("development", "rolling_hash", "rolling_hash"),
    "xor_checksum": ("held_out", "checksum", "xor_checksum"),
    "lookup_switch": ("held_out", "lookup_and_switch", "lookup_switch"),
    "call_chain": ("held_out", "function_calls", "call_chain"),
    "state_machine": ("held_out", "state_machine", "state_machine"),
    "fixed_point_filter": ("held_out", "fixed_point_filter", "fixed_point_filter"),
    "bounded_parser": ("held_out", "bounded_parser", "bounded_parser"),
}


def oracle(name: str, values: list[int]) -> int:
    if name == "sum_u32":
        return sum(values[1:]) & 0xFFFFFFFF
    if name == "sum_u64":
        return sum(values[1:]) & ((1 << 64) - 1)
    if name in {"dot_i16", "dot_i32"}:
        n = values[0]
        return sum(values[1:1 + n][i] * values[1 + n:1 + 2 * n][i] for i in range(n))
    if name == "threshold_count":
        n, threshold = values[:2]
        return sum(value >= threshold for value in values[2:2 + n])
    if name == "threshold_abs":
        threshold, n = values[:2]
        return sum(abs(value) >= threshold for value in values[2:2 + n])
    if name == "histogram_count":
        n = values[0]
        return sum(value + 1 for value in values[1:1 + n])
    if name == "run_length":
        data = values[1:1 + values[0]]
        best = current = 0
        for index, value in enumerate(data):
            current = current + 1 if index and value == data[index - 1] else 1
            best = max(best, current)
        return best
    if name == "rolling_hash":
        result = 0
        for value in values[1:1 + values[0]]:
            result = (result * 257 + value) % 1000000007
        return result
    if name == "xor_checksum":
        result = 0
        for value in values[1:1 + values[0]]: result ^= value
        return result
    if name == "lookup_switch":
        table = {0: 3, 1: 5, 2: 7}
        return sum(table.get(value, -1) for value in values[1:1 + values[0]])
    if name == "call_chain":
        return sum(value * value - value for value in values[1:1 + values[0]])
    if name == "state_machine":
        state = 0
        for event in values[1:1 + values[0]]:
            if event == 0: state = (state + 1) % 4
            elif event == 1: state = (state + 3) % 4
            elif event == 2: state = (state * 2 + 1) % 4
        return state
    if name == "fixed_point_filter":
        threshold, n = values[:2]
        return sum((1 if value >= 0 else -1) * (abs(value * 3) // 2)
                   for value in values[2:2 + n] if value >= threshold)
    if name == "bounded_parser":
        value = 0
        for digit in values[1:1 + values[0]]: value = (value * 10 + digit) % 1000003
        return value
    raise ValueError(name)


def main() -> int:
    entries = []
    families: dict[str, set[str]] = {"development": set(), "held_out": set()}
    for program_id, (split, family, oracle_name) in PROGRAMS.items():
        directory = (ROOT / "benchmarks" / program_id) if program_id in {"sum_u32", "dot_i32", "threshold_count"} else (ROOT / "evaluation" / "programs" / program_id)
        source = directory / "main.c"
        if not source.is_file(): raise ValueError(f"missing source: {source}")
        families[split].add(family)
        case_hashes = []
        for case in sorted((directory / "cases").glob("*.in")):
            raw = case.read_text(encoding="utf-8").split()
            values = [int(item) for item in raw]
            expected = f"{oracle(oracle_name, values)}\n"
            actual = case.with_suffix(".out").read_text(encoding="utf-8")
            if actual != expected: raise ValueError(f"oracle mismatch: {case}")
            case_hashes.append({"case_id": case.stem, "stdin": case.relative_to(ROOT).as_posix(),
                                "expected_stdout": case.with_suffix(".out").relative_to(ROOT).as_posix(),
                                "stdin_sha256": hashlib.sha256(case.read_bytes()).hexdigest(),
                                "expected_stdout_sha256": hashlib.sha256(case.with_suffix(".out").read_bytes()).hexdigest()})
        entries.append({
            "program_id": program_id, "split": split, "family": family,
            "source": str(source.relative_to(ROOT)).replace("\\", "/"),
            "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "provenance": "development_oracle_v1" if split == "development" else "held_out_oracle_v1",
            "source_origin": "repository_authored_development" if split == "development" else "repository_authored_held_out",
            "license": "project-authored-pending-confirmation",
            "cases": case_hashes,
        })
    if families["development"] & families["held_out"]:
        raise ValueError("family leakage")
    document = {
        "corpus_version": "0.1.0",
        "status": "frozen",
        "split_unit": "program_family_and_provenance",
        "development_target": 6,
        "held_out_target": 6,
        "entries": entries,
    }
    path = ROOT / "evaluation" / "corpus.json"
    issues = _corpus_issues(document)
    if issues:
        print("NOT FROZEN: " + "; ".join(issues), file=sys.stderr)
        return 3
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"FROZEN: {len(entries)} programs, {len(families['development'])} development families, {len(families['held_out'])} held-out families")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
