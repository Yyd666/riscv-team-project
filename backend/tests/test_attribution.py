"""Synthetic ELF fixtures exercise evidence gates; these are not measurements."""

import copy
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest

from backend.app.attribution import AttributionError, build_attribution, generate_attributions
from backend.app.reporting import ReportInputError, load_attribution


def fixture_elf(*, outside=False, unknown=False):
    names = b"\0.text\0.init\0.riscv.attributes\0.symtab\0.strtab\0.shstrtab\0"
    strings = b"\0kernel\0"
    code = bytes.fromhex("0100130500008280")  # c.nop; addi a0,zero,0; c.jr ra
    if unknown:
        code = bytes.fromhex("0100130500000000")
    chunks = [b"", code + b"\x01\x00" * 6, code, b"rv64i2p1_m2p0_a2p1_f2p2_d2p2_c2p0\0",
              bytes(24) + struct.pack("<IBBHQQ", 1, 0x12, 0, 2 if outside else 1,
                                     0x2000 if outside else 0x1000, len(code)), strings, names]
    blob = bytearray(64)
    sections = [(0,) * 10]
    for index, data in enumerate(chunks[1:], 1):
        name = [b"", b".text", b".init", b".riscv.attributes", b".symtab", b".strtab", b".shstrtab"][index]
        sections.append((names.index(name), [0, 1, 1, 0x70000003, 2, 3, 3][index],
                         6 if index in (1, 2) else 0,
                         {1: 0x1000, 2: 0x2000}.get(index, 0), len(blob), len(data),
                         5 if index == 4 else 0, 1 if index == 4 else 0, 1, 24 if index == 4 else 0))
        blob.extend(data)
    shoff = len(blob)
    for section in sections:
        blob.extend(struct.pack("<IIQQQQIIQQ", *section))
    blob[:16] = b"\x7fELF\x02\x01\x01" + bytes(9)
    struct.pack_into("<HHIQQQIHHHHHH", blob, 16, 2, 243, 1, 0x1000, 0, shoff, 5, 64, 56, 0, 64, 7, 6)
    section_index = 2 if outside else 1
    start = 0x2000 if outside else 0x1000
    symbols = f"  1: {start:016x} 8 FUNC GLOBAL DEFAULT {section_index} kernel\n"
    table = "".join(f" [{index:2d}] {name} PROGBITS {section[3]:016x} {section[4]:06x} {section[5]:06x} 00 AX 0 0 2\n"
                    for index, name, section in ((1, '.text', sections[1]), (2, '.init', sections[2])))
    disassembly = (f"{start:x}: 0001 c.addi zero,0\n{start+2:x}: 00000513 addi a0,zero,0\n"
                   + f"{start+6:x}: " + ("0000 .2byte 0\n" if unknown else "8082 c.jr ra\n"))
    return bytes(blob), symbols, table, disassembly


def experiment():
    return {
        "schema_version": "0.1.0", "experiment_id": "synthetic-evidence-test", "is_mock": True,
        "created_at": "2026-10-26T00:00:00Z", "baseline_version": "0.1.0",
        "baseline_config_sha256": "a" * 64, "corpus_version": "test", "benchmark_id": "sum_u32",
        "source_sha256": "b" * 64,
        "inputs": [{"case_id": "empty", "stdin_sha256": "c" * 64,
                    "expected_stdout_sha256": hashlib.sha256(b"0\n").hexdigest()}],
        "environment": {key: ("C" if key == "locale" else "test") for key in (
            "os", "kernel", "python_version", "compiler_version", "binutils_version", "qemu_version",
            "libc_version", "locale") } | {"qemu_cpu": "rv64"},
        "variants": [], "selection": {"objective": "min_text_section_bytes", "optimization": "O2", "evidence": "static_size_only"},
    }


