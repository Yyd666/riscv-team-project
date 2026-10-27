import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts.elf_reference import inspect_elf
from scripts.validate_reviews import ReviewError, _validate_adjudication, _validate_shape, validate_reviews


IDS = [f"program_{index:02d}" for index in range(12)]


def review(reviewer):
    profiles = {
        profile: {
            "elf_sha256": "a" * 64, "text_section_bytes": 100,
            "kernel_start": 4096, "kernel_end": 4100, "section_index": 1,
            "instructions_16": 0, "instructions_32": 1, "unclassified_bytes": 0,
            "r001": "verified", "r002": "verified", "evidence": ["O2/program.elf"]
        }
        for profile in ("O0", "O2", "Os")
    }
    return {"schema_version": "0.1.0", "reviewer_id": reviewer,
            "review_date": "2026-10-26", "independent_from": ["other"],
            "batch_id": "evaluation-test", "programs": [
                {"program_id": program, "profiles": copy.deepcopy(profiles)} for program in IDS
            ]}


class ReviewGateTests(unittest.TestCase):
    def test_complete_independent_shapes_pass(self):
        first, second = review("alice"), review("bob")
        _validate_shape(first, IDS, "a")
        _validate_shape(second, IDS, "b")
        decisions = [{"program_id": program, "profile": profile,
                      "final_r001": "verified", "final_r002": "verified", "reason": "same bytes"}
                     for program in IDS for profile in ("O0", "O2", "Os")]
        _validate_adjudication({"schema_version": "0.1.0", "reviewer_ids": ["alice", "bob"],
                                "decisions": decisions, "signoffs": ["alice", "bob"]}, IDS, {"alice", "bob"})

    def test_missing_program_is_rejected(self):
        missing = review("bob")
        missing["programs"].pop()
        with self.assertRaises(ReviewError):
            _validate_shape(missing, IDS, "b")

    def test_schema_rejects_invalid_types_and_dates(self):
        for field, value in (("elf_sha256", "missing"), ("section_index", -1),
                             ("instructions_16", True), ("unclassified_bytes", "0"),
                             ("evidence", [17])):
            with self.subTest(field=field):
                document = review("alice")
                document["programs"][0]["profiles"]["O0"][field] = value
                with self.assertRaises(ReviewError):
                    _validate_shape(document, IDS, "a")
        document = review("alice")
        document["review_date"] = "2026-02-30"
        with self.assertRaises(ReviewError):
            _validate_shape(document, IDS, "a")

    def test_adjudication_requires_every_profile_and_reason(self):
        decisions = [{"program_id": program, "profile": profile,
                      "final_r001": "verified", "final_r002": "verified", "reason": "ok"}
                     for program in IDS for profile in ("O0", "O2", "Os")]
        decisions.pop()
        with self.assertRaises(ReviewError):
            _validate_adjudication({"schema_version": "0.1.0", "reviewer_ids": ["a", "b"],
                                    "decisions": decisions, "signoffs": ["a", "b"]}, IDS, {"a", "b"})


@unittest.skipUnless(sys.platform == "linux" and shutil.which("riscv64-linux-gnu-gcc"),
                     "Review evidence checks require Linux GNU RISC-V tools")
