"""Optional host-GCC smoke check; this does not validate RISC-V or QEMU."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def asset(relative: str) -> Path:
    path = (ROOT / relative).resolve()
    if not path.is_relative_to(ROOT) or not path.is_file():
        raise ValueError(f"Invalid corpus path: {relative}")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cc", default="gcc", help="Trusted local GCC executable (default: gcc)")
    args = parser.parse_args()
    compiler = shutil.which(args.cc)
    if compiler is None:
        raise ValueError(f"Compiler not found: {args.cc}; no tools have been installed")
    manifest = json.loads(asset("benchmarks/manifest.json").read_text(encoding="utf-8"))
    print(subprocess.run([compiler, "--version"], check=True, capture_output=True, text=True, timeout=5).stdout.splitlines()[0])
    runs = 0
    with tempfile.TemporaryDirectory(prefix="optilab-native-") as directory:
        work = Path(directory)
        for program in manifest["benchmarks"]:
            executable = work / (program["id"] + (".exe" if os.name == "nt" else ""))
            command = [compiler, "-std=c11", "-Wall", "-Wextra", "-Werror", "-O2", str(asset(program["source"])), "-o", str(executable)]
            built = subprocess.run(command, cwd=work, capture_output=True, timeout=20)
            if built.returncode != 0:
                raise ValueError(f"Native compile failed: {program['id']}, exit={built.returncode}\nstdout: {built.stdout.decode(errors='replace')}\nstderr: {built.stderr.decode(errors='replace')}")
            for case in program["cases"]:
                result = subprocess.run([str(executable)], input=asset(case["stdin"]).read_bytes(), capture_output=True, cwd=work, timeout=3)
                # The MSVCRT text stream emits CRLF on Windows; this host-only
                # adapter does not change strict byte matching in the Linux API.
                stdout = result.stdout.replace(b"\r\n", b"\n") if os.name == "nt" else result.stdout
                expected = asset(case["stdout"]).read_bytes()
                if (result.returncode != program["expected_exit_code"] or
                        stdout != expected or
                        result.stderr != program["expected_stderr"].encode("utf-8")):
                    raise ValueError(f"Native case failed: {program['id']}/{case['id']}: exit={result.returncode}, stdout={result.stdout!r}, stderr={result.stderr!r}")
                runs += 1
    print(f"PASS: {len(manifest['benchmarks'])} host-GCC -O2 builds, {runs} fixture executions")
    print("Scope: native C smoke only; Windows output line endings are normalized. No RISC-V/QEMU validation.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        sys.exit(1)
