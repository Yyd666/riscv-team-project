"""Read-only numeric/oracle audit; independent of the corpus generator and engine."""

from __future__ import annotations

import argparse
from collections import Counter
from functools import reduce
import hashlib
from itertools import groupby
import json
from operator import xor
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
U32 = (0, 2**32 - 1)
I32 = (-2**31, 2**31 - 1)
PROGRAMS = {
    "sum_u32", "dot_i32", "threshold_count", "histogram_count", "run_length",
    "rolling_hash", "xor_checksum", "lookup_switch", "call_chain",
    "state_machine", "fixed_point_filter", "bounded_parser",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def bounded(values: list[int], limits: tuple[int, int]) -> None:
    require(all(limits[0] <= value <= limits[1] for value in values),
            f"values outside {limits}")


def reference(program: str, raw: bytes) -> int:
    """Use exact integer mathematics, never O0 output or product parser metrics."""
    tokens = raw.decode("ascii").split()
    require(bool(tokens) and all(re.fullmatch(r"-?[0-9]+", item) for item in tokens),
            "input must contain decimal integers")
    numbers = [int(item) for item in tokens]
    header = 2 if program in {"threshold_count", "fixed_point_filter"} else 1
    require(len(numbers) >= header, "missing count/threshold")
    count = numbers[1] if program == "fixed_point_filter" else numbers[0]
    threshold = numbers[0] if program == "fixed_point_filter" else numbers[1] if header == 2 else 0
    maximum = 64 if program in {"sum_u32", "dot_i32", "threshold_count", "histogram_count", "run_length", "rolling_hash"} else 32
    require(0 <= count <= maximum, "invalid element count")
    data = numbers[header:]
    require(len(data) == count * (2 if program == "dot_i32" else 1),
            "input token count differs from declared count")
    bounds = {
        "sum_u32": U32, "dot_i32": (-10000, 10000),
        "threshold_count": (-10000, 10000), "histogram_count": (0, 7),
        "run_length": (0, 15), "rolling_hash": (0, 255),
        "xor_checksum": U32, "lookup_switch": I32, "call_chain": I32,
        "state_machine": U32, "fixed_point_filter": I32, "bounded_parser": (0, 9),
    }
    bounded(data, bounds[program])
    if header == 2:
        bounded([threshold], (-10000, 10000) if program == "threshold_count" else I32)
    if program == "sum_u32":
        return sum(data) % 2**32
    if program == "dot_i32":
        return sum(a * b for a, b in zip(data[:count], data[count:]))
    if program == "threshold_count":
        return count - sum(value < threshold for value in data)
    if program == "histogram_count":
        return count + sum(data)
    if program == "run_length":
        return max((len(list(group)) for _, group in groupby(data)), default=0)
    if program == "rolling_hash":
        # Polynomial evaluation, independent of the generator's iterative recurrence.
        return sum(value * pow(257, count - index - 1, 1000000007)
                   for index, value in enumerate(data)) % 1000000007
    if program == "xor_checksum":
        return reduce(xor, (value for value, frequency in Counter(data).items()
                            if frequency % 2), 0)
    if program == "lookup_switch":
        frequencies = Counter(data)
        return -count + 4 * frequencies[0] + 6 * frequencies[1] + 8 * frequencies[2]
    if program == "call_chain":
        # Check each C int32 intermediate, not only the final mathematical sum.
        total = 0
        for value in data:
            square = value**2
            term = value * (value - 1)
            bounded([square, term, total + term], I32)
            total += term
        return total
    if program == "state_machine":
        transitions = ((1, 3, 1), (2, 0, 3), (3, 1, 1), (0, 2, 3))
        return reduce(lambda state, event: transitions[state][event] if event < 3 else state,
                      data, 0)
    if program == "fixed_point_filter":
        # Python // rounds down; C signed division truncates toward zero.
        selected = [3 * value for value in data if value >= threshold]
        return sum(value // 2 if value >= 0 else -((-value) // 2) for value in selected)
    if program == "bounded_parser":
        return int("".join(str(digit) for digit in data) or "0") % 1000003
    raise ValueError(f"unsupported program: {program}")


def audit(corpus_path: Path, root: Path) -> dict:
    raw = corpus_path.read_bytes()
    corpus = json.loads(raw)
    entries = corpus["entries"]
    ids = [entry["program_id"] for entry in entries]
    require(len(ids) == len(PROGRAMS) and set(ids) == PROGRAMS, "expected 12 distinct registered programs")
    assets: dict[str, str] = {}

    def checked(relative: str, expected: str) -> bytes:
        path = (root / relative).resolve()
        require(path.is_relative_to(root.resolve()), "asset escapes repository")
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        require(digest == expected, f"asset hash mismatch: {relative}")
        assets[relative] = digest
        return data

    checked(corpus["license_file"], corpus["license_sha256"])
    rows = []
    for entry in entries:
        checked(entry["source"], entry["source_sha256"])
        require(entry["license"] == "MIT", "unexpected corpus license metadata")
        case_ids = [case["case_id"] for case in entry["cases"]]
        require(len(case_ids) == 3 and len(set(case_ids)) == 3, "expected three distinct cases")
        results = []
        for case in entry["cases"]:
            stdin = checked(case["stdin"], case["stdin_sha256"])
            expected = checked(case["expected_stdout"], case["expected_stdout_sha256"])
            value = reference(entry["program_id"], stdin)
            require(expected == f"{value}\n".encode("ascii"),
                    f"oracle mismatch: {entry['program_id']}/{case['case_id']}")
            results.append({"case_id": case["case_id"], "mathematical_result": value})
        rows.append({"program_id": entry["program_id"], "split": entry["split"],
                     "family": entry["family"], "cases": results})
    families = {}
    for split in ("development", "held_out"):
        selected = [row for row in rows if row["split"] == split]
        families[split] = {row["family"] for row in selected}
        require(len(selected) == len(families[split]) == 6, "expected six distinct families per split")
    require(not families["development"] & families["held_out"], "family label overlap")
    require(len(assets) == 85, "expected 84 corpus assets and one license")
    return {"scope": "registered_input_numeric_and_oracle_audit", "is_mock": False,
            "corpus_sha256": hashlib.sha256(raw).hexdigest(),
            "checker_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "program_count": 12, "case_count": 36, "asset_count": len(assets),
            "asset_sha256": assets, "programs": rows,
            "limitations": ["No C compilation or QEMU execution in this audit",
                            "Family labels do not prove independent authorship or absence of holdout exposure",
                            "Numeric checks cover registered inputs, not arbitrary CLI inputs",
                            "No human identity or final M2 acceptance verification"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=ROOT / "evaluation/corpus.json")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = audit(args.corpus, ROOT)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("PASS: 12 programs, 36 exact-byte mathematical oracles, 85 asset hashes; registered inputs only")
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
