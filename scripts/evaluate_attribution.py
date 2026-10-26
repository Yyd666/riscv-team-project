"""Evaluate frozen experiment/attribution sidecars without inventing missing measurements."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.reporting import load_attribution, load_result


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def evaluate(corpus_path: Path, artifacts_root: Path) -> dict[str, Any]:
    corpus_raw = corpus_path.read_bytes()
    corpus = json.loads(corpus_raw.decode("utf-8"))
    entries = corpus.get("entries", [])
    by_id = {entry["program_id"]: entry for entry in entries}
    comparisons: list[dict[str, Any]] = []
    missing_results: list[str] = []
    for result_path in sorted(artifacts_root.glob("**/result.json")):
        try:
            result = load_result(result_path)
        except Exception as error:
            comparisons.append({"result": str(result_path), "status": "invalid_result", "reason": str(error)})
            continue
        benchmark = str(result["benchmark_id"])
        entry = by_id.get(benchmark)
        if entry is None:
            continue
        raw = result_path.read_bytes()
        variants = {item["optimization"]: item for item in result["variants"]}
        for candidate in ("O0", "Os"):
            if candidate not in variants:
                continue
            sidecar = result_path.parent / "attribution" / f"O2-{candidate}" / "attribution.json"
            row: dict[str, Any] = {
                "program_id": benchmark,
                "split": entry["split"],
                "family": entry["family"],
                "candidate_profile": candidate,
                "result_path": str(result_path),
                "status": "missing_attribution",
                "byte_error": None,
                "r001_status": None,
                "r002_status": None,
            }
            if sidecar.is_file():
                try:
                    attribution = load_attribution(sidecar, result, raw)
                    row["status"] = attribution["status"]
                    row["r001_status"] = next(rule["status"] for rule in attribution["rules"] if rule["rule_id"] == "R001")
                    row["r002_status"] = next(rule["status"] for rule in attribution["rules"] if rule["rule_id"] == "R002")
                    deltas = attribution.get("deltas")
                    if isinstance(deltas, Mapping):
                        row["byte_error"] = deltas["kernel_delta_bytes"] - sum(
                            deltas[key] for key in ("instruction_count_term_bytes", "encoding_width_term_bytes", "unclassified_term_bytes")
                        )
                except Exception as error:
                    row["status"] = "invalid_attribution"
                    row["reason"] = str(error)
            comparisons.append(row)
    found_programs = {row["program_id"] for row in comparisons if row.get("status") in {"complete", "partial", "unavailable"}}
    valid_rows = [row for row in comparisons if row.get("byte_error") is not None]
    verified_r1 = [row for row in comparisons if row.get("r001_status") == "verified"]
    applicable_r2 = [row for row in comparisons if row.get("r002_status") in {"verified", "abstained"}]
    rejected = [row for row in comparisons if row.get("status") in {"partial", "unavailable", "missing_attribution", "invalid_attribution"}]
    return {
        "schema_version": "0.1.0",
        "is_mock": False,
        "corpus_sha256": _sha(corpus_path),
        "corpus_status": corpus.get("status"),
        "targets": {"development": corpus.get("development_target"), "held_out": corpus.get("held_out_target")},
        "observed_programs": sorted(found_programs),
        "comparisons": comparisons,
        "metrics": {
            "comparison_count": len(comparisons),
            "program_count": len(found_programs),
            "byte_error_exact_rate": (sum(row["byte_error"] == 0 for row in valid_rows) / len(valid_rows)) if valid_rows else None,
            "r001_verified_rate": (len(verified_r1) / len(comparisons)) if comparisons else None,
            "r002_coverage": (len([row for row in applicable_r2 if row.get("r002_status") == "verified"]) / len(applicable_r2)) if applicable_r2 else None,
            "rejection_rate": len(rejected) / len(comparisons) if comparisons else None,
        },
        "limitations": [
            "Only frozen corpus entries with real result.json and attribution sidecars are counted.",
            "Missing development/held-out entries remain missing and are not treated as zero-error measurements.",
            "No causal optimization-pass or performance claim is computed.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = evaluate(args.corpus.resolve(), args.artifacts.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["metrics"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
