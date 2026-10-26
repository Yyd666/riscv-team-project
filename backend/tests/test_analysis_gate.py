"""Gate source pinning, stream recording and infrastructure-failure semantics."""

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import types
import unittest

from backend.app.execution import ProcessRunner
from backend.app.execution_types import ExecutionContext, ExecutionError
from scripts.check_analysis_integration import (
    analyze_recorded, load_candidate, run_gate, run_recorded,
)

ROOT = Path(__file__).resolve().parents[2]


class CandidateError(Exception):
    def __init__(self, code):
        self.code, self.details = code, {}
        super().__init__(code)


@unittest.skipUnless(sys.platform == "linux" and shutil.which("git"), "Linux Git/process tools required")
class AnalysisGateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.context = ExecutionContext(self.root, time.monotonic() + 60)
        self.runner = ProcessRunner(self.context)

    def tearDown(self):
        self.temporary.cleanup()

    def git(self, *args):
        return run_recorded(self.runner, [shutil.which("git"), "-C", str(self.root), *args],
                            self.root / "git-logs" / str(time.monotonic_ns())).decode().strip()

    def init_fixture_repo(self, source):
        self.git("init", "--quiet")
        self.git("config", "user.name", "Integration fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("config", "commit.gpgsign", "false")
        self.git("config", "core.hooksPath", "/dev/null")
        path = self.root / "backend/app/analysis/elf.py"
        path.parent.mkdir(parents=True)
        path.write_text(source)
        self.git("add", "backend/app/analysis/elf.py")
        self.git("commit", "--quiet", "-m", "fixture")
        return self.git("rev-parse", "HEAD")

    def test_git_module_is_pinned_and_raw_source_is_preserved(self):
        source = "def analyze_elf(*args, **kwargs):\n return 'fixture-only'\n"
        commit = self.init_fixture_repo(source)
        audit = self.root / "audit"
        audit.mkdir()
        module, metadata = load_candidate(self.root, "HEAD", audit)
        try:
            self.assertEqual(metadata["candidate_commit"], commit)
            self.assertEqual(metadata["consumer_commit"], commit)
            self.assertEqual(metadata["candidate_source_sha256"], hashlib.sha256(source.encode()).hexdigest())
            self.assertEqual((audit / "analysis.snapshot.py").read_bytes(), source.encode())
            self.assertEqual(module.analyze_elf(), "fixture-only")
        finally:
            sys.modules.pop(module.__name__, None)

    def test_bad_refs_rejected_before_git_or_python_execution(self):
        for ref in ("--help", "main;touch BAD", "HEAD:other.py", "$(echo main)", ""):
            with self.subTest(ref=ref), self.assertRaises(ValueError):
                load_candidate(ROOT, ref, self.root)
        self.assertFalse((self.root / "BAD").exists())

    def test_invalid_candidate_import_does_not_leave_registered_module(self):
        commit = self.init_fixture_repo("def invalid syntax\n")
        audit = self.root / "audit"
        audit.mkdir()
        with self.assertRaises(SyntaxError):
            load_candidate(self.root, commit, audit)
        self.assertNotIn("backend.app._candidate_" + commit, sys.modules)

    def test_auditor_keeps_exact_streams_and_restores_candidate_runner(self):
        module = types.SimpleNamespace(ProcessRunner=ProcessRunner, AnalysisError=CandidateError)

        def analyze(elf, *, context):
            module.ProcessRunner(context).run([
                sys.executable, "-c", "import os; os.write(1,b'\\x00\\xff'); os.write(2,b'err')"],
                cwd=context.workspace, timeout_s=5, max_output_bytes=100)
            return types.SimpleNamespace(to_dict=lambda: {
                "status": "analysis_error", "reason": "fixture only", "metrics": None, "evidence": {}})

        module.analyze_elf = analyze
        folder = self.root / "audit"
        document = analyze_recorded(module, self.root / "unused.elf", self.context, folder)
        self.assertEqual(document["status"], "analysis_error")
        self.assertEqual((folder / "command-00/stdout.bin").read_bytes(), b"\x00\xff")
        self.assertEqual((folder / "command-00/stderr.bin").read_bytes(), b"err")
        self.assertIs(module.ProcessRunner, ProcessRunner)

    def test_missing_tool_is_not_successful_negative_rejection(self):
        module = types.SimpleNamespace(ProcessRunner=ProcessRunner, AnalysisError=CandidateError)

        def analyze(elf, *, context):
            raise CandidateError("TOOLCHAIN_UNAVAILABLE")

        module.analyze_elf = analyze
        folder = self.root / "audit"
        with self.assertRaises(ExecutionError) as caught:
            analyze_recorded(module, self.root / "unused.elf", self.context, folder)
        self.assertEqual(caught.exception.code, "TOOLCHAIN_UNAVAILABLE")
        self.assertFalse((folder / "analysis.json").exists())
        self.assertIs(module.ProcessRunner, ProcessRunner)

    def test_setup_failure_writes_failed_summary_instead_of_green_result(self):
        with self.assertRaises(ValueError):
            run_gate(ROOT, "--invalid-ref", self.root)
        summary = json.loads(next(self.root.glob("integration-*/summary.json")).read_bytes())
        self.assertEqual(summary["status"], "infrastructure_error")
        self.assertFalse(summary["positive_cases"])
        self.assertFalse(summary["negative_cases"])

    def test_cli_unexpected_failures_exit_five_and_keep_partial_evidence(self):
        # Inject candidate-loading failures in a child process, while keeping
        # the real gate's summary writer and the CLI's exit boundary intact.
        program = """
import builtins
from pathlib import Path
import sys
from unittest.mock import patch
from scripts.check_analysis_integration import main

def fail(repo, revision, audit):
    (audit / 'partial-output.bin').write_bytes(b'\\x00\\xff')
    raise getattr(builtins, sys.argv[2])('candidate failure fixture')

with patch('scripts.check_analysis_integration.load_candidate', side_effect=fail):
    raise SystemExit(main(['--analysis-ref', 'HEAD', '--output', sys.argv[1]]))
"""
        for error_type in ("SyntaxError", "TypeError", "RuntimeError", "OSError", "ValueError"):
            with self.subTest(error_type=error_type):
                output = self.root / error_type
                result = subprocess.run(
                    [sys.executable, "-B", "-c", program, str(output), error_type],
                    cwd=ROOT, capture_output=True, timeout=20, check=False,
                )
                self.assertEqual(result.returncode, 5, result.stderr.decode())
                self.assertIn(error_type.encode(), result.stderr)
                summary_path = next(output.glob("integration-*/summary.json"))
                summary = json.loads(summary_path.read_bytes())
                self.assertEqual(summary["status"], "infrastructure_error")
                self.assertFalse(summary["positive_cases"])
                self.assertFalse(summary["negative_cases"])
                raw = summary_path.parent / "candidate/partial-output.bin"
                self.assertEqual(raw.read_bytes(), b"\x00\xff")
                self.assertEqual(summary["artifact_sha256"]["candidate/partial-output.bin"],
                                 hashlib.sha256(raw.read_bytes()).hexdigest())

    def test_nonzero_tool_exit_is_not_valid_domain_rejection(self):
        module = types.SimpleNamespace(ProcessRunner=ProcessRunner, AnalysisError=CandidateError)

        def analyze(elf, *, context):
            module.ProcessRunner(context).run([sys.executable, "-c", "exit(7)"],
                cwd=context.workspace, timeout_s=5, max_output_bytes=100)
            raise CandidateError("ANALYSIS_ERROR")

        module.analyze_elf = analyze
        folder = self.root / "audit"
        with self.assertRaises(ExecutionError) as caught:
            analyze_recorded(module, self.root / "unused.elf", self.context, folder)
        self.assertEqual(caught.exception.code, "INTEGRATION_TOOL_FAILED")
        self.assertFalse((folder / "analysis.json").exists())
        self.assertIs(module.ProcessRunner, ProcessRunner)


if __name__ == "__main__":
    unittest.main()