class ReviewEvidenceTests(unittest.TestCase):
    """Tiny real ELF fixtures test gate behavior, never M2 algorithm accuracy."""

    @classmethod
    def setUpClass(cls):
        cls.tools = tempfile.TemporaryDirectory(prefix="optipilot-review-tools-")
        cls.addClassCleanup(cls.tools.cleanup)
        root = Path(cls.tools.name)
        source, cls.elf = root / "kernel.S", root / "reference.elf"
        source.write_text(".option rvc\n.text\n.globl kernel\n.type kernel,@function\nkernel:\n"
                          "addi a0,a0,1\nret\n.size kernel,.-kernel\n", encoding="ascii")
        subprocess.run(["riscv64-linux-gnu-gcc", "-march=rv64gc", "-mabi=lp64d", "-static", "-nostdlib",
                        "-no-pie", "-Wl,-e,kernel", str(source), "-o", str(cls.elf)],
                       check=True, capture_output=True, timeout=30)
        cls.metrics, cls.disassembly = inspect_elf(cls.elf, include_boundaries=True)
        cls.outputs = {
            filename: subprocess.run(argv + [str(cls.elf)], check=True, capture_output=True, timeout=10).stdout
            for filename, argv in (
                ("readelf-symbols.txt", ["riscv64-linux-gnu-readelf", "-sW"]),
                ("readelf-sections.txt", ["riscv64-linux-gnu-readelf", "-SW"]),
                ("objdump-kernel.txt", ["riscv64-linux-gnu-objdump", "-d", "-M", "no-aliases,numeric", "--disassemble=kernel"]))}

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="optipilot-review-gate-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "evaluation-test"
        self.root.mkdir()
        self.corpus = self.root / "corpus.json"
        self.batch_path = self.root / "batch.json"
        self.first_path = self.root / "reviewer-alice.json"
        self.second_path = self.root / "reviewer-bob.json"
        self.adjudication_path = self.root / "adjudication.json"
        self.write(self.corpus, {"status": "frozen", "entries": [{"program_id": program} for program in IDS]})
        self.first, self.second = review("alice"), review("bob")
        self.first["independent_from"], self.second["independent_from"] = ["bob"], ["alice"]
        rows = []
        for index, program in enumerate(IDS):
            workspace = self.root / "experiments" / f"exec-{index}"
            self.write(workspace / "result.json", {"fixture": True, "benchmark_id": program, "is_mock": False,
                "variants": [{"optimization": profile, "status": "passed"} for profile in ("O0", "O2", "Os")]})
            for profile in ("O0", "O2", "Os"):
                folder = workspace / profile
                analysis = folder / "analysis"
                analysis.mkdir(parents=True)
                shutil.copyfile(self.elf, folder / "program.elf")
                for filename, data in self.outputs.items():
                    (analysis / filename).write_bytes(data)
                self.write(analysis / "record.json", {"status": "passed", "elf_sha256": self.sha(self.elf),
                    "artifact_sha256": {name: self.sha(analysis / filename) for name, filename in
                        (("symbols", "readelf-symbols.txt"), ("sections", "readelf-sections.txt"),
                         ("disassembly", "objdump-kernel.txt"))}})
                for document in (self.first, self.second):
                    annotation = document["programs"][index]["profiles"][profile]
                    annotation.update({key: self.metrics[key] for key in
                        ("text_section_bytes", "kernel_start", "kernel_end", "section_index", "unclassified_bytes")})
                    annotation.update(elf_sha256=self.sha(self.elf),
                        instructions_16=self.metrics["kernel_compressed_instruction_count"],
                        instructions_32=self.metrics["kernel_static_instruction_count"] - self.metrics["kernel_compressed_instruction_count"],
                        evidence=[str((folder / filename).relative_to(self.root)) for filename in
                            ("program.elf", "analysis/readelf-symbols.txt", "analysis/readelf-sections.txt", "analysis/objdump-kernel.txt")])
            rows.append({"program_id": program, "result_path": str(workspace / "result.json"),
                         "status": "passed", "exit_code": 0,
                         "variant_statuses": {profile: "passed" for profile in ("O0", "O2", "Os")}})
        self.batch = {"batch_id": "evaluation-test", "completed": True, "all_passed": True,
                      "is_mock": False, "mode": "formal", "corpus_status": "frozen", "exit_code": 0,
                      "corpus_sha256": self.sha(self.corpus), "programs": rows,
                      "artifact_sha256": {str(path.relative_to(self.root)): self.sha(path)
                                          for path in self.root.rglob("*") if path.is_file()}}
        self.adjudication = {"schema_version": "0.1.0", "reviewer_ids": ["alice", "bob"],
            "decisions": [{"program_id": program, "profile": profile,
                           "final_r001": "verified", "final_r002": "verified", "reason": "fixture byte check"}
                          for program in IDS for profile in ("O0", "O2", "Os")], "signoffs": ["alice", "bob"]}

    @staticmethod
    def sha(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    @staticmethod
    def write(path, document):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(document), encoding="utf-8")

    def validate(self, *, real_tools=False):
        for path, document in ((self.batch_path, self.batch), (self.first_path, self.first),
                               (self.second_path, self.second), (self.adjudication_path, self.adjudication)):
            self.write(path, document)
        args = (self.corpus, self.batch_path, self.first_path, self.second_path, self.adjudication_path)
        if real_tools:
            return validate_reviews(*args)
        with patch("scripts.validate_reviews.inspect_elf", return_value=(self.metrics, self.disassembly)):
            return validate_reviews(*args)

    def test_complete_package_with_fresh_gnu_does_not_certify_people(self):
        summary = self.validate(real_tools=True)
        self.assertEqual(summary["profile_count"], 36)
        self.assertTrue(summary["machine_evidence_checked"])
        self.assertTrue(summary["declared_signoffs_checked"])
        self.assertFalse(summary["human_identity_verified"])
        self.assertFalse(summary["acceptance_ready"])

    def test_shifted_equal_length_range_wrong_section_and_unknown_bytes_fail(self):
        for change in ({"kernel_start": self.metrics["kernel_start"]+2, "kernel_end": self.metrics["kernel_end"]+2},
                       {"section_index": self.metrics["section_index"]+1}, {"unclassified_bytes": 2},
                       {"elf_sha256": "0"*64}, {"instructions_16": self.metrics["kernel_compressed_instruction_count"]+1}):
            with self.subTest(change=change):
                original = copy.deepcopy(self.first)
                self.first["programs"][0]["profiles"]["O0"].update(change)
                with self.assertRaises(ReviewError):
                    self.validate()
                self.first = original

    def test_same_identity_and_missing_mutual_independence_fail(self):
        for identity in ("alice", " ALICE "):
            with self.subTest(identity=identity):
                self.second["reviewer_id"] = identity
                self.second["independent_from"] = ["someone-else"]
                with self.assertRaises(ReviewError):
                    self.validate()
        self.second["reviewer_id"] = "bob"
        with self.assertRaisesRegex(ReviewError, "independence from the other"):
            self.validate()

    def test_evidence_must_exist_and_belong_to_the_reviewed_profile(self):
        annotation = self.first["programs"][0]["profiles"]["O0"]
        original = copy.deepcopy(annotation["evidence"])
        for references in (["missing.elf"], ["../program.elf"],
                           [reference.replace("/O0/", "/O2/") for reference in original], original[:1]):
            with self.subTest(references=references):
                annotation["evidence"] = references
                with self.assertRaises(ReviewError):
                    self.validate()

    def test_original_absolute_evidence_locations_survive_transfer(self):
        for document in (self.first, self.second):
            for program in document["programs"]:
                for annotation in program["profiles"].values():
                    annotation["evidence"] = ["/original/host/evaluation-test/" + reference + "#kernel"
                                              for reference in annotation["evidence"]]
        self.assertTrue(self.validate()["machine_evidence_checked"])

    def test_mock_diagnostic_and_missing_manifest_fail(self):
        original = copy.deepcopy(self.batch)
        for change in ({"is_mock": True}, {"mode": "diagnostic"}, {"artifact_sha256": {}}, {"completed": 1}):
            with self.subTest(change=change):
                self.batch.update(change)
                with self.assertRaises(ReviewError):
                    self.validate()
                self.batch = copy.deepcopy(original)

    def test_duplicate_programs_and_reused_experiments_fail(self):
        original = copy.deepcopy(self.batch)
        self.batch["programs"].append(copy.deepcopy(self.batch["programs"][0]))
        with self.assertRaises(ReviewError):
            self.validate()
        self.batch = copy.deepcopy(original)
        self.batch["programs"][1]["result_path"] = self.batch["programs"][0]["result_path"]
        with self.assertRaises(ReviewError):
            self.validate()

    def test_duplicate_or_missing_adjudication_and_signoffs_fail(self):
        original = copy.deepcopy(self.adjudication)
        for change in ({"decisions": original["decisions"] + [original["decisions"][0]]},
                       {"decisions": original["decisions"][:-1]}, {"signoffs": ["alice"]},
                       {"signoffs": ["alice", "bob", "bob"]}, {"reviewer_ids": ["alice", "bob", "alice"]}):
            with self.subTest(change=change):
                self.adjudication.update(change)
                with self.assertRaises(ReviewError):
                    self.validate()
                self.adjudication = copy.deepcopy(original)

    def test_program_rows_cannot_be_swapped_between_distinct_experiments(self):
        first, second = self.batch["programs"][:2]
        first["result_path"], second["result_path"] = second["result_path"], first["result_path"]
        with self.assertRaisesRegex(ReviewError, "benchmark identity mismatch"):
            self.validate()

    def test_frozen_corpus_mismatch_fails(self):
        other = self.root.parent / "other-corpus.json"
        document = json.loads(self.corpus.read_bytes())
        document["different_source"] = True
        self.write(other, document)
        self.corpus = other
        with self.assertRaisesRegex(ReviewError, "corpus does not match"):
            self.validate()

    def test_modified_gnu_output_fails_frozen_manifest(self):
        symbols = self.root / "experiments/exec-0/O0/analysis/readelf-symbols.txt"
        symbols.write_text("kernel no longer exists", encoding="ascii")
        with self.assertRaisesRegex(ReviewError, "Batch artifact hash mismatch"):
            self.validate()

    def test_rehashed_false_symbol_boundaries_still_fail_fresh_reference(self):
        symbols = self.root / "experiments/exec-0/O0/analysis/readelf-symbols.txt"
        symbols.write_text("kernel no longer exists", encoding="ascii")
        self.batch["artifact_sha256"][str(symbols.relative_to(self.root))] = self.sha(symbols)
        with self.assertRaisesRegex(ReviewError, "Archived GNU symbol boundaries"):
            self.validate()

    def test_unknown_elf_is_a_controlled_cli_failure(self):
        # Bind a changed ELF to both reviews and manifest: fresh GNU must still reject it.
        elf = self.root / "experiments/exec-0/O0/program.elf"
        elf.write_bytes(b"not an ELF")
        digest = self.sha(elf)
        self.batch["artifact_sha256"][str(elf.relative_to(self.root))] = digest
        for document in (self.first, self.second):
            document["programs"][0]["profiles"]["O0"]["elf_sha256"] = digest
        with self.assertRaises(ReviewError):
            self.validate(real_tools=True)
        script = Path(__file__).resolve().parents[2] / "scripts/validate_reviews.py"
        result = subprocess.run([sys.executable, "-B", str(script), "--corpus", str(self.corpus),
                                 "--batch", str(self.batch_path), "--review-a", str(self.first_path),
                                 "--review-b", str(self.second_path), "--adjudication", str(self.adjudication_path)],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 3)
        self.assertIn("FAIL:", result.stderr)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
