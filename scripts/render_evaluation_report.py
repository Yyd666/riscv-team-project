"""Render the frozen evaluation summary as a limitation-aware Markdown report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def render(summary: dict) -> str:
    metrics = summary.get("metrics", {})
    status = summary.get("corpus_status", "unknown")
    lines = [
        "# OptiPilot 独立评估报告",
        "",
        f"> 评估语料状态：`{status}`。本报告不把缺失样本当作零误差，也不提供因果或性能结论。",
        "",
        "## 语料与分母",
        "",
        f"- 观测程序数：{summary.get('program_count', len(summary.get('observed_programs', [])))}",
        f"- 开发集目标：{summary.get('targets', {}).get('development', '—')}",
        f"- 留出集目标：{summary.get('targets', {}).get('held_out', '—')}",
        f"- 比较对数量：{metrics.get('comparison_count', '—')}",
        "",
        "## 指标",
        "",
        "| 指标 | 值 | 分母说明 |",
        "| --- | ---: | --- |",
        f"| 字节重建精确率 | {metrics.get('byte_error_exact_rate', '—')} | 有字节误差记录的比较对 |",
        f"| R001 验证率 | {metrics.get('r001_verified_rate', '—')} | 全部请求比较对 |",
        f"| R002 覆盖率 | {metrics.get('r002_coverage', '—')} | R002 适用或拒判的比较对 |",
        f"| 拒判率 | {metrics.get('rejection_rate', '—')} | 全部请求比较对 |",
        "",
        "## 逐比较对记录",
        "",
        "| 程序 | 划分 | 候选 | 状态 | R001 | R002 | 字节误差 |",
        "| --- | --- | --- | --- | --- | --- | ---: |",
    ]
    for row in summary.get("comparisons", []):
        lines.append("| " + " | ".join(str(row.get(key, "—")) for key in ("program_id", "split", "candidate_profile", "status", "r001_status", "r002_status", "byte_error")) + " |")
    lines.extend(["", "## 限制", ""])
    lines.extend(f"- {item}" for item in summary.get("limitations", []))
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = json.loads(args.input.read_text(encoding="utf-8"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render(summary), encoding="utf-8", newline="\n")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
