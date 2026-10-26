"""CLI-facing orchestration from execution records to the stable result schema."""

from __future__ import annotations

from pathlib import Path
import json
from typing import Mapping, Any

from backend.app.analysis import AnalysisError, AnalysisResult, analyze_elf
from backend.app.execution import execute, experiment_session
from backend.app.execution.engine import atomic_json
from backend.app.execution_types import (
    CaseExecution, ExecutionBundle, ExecutionContext, ExecutionError,
    ExecutionRequest, VariantExecution,
)
from backend.app.selection import select_candidate, validate_baseline_policy


def _text(data: bytes) -> str:
    return data.decode("utf-8", errors="replace")


def _failed_analysis(error: AnalysisError) -> AnalysisResult:
    return AnalysisResult(
        "analysis_error", str(error), None, None,
        {"error_code": error.code, **error.details},
    )


def _analysis_variant(
    variant: VariantExecution,
    analysis: AnalysisResult | None,
) -> dict[str, Any]:
    diagnostics = (
        f"compile_status={variant.compilation.status} "
        f"compile_exit_code={variant.compilation.exit_code}"
    )
    compile_stderr = _text(variant.compilation.stderr)
    if compile_stderr:
        diagnostics += "\n" + compile_stderr
    status: str = variant.status
    metrics = None
    disassembly = None
    evidence: Mapping[str, Any] = {}
    analysis_argv: list[list[str]] = []

    if variant.status == "execution_passed":
        if analysis is None:
            status = "analysis_error"
            diagnostics = (diagnostics + "\nAnalysis was not run").strip()
        elif analysis.status == "passed":
            status = "passed"
            metrics = analysis.metrics
            disassembly = analysis.kernel_disassembly
            evidence = analysis.evidence
        else:
            status = "analysis_error"
            diagnostics = (diagnostics + "\n" + (analysis.reason or "Static analysis failed")).strip()
            evidence = analysis.evidence

        raw_argv = evidence.get("analysis_argv", [])
        if isinstance(raw_argv, list):
            analysis_argv = raw_argv

    return {
        "optimization": variant.optimization,
        "status": status,
        "compile_argv": list(variant.compilation.argv),
        "run_argv": list(variant.run_argv) if variant.run_argv else None,
        "analysis_argv": analysis_argv,
        "diagnostics": diagnostics,
        "kernel_disassembly": disassembly,
        "metrics": metrics,
        "runs": [_run_document(run) for run in variant.runs],
    }


def _run_document(run: CaseExecution) -> dict[str, Any]:
    return {
        "case_id": run.case_id,
        "status": run.status,
        "exit_code": run.process.exit_code,
        "stdout": _text(run.process.stdout),
        "stderr": _text(run.process.stderr),
        "wall_time_ms": run.process.wall_time_ms,
    }


def assemble_result(
    bundle: ExecutionBundle,
    analyses: Mapping[str, AnalysisResult],
    *,
    baseline_policy: Mapping[str, Any],
) -> dict[str, Any]:
    """Convert internal execution/analysis records into experiment.schema.json."""
    validate_baseline_policy(baseline_policy)
    variants = [
        _analysis_variant(variant, analyses.get(variant.optimization))
        for variant in bundle.variants
    ]
    decision = select_candidate(variants)
    return {
        "schema_version": "0.1.0",
        "experiment_id": bundle.experiment_id,
        "is_mock": False,
        "created_at": bundle.created_at,
        "baseline_version": bundle.baseline_version,
        "baseline_config_sha256": bundle.baseline_config_sha256,
        "corpus_version": bundle.corpus_version,
        "benchmark_id": bundle.benchmark_id,
        "source_sha256": bundle.source_sha256,
        "inputs": [
            {
                "case_id": record.case_id,
                "stdin_sha256": record.stdin_sha256,
                "expected_stdout_sha256": record.expected_stdout_sha256,
            }
            for record in bundle.inputs
        ],
        "environment": bundle.environment,
        "variants": variants,
        "selection": decision.selection,
    }


def run_experiment(
    repo_root: Path,
    output_root: Path,
    benchmark_id: str,
    optimizations: tuple[str, ...],
    baseline_policy: Mapping[str, Any],
) -> tuple[dict[str, Any], Path, int]:
    """Run one real experiment and atomically save its result."""
    request = ExecutionRequest(benchmark_id, optimizations)
    with experiment_session(repo_root, output_root) as context:
        bundle = execute(request, repo_root=repo_root, context=context)
        analyses: dict[str, AnalysisResult] = {}

        for variant in bundle.variants:
            if variant.status != "execution_passed" or variant.elf_path is None:
                continue
            try:
                analyses[variant.optimization] = analyze_elf(
                    variant.elf_path,
                    context=context,
                    symbol=bundle.kernel_symbol,
                )
            except AnalysisError as error:
                if error.code != "ANALYSIS_ERROR":
                    raise ExecutionError(error.code, str(error), **error.details) from error
                analyses[variant.optimization] = _failed_analysis(error)

        result = assemble_result(
            bundle, analyses, baseline_policy=baseline_policy,
        )
        result_path = context.workspace / "result.json"
        atomic_json(result_path, result)
        code = 0 if all(item["status"] == "passed" for item in result["variants"]) else 3
        return result, result_path, code


def load_baseline(repo_root: Path) -> dict[str, Any]:
    path = repo_root / "config" / "baseline.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ExecutionError("INVALID_REQUEST", "Unable to load baseline configuration") from error