def artifacts(folder, *, outside=False, unknown=False):
    result = experiment()
    for profile in ("O2", "O0"):
        elf, symbols, sections, disassembly = fixture_elf(outside=outside and profile == "O0", unknown=unknown and profile == "O0")
        root = folder / profile
        (root / "analysis").mkdir(parents=True)
        (root / "program.elf").write_bytes(elf)
        for name, data in (("readelf-symbols.txt", symbols), ("readelf-sections.txt", sections), ("objdump-kernel.txt", disassembly)):
            (root / "analysis" / name).write_text(data, encoding="utf-8")
        bad = (outside or unknown) and profile == "O0"
        result["variants"].append({
            "optimization": profile, "status": "analysis_error" if bad else "passed",
            "compile_argv": ["test-compiler"], "run_argv": ["test-runner"],
            "analysis_argv": [["test-binutils"]], "diagnostics": "synthetic test", "kernel_disassembly": disassembly,
            "metrics": None if bad else {"elf_file_bytes": len(elf), "text_section_bytes": 20, "kernel_code_bytes": 8,
                "kernel_static_instruction_count": 3, "kernel_compressed_instruction_count": 2,
                "dynamic_instruction_count": None, "target_cycles": None},
            "runs": [{"case_id": "empty", "status": "passed", "exit_code": 0, "stdout": "0\n", "stderr": "", "wall_time_ms": 1}],
        })
    return result


