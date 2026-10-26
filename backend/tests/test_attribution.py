from pathlib import Path
import tempfile
import unittest

from backend.app.attribution import build_attribution, generate_attributions


def _variant(profile: str, *, kernel_bytes: int = 10, status: str = "passed"):
    return {
        "optimization": profile,
        "status": status,
        "metrics": None if status != "passed" else {
            "elf_file_bytes": 100,
            "text_section_bytes": 40,
            "kernel_code_bytes": kernel_bytes,
            "kernel_static_instruction_count": 3,
            "kernel_compressed_instruction_count": 1,
            "dynamic_instruction_count": None,
            "target_cycles": None,
        },
        "runs": [] if status != "passed" else [{"case_id": "empty", "status": "passed"}],
    }


def _experiment(reference=True, candidate=True):
    variants = []
    if reference:
        variants.append(_variant("O2"))
    if candidate:
        variants.append(_variant("O0"))
    return {"experiment_id": "attr-test", "is_mock": False, "variants": variants}


class AttributionTests(unittest.TestCase):
    def artifacts(self, folder: Path):
        for profile in ("O2", "O0"):
            directory = folder / profile / "analysis"
            directory.mkdir(parents=True)
            (folder / profile / "program.elf").write_bytes(profile.encode())
            for name in ("objdump-kernel.txt", "readelf-symbols.txt", "readelf-sections.txt"):
                (directory / name).write_text(name, encoding="utf-8")

    def test_complete_r001_and_r002_reconcile(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            self.artifacts(folder)
            result = build_attribution(_experiment(), b"{}", folder, "O0")
            self.assertEqual(result["status"], "complete")
            self.assertEqual(result["deltas"]["kernel_delta_bytes"], 0)
            self.assertEqual(result["deltas"]["outside_kernel_delta_bytes"], 0)
            self.assertEqual({rule["status"] for rule in result["rules"]}, {"verified"})

    def test_unknown_width_bytes_are_partial(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            self.artifacts(folder)
            experiment = _experiment()
            experiment["variants"][1]["metrics"]["kernel_code_bytes"] = 12
            result = build_attribution(experiment, b"{}", folder, "O0")
            self.assertEqual(result["status"], "partial")
            self.assertEqual(result["rules"][0]["status"], "abstained")
            self.assertEqual(result["snapshots"]["candidate"]["unclassified_bytes"], 2)

    def test_missing_reference_is_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            result = build_attribution(_experiment(reference=False), b"{}", Path(directory), "O0")
            self.assertEqual(result["status"], "unavailable")
            self.assertIsNone(result["snapshots"])
            self.assertTrue(all(rule["status"] == "abstained" for rule in result["rules"]))

    def test_generate_writes_one_sidecar_per_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            self.artifacts(folder)
            result = _experiment()
            result_path = folder / "result.json"
            result_path.write_text("{}", encoding="utf-8")
            paths, complete = generate_attributions(result_path, result)
            self.assertTrue(complete)
            self.assertEqual(len(paths), 1)
            self.assertTrue(paths[0].is_file())


if __name__ == "__main__":
    unittest.main()
