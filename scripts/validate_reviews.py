"""Validate two independent M2 annotations and their adjudication.

This gate checks completeness, reviewer independence, artifact hashes and
objective GNU ELF facts. It never creates annotations or decides a reviewer
label on their behalf.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.elf_reference import inspect_elf


class ReviewError(ValueError):
    pass


def _load(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ReviewError(f"Unable to read review file: {path}") from error
    if not isinstance(value, dict):
        raise ReviewError(f"Review file must be an object: {path}")
    return value


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ReviewError(message)


def _corpus_ids(corpus_path: Path) -> list[str]:
    corpus = _load(corpus_path)
    entries = corpus.get("entries")
    _require(corpus.get("status") == "frozen", "Review requires a machine-frozen corpus")
    _require(isinstance(entries, list) and len(entries) == 12, "Review requires exactly 12 frozen programs")
    ids = [entry.get("program_id") for entry in entries]
    _require(all(isinstance(item, str) and item for item in ids) and len(set(ids)) == 12,
             "Corpus program IDs must be unique")
    return sorted(ids)


def _validate_shape(document: dict, ids: list[str], label: str) -> None:
    _require(document.get("schema_version") == "0.1.0", f"{label}: unsupported schema version")
    reviewer = document.get("reviewer_id")
    _require(isinstance(reviewer, str) and reviewer.strip(), f"{label}: reviewer_id is required")
    _require(re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(document.get("review_date", ""))) is not None,
             f"{label}: review_date must be YYYY-MM-DD")
    independent = document.get("independent_from")
    _require(isinstance(independent, list) and independent and reviewer not in independent,
             f"{label}: independence declaration is invalid")
    programs = document.get("programs")
    _require(isinstance(programs, list), f"{label}: programs must be a list")
    observed = [item.get("program_id") for item in programs if isinstance(item, dict)]
    _require(sorted(observed) == ids and len(observed) == len(set(observed)),
             f"{label}: program set does not exactly match corpus")
    for item in programs:
        profiles = item.get("profiles")
        _require(isinstance(profiles, dict) and set(profiles) == {"O0", "O2", "Os"},
                 f"{label}/{item.get('program_id')}: O0/O2/Os annotations are required")
        for profile, annotation in profiles.items():
            _require(isinstance(annotation, dict), f"{label}/{item['program_id']}/{profile}: invalid annotation")
            _require(annotation.get("kernel_end", 0) > annotation.get("kernel_start", -1),
                     f"{label}/{item['program_id']}/{profile}: invalid kernel range")
            _require(annotation.get("r001") in {"verified", "abstained", "not_applicable"}
                     and annotation.get("r002") in {"verified", "abstained", "not_applicable"},
                     f"{label}/{item['program_id']}/{profile}: rule labels are required")
            _require(isinstance(annotation.get("evidence"), list) and annotation["evidence"],
                     f"{label}/{item['program_id']}/{profile}: evidence locations are required")


def _validate_adjudication(document: dict, ids: list[str], reviewer_ids: set[str]) -> None:
    _require(document.get("schema_version") == "0.1.0", "Adjudication schema version is unsupported")
    _require(set(document.get("reviewer_ids", [])) == reviewer_ids,
             "Adjudication must name exactly the two independent reviewers")
    decisions = document.get("decisions")
    _require(isinstance(decisions, list), "Adjudication decisions are required")
    expected = {(program, profile) for program in ids for profile in ("O0", "O2", "Os")}
    observed = {(item.get("program_id"), item.get("profile")) for item in decisions if isinstance(item, dict)}
    _require(observed == expected, "Adjudication must cover every program/profile pair")
    for item in decisions:
        _require(item.get("final_r001") in {"verified", "abstained", "not_applicable"}
                 and item.get("final_r002") in {"verified", "abstained", "not_applicable"},
                 "Adjudication has an invalid final rule label")
        _require(isinstance(item.get("reason"), str) and item["reason"].strip(),
                 "Every adjudication decision needs a reason")
    signoffs = document.get("signoffs")
    _require(isinstance(signoffs, list) and set(signoffs) == reviewer_ids,
             "Both reviewers must sign the adjudication")


def validate_reviews(corpus_path: Path, batch_path: Path, review_a: Path, review_b: Path,
                     adjudication: Path) -> dict:
    ids = _corpus_ids(corpus_path)
    first, second = _load(review_a), _load(review_b)
    _validate_shape(first, ids, "reviewer_a")
    _validate_shape(second, ids, "reviewer_b")
    _require(first["reviewer_id"] != second["reviewer_id"], "Reviewers must be different people")
    _require(first.get("batch_id") == second.get("batch_id"), "Reviews must target the same batch")
    batch = _load(batch_path)
    _require(batch.get("batch_id") == first.get("batch_id"), "Review batch_id does not match batch.json")
    _require(batch.get("completed") and batch.get("all_passed"), "Review requires a completed successful batch")
    _validate_adjudication(_load(adjudication), ids, {first["reviewer_id"], second["reviewer_id"]})

    rows = {entry["program_id"]: entry for entry in batch.get("programs", [])}
    _require(set(rows) == set(ids), "Batch does not contain every reviewed program")
    for reviewer in (first, second):
        for program in reviewer["programs"]:
            result = Path(rows[program["program_id"]]["result_path"])
            for profile, annotation in program["profiles"].items():
                elf = result.parent / profile / "program.elf"
                _require(_sha(elf) == annotation["elf_sha256"],
                         f"{reviewer['reviewer_id']}/{program['program_id']}/{profile}: ELF hash mismatch")
                metrics, _ = inspect_elf(elf)
                for field in ("text_section_bytes", "kernel_code_bytes"):
                    if field == "kernel_code_bytes":
                        expected = metrics[field]
                        observed = annotation["kernel_end"] - annotation["kernel_start"]
                    else:
                        expected = metrics[field]
                        observed = annotation[field]
                    _require(expected == observed, f"{reviewer['reviewer_id']}/{program['program_id']}/{profile}: {field} mismatch")
                _require(annotation["instructions_16"] == metrics["kernel_compressed_instruction_count"],
                         f"{reviewer['reviewer_id']}/{program['program_id']}/{profile}: compressed count mismatch")
                _require(annotation["instructions_16"] + annotation["instructions_32"] == metrics["kernel_static_instruction_count"],
                         f"{reviewer['reviewer_id']}/{program['program_id']}/{profile}: instruction count mismatch")
    return {"reviewers": [first["reviewer_id"], second["reviewer_id"]], "program_count": len(ids),
            "profile_count": len(ids) * 3, "adjudication_count": len(ids) * 3,
            "machine_evidence_checked": True, "human_signoff_checked": True}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--batch", type=Path, required=True)
    parser.add_argument("--review-a", type=Path, required=True)
    parser.add_argument("--review-b", type=Path, required=True)
    parser.add_argument("--adjudication", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = validate_reviews(args.corpus.resolve(), args.batch.resolve(), args.review_a.resolve(),
                                  args.review_b.resolve(), args.adjudication.resolve())
    except (OSError, ReviewError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 3
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
