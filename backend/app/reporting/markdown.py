"""Read-only Markdown reporting for completed experiment results."""

from __future__ import annotations

from collections.abc import Mapping
import json
import os
from pathlib import Path
import tempfile
from typing import Any

try:
    from jsonschema import Draft202012Validator, FormatChecker
except ImportError as error:  # pragma: no cover - dependency is in foundation requirements
    Draft202012Validator = None
    FormatChecker = None
    _JSONSCHEMA_IMPORT_ERROR = error

STATUSES = {
    "passed", "compile_error", "runtime_error", "wrong_answer",
    "timeout", "output_limit", "analysis_error",
}


class ReportInputError(ValueError):
    """The input is not a valid experiment result document."""


def _value(value: object) -> str:
    if value is None:
        return "—"
    return str(value).replace("|", "\\|").replace("\\n", " ").replace("\n", " ")


def _require_mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ReportInputError(f"{name} must be an object")
    return value



def _validate_schema(document: object) -> None:
    if Draft202012Validator is None:
        raise ReportInputError("jsonschema is required to validate experiment results") from _JSONSCHEMA_IMPORT_ERROR
    schema_path = Path(__file__).resolve().parents[3] / "contracts" / "experiment.schema.json"
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ReportInputError("Unable to load experiment result schema") from error
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(document), key=lambda item: list(item.path))
    if errors:
        location = ".".join(str(part) for part in errors[0].path) or "<root>"
        raise ReportInputError(f"Invalid experiment result at {location}: {errors[0].message}")

def validate_result(document: object) -> Mapping[str, Any]:
    _validate_schema(document)
    root = _require_mapping(document, "result")
    required = {
        "schema_version", "experiment_id", "is_mock", "created_at",
        "baseline_version", "baseline_config_sha256", "corpus_version",
        "benchmark_id", "source_sha256", "inputs", "environment",
        "variants", "selection",
    }
    missing = sorted(required - set(root))
    if missing:
        raise ReportInputError("Missing result fields: " + ", ".join(missing))
    if root["schema_version"] != "0.1.0":
        raise ReportInputError("Unsupported result schema version")
    if not isinstance(root["is_mock"], bool):
        raise ReportInputError("is_mock must be boolean")
    if not isinstance(root["variants"], list) or not root["variants"]:
        raise ReportInputError("variants must be a non-empty list")
    seen: set[str] = set()
    for raw in root["variants"]:
        variant = _require_mapping(raw, "variant")
        profile = variant.get("optimization")
        if profile in seen:
            raise ReportInputError(f"Duplicate optimization profile: {profile}")
        seen.add(profile)
        if profile not in {"O0", "O2", "Os"}:
            raise ReportInputError(f"Unknown optimization profile: {profile}")
        if variant.get("status") not in STATUSES:
            raise ReportInputError(f"Unknown variant status: {variant.get('status')}")
        metrics = variant.get("metrics")
        if metrics is not None and not isinstance(metrics, Mapping):
            raise ReportInputError(f"metrics must be object or null for {profile}")
        if variant["status"] == "passed" and metrics is None:
            raise ReportInputError(f"passed variant has no metrics: {profile}")
        if not isinstance(variant.get("runs"), list):
            raise ReportInputError(f"runs must be a list for {profile}")
    selection = root["selection"]
    if selection is not None:
        selection = _require_mapping(selection, "selection")
        if selection.get("objective") != "min_text_section_bytes":
            raise ReportInputError("Unsupported selection objective")
        if selection.get("optimization") not in {"O0", "O2", "Os"}:
            raise ReportInputError("Invalid selected optimization")
        if selection.get("evidence") != "static_size_only":
            raise ReportInputError("Unsupported selection evidence")
    return root


