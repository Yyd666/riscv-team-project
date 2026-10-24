"""Check repository assets without compiling or running benchmark C code."""

from __future__ import annotations

import copy
import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote

try:
    from jsonschema import Draft202012Validator, FormatChecker
except ImportError:
    sys.exit("Install foundation dependencies: python -m pip install -r requirements-foundation.txt")


ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def asset(relative: str) -> Path:
    path = (ROOT / relative).resolve()
    require(path.is_relative_to(ROOT), f"Path escapes repository: {relative}")
    require(path.is_file(), f"Missing file: {relative}")
    return path


def load_json(relative: str) -> dict:
    return json.loads(asset(relative).read_text(encoding="utf-8"))


def digest(relative: str) -> str:
    return hashlib.sha256(asset(relative).read_bytes()).hexdigest()


def expected_output(benchmark_id: str, data: bytes) -> bytes:
    values = [int(token) for token in data.split()]
    require(bool(values), f"Empty input file: {benchmark_id}")
    count = values[0]
    require(0 <= count <= 64, f"Invalid count: {benchmark_id}")
    if benchmark_id == "sum_u32":
        items = values[1:]
        require(len(items) == count, "sum_u32 input length")
        require(all(0 <= item <= 0xFFFFFFFF for item in items), "sum_u32 range")
        result = sum(items) % (1 << 32)
    elif benchmark_id == "dot_i32":
        require(len(values) == 1 + 2 * count, "dot_i32 input length")
        require(all(-10000 <= item <= 10000 for item in values[1:]), "dot_i32 range")
        left, right = values[1:1 + count], values[1 + count:]
        result = sum(a * b for a, b in zip(left, right))
    elif benchmark_id == "threshold_count":
        require(len(values) == 2 + count, "threshold_count input length")
        require(all(-10000 <= item <= 10000 for item in values[1:]), "threshold_count range")
        threshold = values[1]
        result = sum(item >= threshold for item in values[2:])
    else:
        raise ValueError(f"Add an independent oracle for new benchmark: {benchmark_id}")
    return f"{result}\n".encode("utf-8")


def check_baseline(config: dict) -> None:
    require(config["schema_version"] == "0.1.0", "Unexpected config schema version")
    require(config["target"] == {
        "isa": "rv64gc", "abi": "lp64d", "triplet": "riscv64-linux-gnu", "qemu_cpu": "rv64"
    }, "Target change requires updating the baseline checks and decision record")
    require(config["profiles"] == {"O0": ["-O0"], "O2": ["-O2"], "Os": ["-Os"]}, "Profile policy drift")
    require(config["selection"]["require_all_cases_pass"] is True, "Correctness gate is mandatory")
    require(config["selection"]["objective"] == "min_text_section_bytes", "Unexpected selection objective")
    require(config["selection"]["tie_break_order"] == ["O2", "Os", "O0"], "Unexpected tie break")
    flags = config["common_compile_flags"]
    require(flags == ["-std=c11", "-Wall", "-Wextra", "-Werror", "-static", "-fno-pie", "-no-pie", "-march=rv64gc", "-mabi=lp64d"], "Common flag policy drift; update decision record and baseline guards together")
    require(config["tools"] == {
        "cc": "riscv64-linux-gnu-gcc", "objdump": "riscv64-linux-gnu-objdump",
        "readelf": "riscv64-linux-gnu-readelf", "size": "riscv64-linux-gnu-size",
        "qemu": "qemu-riscv64"
    }, "Tool policy drift")
    require(config["unsupported_metrics"] == ["dynamic_instruction_count", "target_cycles"], "Unmeasured metrics must remain explicit")
    require(config["timing"] == {"runs_per_case": 1, "purpose": "host_diagnostics_only"}, "Timing policy drift")
    require(all(value > 0 for value in config["limits"].values()), "Limits must be positive")


def check_corpus(manifest: dict) -> tuple[dict, int]:
    programs = manifest["benchmarks"]
    ids = [program["id"] for program in programs]
    require(len(ids) == len(set(ids)), "Duplicate benchmark ID")
    require(set(ids) == {"sum_u32", "dot_i32", "threshold_count"}, "Update checks when extending corpus")
    count = 0
    for program in programs:
        source = asset(program["source"]).read_text(encoding="utf-8")
        require("kernel(" in source and "noinline" in source, f"Kernel not identifiable: {program['id']}")
        require(program["kernel_symbol"] == "kernel", "Unexpected kernel symbol")
        require(program["expected_exit_code"] == 0 and program["expected_stderr"] == "", "Unexpected success policy")
        case_ids = [case["id"] for case in program["cases"]]
        require(len(case_ids) == len(set(case_ids)) and len(case_ids) >= 3, "Need distinct baseline cases")
        for case in program["cases"]:
            input_bytes = asset(case["stdin"]).read_bytes()
            actual = asset(case["stdout"]).read_bytes()
            require(b"\r" not in input_bytes + actual, f"Use LF for fixtures: {case}")
            require(input_bytes.endswith(b"\n"), f"Missing final newline: {case['stdin']}")
            require(actual == expected_output(program["id"], input_bytes), f"Oracle mismatch: {case['stdout']}")
            count += 1
    return {program["id"]: program for program in programs}, count


