"""Render diagnostic evaluation statistics without overstating acceptance."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import tempfile


def cell(value):
    return "—" if value is None else str(value).replace("|", "\\|").replace("\n", " ")


def render(summary: dict) -> str:
    metrics = summary["metrics"]
    if summary.get("schema_version") != "0.2.0":
        raise ValueError("Regenerate the evaluation summary with independent ELF checks (schema 0.2.0)")
    lines = ["# OptiPilot 评估核验报告", "",
             f"> 自动核验通过：{summary.get('automated_checks_passed')}；M2 验收完成：{summary.get('acceptance_ready')}。",
             "> 此报告包含失败、缺失和无收益项；自动 GNU 对照不替代双人独立标注。", "",
             f"语料状态：`{summary['corpus_status']}`；清单 SHA-256：`{summary['corpus_sha256']}`。", "",
             "## 语料与分母", "",
             f"- 程序目标：开发 {summary['targets'].get('development')}，留出 {summary['targets'].get('held_out')}。",
             f"- 观测真实程序：{metrics['program_count']}；请求比较：{metrics['comparison_count']}。",
             f"- 缺失/拒收程序：{', '.join(summary.get('missing_programs', [])) or '无'}。",
             f"- 比较状态计数：`{json.dumps(metrics['status_counts'], ensure_ascii=False)}`。", "",
             "## 独立核验指标", "", "| 指标 | 值 | 分母 |", "| --- | ---: | ---: |"]
    for name, key, denominator in (
        ("字节重建零误差率", "byte_error_exact_rate", "independent_byte_error_denominator"),
        ("规则有效率", "rule_validity_rate", "claimed_verified_rules"),
        ("R001 自动证据覆盖率", "r001_verified_rate", "independently_applicable_comparisons"),
        ("R002 自动证据覆盖率", "r002_coverage", "independently_applicable_comparisons"),
        ("拒判/缺失率", "rejection_rate", "comparison_count"),
        ("配置通过率", "configuration_pass_rate", "attempted_variants"),
        ("编译失败率", "compile_failure_rate", "attempted_variants"),
        ("用例失败率", "case_failure_rate", "executed_cases")):
        lines.append(f"| {name} | {cell(metrics.get(key))} | {cell(metrics.get(denominator))} |")
    lines.extend(["", f"用例超时：{metrics.get('timeout_cases', 0)}；相对 O2 零收益程序：{metrics.get('zero_gain_vs_O2_programs', 0)}；"
                  f"相对 Os 零收益程序：{metrics.get('zero_gain_vs_Os_programs', 0)}。", "",
                  "## B1/B2/B3 逐程序对照", "",
                  "B0 为重新执行 GNU 工具读取的 ELF 指标；以下三档推荐只使用通过正确性和静态核验的候选。", "",
                  "| 程序 | 划分 | O2 字节 | Os 字节 | 穷举最小字节 | 推荐 | 穷举差额字节 | 相对 O2 变化字节 | 相对 Os 变化字节 |",
                  "| --- | --- | ---: | ---: | ---: | --- | ---: | ---: | ---: |"])
    for row in summary.get("programs", []):
        lines.append("| " + " | ".join(cell(row.get(key)) for key in (
            "program_id", "split", "fixed_O2_bytes", "fixed_Os_bytes", "exhaustive_text_bytes",
            "selected_profile", "regret_bytes", "delta_vs_O2_bytes", "delta_vs_Os_bytes")) + " |")
    lines.extend(["", "## R001/R002 逐比较核对", "",
                  "| 程序 | 划分 | 候选 | 状态 | R001 输出 | R002 输出 | 独立字节误差 | 内部恒等式误差 |",
                  "| --- | --- | --- | --- | --- | --- | ---: | ---: |"])
    for row in summary.get("comparisons", []):
        lines.append("| " + " | ".join(cell(row.get(key)) for key in (
            "program_id", "split", "candidate_profile", "status", "r001_status", "r002_status",
            "byte_error", "internal_identity_error")) + " |")
    lines.extend(["", "## 验收缺口与原始结果索引", ""])
    for issue in summary.get("corpus_issues", []):
        lines.append(f"- 语料：{cell(issue)}")
    for issue in summary.get("input_errors", []):
        lines.append(f"- 输入/参考核验：{cell(issue)}")
    for row in summary.get("comparisons", []):
        if row.get("reason"):
            lines.append(f"- {row['program_id']} O2→{row['candidate_profile']}：{cell(row['reason'])}")
    for path in sorted({row["result_path"] for row in summary.get("comparisons", []) if row.get("result_path")}):
        lines.append(f"- 原始结果：`{path}`；同目录保存 ELF、执行记录和 sidecar。")
    lines.extend(["", "## 限制", ""])
    lines.extend(f"- {item}" for item in summary.get("limitations", []))
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.input.resolve() == args.output.resolve():
        parser.error("Report output must differ from its input summary")
    summary = json.loads(args.input.read_text(encoding="utf-8"))
    text = render(summary)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".evaluation-report-", dir=args.output.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, args.output)
    finally:
        Path(temporary).unlink(missing_ok=True)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