class AttributionTests(unittest.TestCase):
    def check(self, root, result):
        return build_attribution(result, json.dumps(result).encode(), root, "O0")

    def test_byte_matched_evidence_and_precise_locations(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = self.check(root, artifacts(root))
            self.assertEqual(result["status"], "complete")
            self.assertEqual(result["snapshots"]["candidate"]["instructions_16"], 2)
            self.assertEqual(result["deltas"]["outside_kernel_delta_bytes"], 0)
            self.assertTrue(all("kernel file bytes" in row["locator"] for row in result["evidence"]))
            self.assertEqual(result["snapshots"]["reference"]["known_padding_bytes"], 0)
            self.assertEqual(result["snapshots"]["candidate"]["known_padding_bytes"], 0)
            self.assertFalse(any(row["kind"] == "alignment_map" for row in result["evidence"]))

    def test_equally_small_function_in_another_section_is_not_applicable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = self.check(root, artifacts(root, outside=True))
            self.assertEqual(result["status"], "partial")
            self.assertEqual(result["rules"][1]["status"], "not_applicable")
            self.assertFalse(result["snapshots"]["candidate"]["inside_text"])
            self.assertIsNone(result["deltas"]["outside_kernel_delta_bytes"])

    def test_unknown_bytes_remain_partial_with_known_bounds(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = self.check(root, artifacts(root, unknown=True))
            self.assertEqual(result["status"], "partial")
            self.assertEqual(result["rules"][0]["status"], "abstained")
            self.assertEqual(result["snapshots"]["candidate"]["unclassified_bytes"], 2)

    def test_tampering_cannot_be_hidden_by_consistent_algebra(self):
        for artifact, content in (("program.elf", b"garbage"),
                                  ("analysis/readelf-symbols.txt", b"1: 00001000 9 FUNC GLOBAL DEFAULT 1 kernel\n"),
                                  ("analysis/readelf-sections.txt", b" [1] .text PROGBITS 1000 42 14 00 AX 0 0 2\n"),
                                  ("analysis/objdump-kernel.txt", b"1000: 0002 c.addi zero,0\n")):
            with self.subTest(artifact=artifact), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                experiment = artifacts(root)
                (root / "O0" / artifact).write_bytes(content)
                self.assertEqual(self.check(root, experiment)["status"], "unavailable")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            experiment = artifacts(root)
            experiment["variants"][1]["metrics"].update(kernel_code_bytes=12, kernel_static_instruction_count=4)
            self.assertEqual(self.check(root, experiment)["status"], "unavailable")

    def test_missing_evidence_does_not_verify_a_rule(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            experiment = artifacts(root)
            (root / "O0/analysis/objdump-kernel.txt").unlink()
            result = self.check(root, experiment)
            self.assertEqual(result["status"], "partial")
            self.assertEqual(result["rules"][0]["status"], "abstained")
            self.assertEqual(result["snapshots"]["candidate"]["unclassified_bytes"], 8)

    def test_all_unique_registered_cases_are_required(self):
        for kind in ("omitted", "duplicate", "wrong_output"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                experiment = artifacts(root)
                if kind == "omitted":
                    experiment["inputs"].append({**experiment["inputs"][0], "case_id": "second"})
                elif kind == "duplicate":
                    experiment["variants"][1]["runs"] *= 2
                else:
                    experiment["variants"][1]["runs"][0]["stdout"] = "wrong\n"
                self.assertEqual(self.check(root, experiment)["status"], "unavailable")

    def test_generate_requires_saved_result_and_at_least_one_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = artifacts(root)
            source = root / "result.json"
            source.write_text(json.dumps(result), encoding="utf-8")
            paths, complete = generate_attributions(source)
            self.assertTrue(complete)
            self.assertEqual(len(paths), 1)
            with self.assertRaises(AttributionError):
                generate_attributions(source, {**result, "experiment_id": "different"})
            result["variants"] = result["variants"][:1]
            source.write_text(json.dumps(result), encoding="utf-8")
            self.assertEqual(generate_attributions(source), ([], False))

    def test_real_sidecar_consumer_rejects_modified_delta_or_artifact(self):
        # A unit fixture sets the real-mode switch solely to exercise the consumer
        # gate. It is never passed to the evaluator or counted as a measurement.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = artifacts(root)
            result["is_mock"] = False
            (root / "source").mkdir()
            (root / "source/main.c").write_bytes(b"unit fixture source")
            (root / "baseline.json").write_bytes(b"unit fixture baseline")
            result["source_sha256"] = hashlib.sha256(b"unit fixture source").hexdigest()
            result["baseline_config_sha256"] = hashlib.sha256(b"unit fixture baseline").hexdigest()
            record = copy.deepcopy(result)
            for variant in record["variants"]:
                variant["status"] = "execution_passed"
                variant["elf_sha256"] = hashlib.sha256((root / variant["optimization"] / "program.elf").read_bytes()).hexdigest()
                analysis_dir = root / variant["optimization"] / "analysis"
                (analysis_dir / "record.json").write_text(json.dumps({
                    "elf_sha256": variant["elf_sha256"],
                    "artifact_sha256": {key: hashlib.sha256((analysis_dir / name).read_bytes()).hexdigest() for key, name in (
                        ("symbols", "readelf-symbols.txt"), ("sections", "readelf-sections.txt"), ("disassembly", "objdump-kernel.txt"))},
                }), encoding="utf-8")
                variant["runs"] = [{"case_id": run["case_id"], "status": run["status"], "process": run} for run in variant["runs"]]
            (root / "execution.json").write_text(json.dumps(record), encoding="utf-8")
            source = root / "result.json"
            source.write_text(json.dumps(result), encoding="utf-8")
            paths, _ = generate_attributions(source)
            raw = source.read_bytes()
            load_attribution(paths[0], result, raw, workspace=root)
            document = json.loads(paths[0].read_text())
            changed = copy.deepcopy(document)
            changed["deltas"]["kernel_delta_bytes"] += 4
            changed["deltas"]["instruction_count_term_bytes"] += 4
            paths[0].write_text(json.dumps(changed), encoding="utf-8")
            with self.assertRaises(ReportInputError):
                load_attribution(paths[0], result, raw, workspace=root)
            paths[0].write_text(json.dumps(document), encoding="utf-8")
            (root / "O0/analysis/readelf-symbols.txt").write_text("changed", encoding="utf-8")
            with self.assertRaises(ReportInputError):
                load_attribution(paths[0], result, raw, workspace=root)


if __name__ == "__main__":
    unittest.main()