def check_mock(document: dict, programs: dict, manifest: dict, config: dict) -> None:
    require(document["is_mock"] is True, "Example must remain explicitly mock")
    require(document["baseline_version"] == config["baseline_version"], "Mock baseline version drift")
    require(document["corpus_version"] == manifest["corpus_version"], "Mock corpus version drift")
    require(document["baseline_config_sha256"] == digest("config/baseline.json"), "Mock config hash drift")
    program = programs[document["benchmark_id"]]
    require(document["source_sha256"] == digest(program["source"]), "Mock source hash drift")
    expected_inputs = [{
        "case_id": case["id"],
        "stdin_sha256": digest(case["stdin"]),
        "expected_stdout_sha256": digest(case["stdout"]),
    } for case in program["cases"]]
    require(document["inputs"] == expected_inputs, "Mock input hashes/order drift")
    profile_ids = [variant["optimization"] for variant in document["variants"]]
    require(len(profile_ids) == len(set(profile_ids)), "Duplicate variant")
    passed = []
    for variant in document["variants"]:
        if variant["status"] != "compile_error":
            require([run["case_id"] for run in variant["runs"]] == [case["id"] for case in program["cases"]], "Mock run order drift")
        for run, case in zip(variant["runs"], program["cases"]):
            if run["status"] == "passed":
                require(run["stdout"].encode("utf-8") == asset(case["stdout"]).read_bytes(), "Passing mock output mismatch")
                require(run["stderr"] == program["expected_stderr"] and run["exit_code"] == program["expected_exit_code"], "Passing mock exit/stderr mismatch")
        if variant["status"] == "passed":
            metrics = variant["metrics"]
            static = metrics["kernel_static_instruction_count"]
            compressed = metrics["kernel_compressed_instruction_count"]
            require(compressed <= static, "Compressed count exceeds total")
            require(metrics["kernel_code_bytes"] == 2 * compressed + 4 * (static - compressed), "RV64GC kernel byte/count mismatch")
            require(metrics["kernel_code_bytes"] <= metrics["text_section_bytes"] <= metrics["elf_file_bytes"], "Size metric order mismatch")
            passed.append(variant)
    if passed:
        priority = config["selection"]["tie_break_order"]
        winner = min(passed, key=lambda item: (item["metrics"]["text_section_bytes"], priority.index(item["optimization"])))
        require(document["selection"] is not None and document["selection"]["optimization"] == winner["optimization"], "Mock recommendation mismatch")
    else:
        require(document["selection"] is None, "Failed experiment cannot recommend")


def check_links() -> int:
    documents = [ROOT / "README.md", ROOT / "AGENTS.md", ROOT / "CONTRIBUTING.md"]
    documents += list((ROOT / "docs").glob("*.md")) + [ROOT / "benchmarks/README.md"]
    count = 0
    for document in documents:
        text = document.read_text(encoding="utf-8")
        for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", text):
            target = target.split("#", 1)[0]
            if not target or "://" in target or target.startswith("mailto:"):
                continue
            path = (document.parent / unquote(target)).resolve()
            require(path.is_relative_to(ROOT) and path.exists(), f"Broken link in {document.name}: {target}")
            count += 1
    return count


def check_schema_guards(validator: Draft202012Validator, example: dict) -> None:
    invalid = copy.deepcopy(example)
    invalid["variants"][0]["metrics"]["target_cycles"] = 0
    require(not validator.is_valid(invalid), "Schema must reject invented cycle measurements")
    invalid = copy.deepcopy(example)
    del invalid["is_mock"]
    require(not validator.is_valid(invalid), "Schema must require explicit provenance flag")
    invalid = copy.deepcopy(example)
    invalid["variants"][0]["status"] = "compile_error"
    require(not validator.is_valid(invalid), "Schema must reject success metrics on failed compilation")
    invalid = copy.deepcopy(example)
    invalid["created_at"] = "not-a-date"
    require(not validator.is_valid(invalid), "Schema must validate timestamps")


def main() -> None:
    config = load_json("config/baseline.json")
    manifest = load_json("benchmarks/manifest.json")
    check_baseline(config)
    programs, cases = check_corpus(manifest)
    schema = load_json("contracts/experiment.schema.json")
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    request_schema = load_json("contracts/experiment-request.schema.json")
    Draft202012Validator.check_schema(request_schema)
    request_validator = Draft202012Validator(request_schema)
    request_validator.validate({"benchmark_id": "sum_u32", "optimizations": ["O0", "O2", "Os"]})
    for request in [
        {"benchmark_id": "sum_u32", "optimizations": ["O2", "O2"]},
        {"benchmark_id": "sum_u32", "optimizations": ["-O2; echo bad"]},
        {"benchmark_id": "sum_u32", "optimizations": ["O2"], "source": "unregistered"},
    ]:
        require(not request_validator.is_valid(request), "Request schema must reject duplicate/free flags or extra fields")
    mocks = sorted((ROOT / "contracts/examples").glob("experiment*.mock.json"))
    require(len(mocks) >= 2, "Need passing and failing experiment mocks")
    for mock in mocks:
        document = json.loads(mock.read_text(encoding="utf-8"))
        validator.validate(document)
        check_mock(document, programs, manifest, config)
    example = load_json("contracts/examples/experiment.mock.json")
    check_schema_guards(validator, example)
    listing = load_json("contracts/examples/benchmarks.mock.json")
    require(listing["is_mock"] is True and listing["schema_version"] == "0.1.0", "List mock provenance/version missing")
    expected_listing = [{"id": program["id"], "name": program["name"], "description": program["description"], "case_ids": [case["id"] for case in program["cases"]]} for program in manifest["benchmarks"]]
    require(listing["benchmarks"] == expected_listing, "Benchmark list mock drift")
    links = check_links()
    print(f"PASS: {len(programs)} programs, {cases} fixture oracles, {len(mocks)} experiment mocks, schema guards, {links} local links")
    print("Scope: foundation assets only; no C compilation, QEMU execution, or performance validation.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        sys.exit(1)
