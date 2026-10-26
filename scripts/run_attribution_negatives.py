"""Exercise real ELF negative fixtures and record explicit attribution boundaries."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.analysis import AnalysisError, analyze_elf
from backend.app.execution import ProcessRunner
from backend.app.execution_types import ExecutionContext


def source_for(case: str) -> tuple[str, str]:
    symbol = "other" if case == "missing_symbol" else "kernel"
    section = ".init" if case == "outside_text" else ".text"
    body = {
        "unknown_16": ".2byte 0x0000",
        "unknown_32": ".4byte 0x0000000b",
        "conflicting_evidence": ".2byte 0x0001",
    }.get(case, ".option rvc\nli a0,0\n.option norvc\naddi a0,a0,1\n.option rvc\nret")
    return symbol, f"{section}\n.globl {symbol}\n.type {symbol},@function\n{symbol}:\n{body}\n.size {symbol},.-{symbol}\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cc = shutil.which("riscv64-linux-gnu-gcc") or "/usr/bin/riscv64-linux-gnu-gcc"
    rows = []
    with tempfile.TemporaryDirectory(prefix="optipilot-negative-") as directory:
        base = Path(directory)
        for case in ("unknown_16", "unknown_32", "missing_symbol", "outside_text", "conflicting_evidence"):
            symbol, source_text = source_for(case)
            assembly = base / f"{case}.S"
            elf = base / f"{case}.elf"
            assembly.write_text(source_text, encoding="utf-8")
            context = ExecutionContext(base, time.monotonic() + 60)
            result = ProcessRunner(context).run([
                cc, "-march=rv64gc", "-mabi=lp64d", "-nostdlib", "-static", "-no-pie",
                f"-Wl,-e,{symbol}", str(assembly), "-o", str(elf),
            ], cwd=base, timeout_s=20, max_output_bytes=1048576)
            status = "compile_error"
            reason = result.stderr.decode("utf-8", errors="replace")
            if result.status == "completed" and result.exit_code == 0:
                try:
                    analysis = analyze_elf(elf, context=context)
                    status = analysis.status
                    reason = analysis.reason
                except AnalysisError as error:
                    status = "analysis_error"
                    reason = str(error)
            rows.append({"case": case, "status": status, "reason": reason})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    document = {"is_mock": False, "cases": rows, "all_rejected": all(row["status"] != "passed" for row in rows)}
    args.output.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"cases": len(rows), "all_rejected": document["all_rejected"]}, ensure_ascii=False))
    return 0 if document["all_rejected"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