def load_result(path: Path) -> Mapping[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ReportInputError(f"Experiment file does not exist: {path}") from error
    except (OSError, json.JSONDecodeError) as error:
        raise ReportInputError(f"Unable to read experiment JSON: {path}") from error
    return validate_result(document)


def _metrics(variant: Mapping[str, Any], key: str) -> object:
    metrics = variant.get("metrics")
    return metrics.get(key) if isinstance(metrics, Mapping) else None


def render_report(document: Mapping[str, Any], *, source_path: Path | None = None) -> str:
    result = validate_result(document)
    mock_label = "合成演示数据（is_mock=true）" if result["is_mock"] else "真实实验记录（is_mock=false）"
    selection = result["selection"]
    lines = [
        "# OptiPilot 实验报告",
        "",
        f"> {mock_label}。本报告只读取已有 result.json，不重新执行实验。",
        "",
        "## 实验概览",
        "",
        "| 字段 | 值 |",
        "| --- | --- |",
        f"| 实验 ID | {_value(result['experiment_id'])} |",
        f"| 样例 | {_value(result['benchmark_id'])} |",
        f"| 创建时间 | {_value(result['created_at'])} |",
        f"| 基线版本 | {_value(result['baseline_version'])} |",
        f"| 语料版本 | {_value(result['corpus_version'])} |",
        f"| 输入数量 | {_value(len(result['inputs']))} |",
    ]
    if source_path is not None:
        lines.append(f"| 输入文件 | {_value(source_path)} |")
    lines.extend(["", "## 有限候选推荐", ""])
    if selection is None:
        lines.append("没有通过正确性和静态分析门控的可推荐方案。")
    else:
        lines.extend([
            f"- 推荐配置：**{selection['optimization']}**",
            f"- 目标：{selection['objective']}",
            f"- 证据：{selection['evidence']}",
        ])
    lines.extend([
        "",
        "## 方案结果",
        "",
        "| 配置 | 状态 | .text 字节 | kernel 字节 | 静态指令数 | 压缩指令数 |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ])
    for raw in result["variants"]:
        variant = _require_mapping(raw, "variant")
        lines.append(
            f"| {_value(variant['optimization'])} | {_value(variant['status'])} | "
            f"{_value(_metrics(variant, 'text_section_bytes'))} | "
            f"{_value(_metrics(variant, 'kernel_code_bytes'))} | "
            f"{_value(_metrics(variant, 'kernel_static_instruction_count'))} | "
            f"{_value(_metrics(variant, 'kernel_compressed_instruction_count'))} |"
        )
    lines.extend(["", "## 运行与诊断", ""])
    for raw in result["variants"]:
        variant = _require_mapping(raw, "variant")
        profile = variant["optimization"]
        lines.extend([f"### {profile}", "", f"- 状态：{variant['status']}"])
        diagnostics = variant.get("diagnostics")
        if diagnostics:
            lines.extend(["- 诊断：", "", "~~~text", str(diagnostics), "~~~"])
        analysis_argv = variant.get("analysis_argv") or []
        if analysis_argv:
            lines.extend(["- 分析命令：", ""])
            for argv in analysis_argv:
                lines.append("  - " + " ".join(str(item) for item in argv))
        runs = variant.get("runs") or []
        if runs:
            lines.extend(["", "| 用例 | 状态 | 退出码 | 宿主耗时（诊断） |", "| --- | --- | ---: | ---: |"])
            for run in runs:
                run_map = _require_mapping(run, "run")
                lines.append(
                    f"| {_value(run_map.get('case_id'))} | {_value(run_map.get('status'))} | "
                    f"{_value(run_map.get('exit_code'))} | {_value(run_map.get('wall_time_ms'))} |"
                )
    lines.extend([
        "",
        "## 结论边界",
        "",
        "- 推荐只比较通过正确性门控的 O0/O2/Os 候选，依据是完整 .text 静态节大小。",
        "- wall_time_ms 只作宿主诊断，不作为性能排名依据。",
        "- 静态指令数不等于动态执行数量，QEMU 宿主耗时不等于目标硬件性能。",
        "- 本报告不提供 R001/R002 函数级归因；归因结果属于 ATTR-01。",
        "- 初始语料和当前实验结果不能支持对一般 C 程序的普遍优化收益结论。",
        "",
    ])
    return "\n".join(lines)


def write_report(document: Mapping[str, Any], output: Path, *, source_path: Path | None = None) -> Path:
    text = render_report(document, source_path=source_path)
    output = output.resolve()
    if source_path is not None and output == source_path.resolve():
        raise ReportInputError("Report output must differ from the experiment JSON")
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".report-", dir=output.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, output)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return output
