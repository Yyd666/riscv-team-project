"""Behavior checks for Linux process boundaries and execution orchestration."""

from __future__ import annotations

from dataclasses import replace
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from threading import Timer
import time
import unittest
from unittest.mock import patch

from backend.app.execution import execute, experiment_session, ProcessRunner
from backend.app.execution.engine import _load_assets, validate_request
from backend.app.execution_types import ExecutionContext, ExecutionError, ExecutionRequest

ROOT = Path(__file__).resolve().parents[2]


def running(pid: int) -> bool:
    try:
        return Path(f"/proc/{pid}/stat").read_text().split(") ")[1][0] != "Z"
    except (FileNotFoundError, ProcessLookupError):
        return False


@unittest.skipUnless(sys.platform == "linux", "Linux process groups required")
class ProcessTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.context = ExecutionContext(self.root, time.monotonic() + 10)
        self.runner = ProcessRunner(self.context)

    def tearDown(self):
        self.temporary.cleanup()

    def run_python(self, source, **kwargs):
        return self.runner.run([sys.executable, "-c", source], cwd=self.root,
                               timeout_s=kwargs.pop("timeout_s", 2),
                               max_output_bytes=kwargs.pop("max_output_bytes", 1048576), **kwargs)

    def assert_gone(self, pid):
        until = time.monotonic() + 2
        while running(pid) and time.monotonic() < until:
            time.sleep(0.02)
        self.assertFalse(running(pid), f"Process {pid} survived group cleanup")

    def test_binary_streams_nonzero_and_c_locale(self):
        result = self.run_python(
            "import os; os.write(1,b'\\xff\\x00'); os.write(2,os.environ['LC_ALL'].encode()); exit(7)")
        self.assertEqual((result.status, result.exit_code), ("completed", 7))
        self.assertEqual(result.stdout, b"\xff\x00")
        self.assertEqual(result.stderr, b"C")

    def test_argv_is_not_a_shell_command(self):
        literal = "$(touch INJECTED); echo unsafe"
        result = self.runner.run([sys.executable, "-c", "import sys; print(sys.argv[1])", literal],
                                 cwd=self.root, timeout_s=2, max_output_bytes=1024)
        self.assertEqual(result.stdout, (literal + "\n").encode())
        self.assertFalse((self.root / "INJECTED").exists())
        with self.assertRaises(ValueError):
            self.runner.run("echo unsafe", cwd=self.root, timeout_s=2, max_output_bytes=1024)

    def test_large_stdin_and_both_streams_do_not_deadlock(self):
        data = b"x" * 200000
        result = self.run_python(
            "import os,sys; os.write(2,b'e'*100000); sys.stdout.buffer.write(sys.stdin.buffer.read())",
            stdin=data)
        self.assertEqual(result.stdout, data)
        self.assertEqual(result.stderr, b"e" * 100000)
        self.assertEqual(result.exit_code, 0)

    def test_output_cap_each_stream_and_exact_boundary(self):
        for fd in (1, 2):
            for count in (4096, 1000000):
                with self.subTest(fd=fd, count=count):
                    result = self.run_python(f"import os; os.write({fd}, b'x'*{count})",
                                             max_output_bytes=4096)
                    self.assertEqual(result.status, "output_limit")
                    self.assertIsNone(result.exit_code)
                    self.assertEqual(len(result.stdout if fd == 1 else result.stderr), 4096)

    def test_timeout_cleans_descendants_inheriting_pipes(self):
        result = self.run_python(
            "import os,time; pid=os.fork(); print(os.getpid(),flush=True); time.sleep(30)", timeout_s=0.2)
        self.assertEqual(result.status, "timeout")
        for line in result.stdout.splitlines():
            self.assert_gone(int(line))
        self.assertGreaterEqual(len(result.stdout.splitlines()), 2)

    def test_exited_parent_does_not_leave_descendant(self):
        result = self.run_python(
            "import os,time; pid=os.fork(); "
            "print(os.getpid(),flush=True); "
            "os._exit(0) if pid else time.sleep(30)", timeout_s=0.2)
        self.assertEqual(result.status, "timeout")
        for line in result.stdout.splitlines():
            self.assert_gone(int(line))

    def test_success_also_cleans_descendants_that_close_pipes(self):
        result = self.run_python(
            "import os,time; pid=os.fork(); "
            "print(os.getpid(),flush=True); "
            "(os.close(1),os.close(2),time.sleep(30)) if pid==0 else None")
        self.assertEqual(result.status, "completed")
        for line in result.stdout.splitlines():
            self.assert_gone(int(line))

    def test_total_budget_is_infrastructure_error_with_partial_output(self):
        self.runner = ProcessRunner(replace(self.context, deadline=time.monotonic() + 0.15))
        with self.assertRaises(ExecutionError) as caught:
            self.run_python("import time; print('started',flush=True); time.sleep(30)")
        self.assertEqual(caught.exception.code, "REQUEST_TIMEOUT")
        self.assertEqual(caught.exception.process_result.stdout, b"started\n")

    def test_cancellation_cleans_group(self):
        timer = Timer(0.15, self.context.cancel.set)
        timer.start()
        try:
            with self.assertRaises(ExecutionError) as caught:
                self.run_python("import os,time; print(os.getpid(),flush=True); time.sleep(30)")
            self.assertEqual(caught.exception.code, "EXPERIMENT_CANCELLED")
            self.assert_gone(int(caught.exception.process_result.stdout))
        finally:
            timer.join()

    def test_workdir_and_timeout_validation(self):
        for timeout in (0, -1, float("nan"), float("inf")):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                self.run_python("pass", timeout_s=timeout)
        with self.assertRaises(ValueError):
            self.runner.run([sys.executable, "-c", "pass"], cwd=self.root.parent,
                            timeout_s=1, max_output_bytes=100)

    def test_early_stdin_close_is_handled(self):
        result = self.run_python("pass", stdin=b"a" * 200000)
        self.assertEqual((result.status, result.exit_code), ("completed", 0))

    def test_expired_budget_and_unavailable_tool(self):
        self.runner = ProcessRunner(replace(self.context, deadline=time.monotonic() - 1))
        with self.assertRaises(ExecutionError) as caught:
            self.run_python("pass")
        self.assertEqual(caught.exception.code, "REQUEST_TIMEOUT")
        self.runner = ProcessRunner(self.context)
        with self.assertRaises(ExecutionError) as caught:
            self.runner.run(["/missing/optipilot-tool"], cwd=self.root,
                            timeout_s=1, max_output_bytes=100)
        self.assertEqual(caught.exception.code, "TOOLCHAIN_UNAVAILABLE")

    def test_keyboard_interrupt_still_kills_process_group(self):
        from selectors import DefaultSelector
        actual_select = DefaultSelector.select
        calls = 0

        def interrupt_after_output(selector, timeout=None):
            nonlocal calls
            calls += 1
            if (self.root / "pid").exists():
                raise KeyboardInterrupt()
            return actual_select(selector, timeout)

        with patch.object(DefaultSelector, "select", interrupt_after_output):
            with self.assertRaises(KeyboardInterrupt):
                self.run_python(
                    "import os,time,pathlib; pathlib.Path('pid').write_text(str(os.getpid())); time.sleep(30)")
        self.assertGreater(calls, 0)
        self.assert_gone(int((self.root / "pid").read_text()))

    def test_windows_execution_is_rejected_without_fallback(self):
        with patch("backend.app.execution.process.sys.platform", "win32"):
            with self.assertRaises(ExecutionError) as caught:
                self.run_python("pass")
        self.assertEqual(caught.exception.code, "TOOLCHAIN_UNAVAILABLE")


class RequestTests(unittest.TestCase):
    def setUp(self):
        self.manifest = _load_assets(ROOT)[1]

    def test_invalid_requests_rejected(self):
        for request in (ExecutionRequest("../main", ("O2",)), ExecutionRequest("sum_u32", ()),
                        ExecutionRequest("sum_u32", ("-O3",)),
                        ExecutionRequest("sum_u32", ("O2", "O2")),
                        ExecutionRequest("sum_u32", "O2")):
            with self.subTest(request=request), self.assertRaises(ExecutionError) as caught:
                validate_request(request, self.manifest)
            self.assertEqual(caught.exception.code, "INVALID_REQUEST")

    def test_unknown_and_requested_order(self):
        with self.assertRaises(ExecutionError) as caught:
            validate_request(ExecutionRequest("missing", ("O2",)), self.manifest)
        self.assertEqual(caught.exception.code, "UNKNOWN_BENCHMARK")
        request = ExecutionRequest("sum_u32", ("Os", "O0"))
        self.assertEqual(validate_request(request, self.manifest)["id"], "sum_u32")
        self.assertEqual(request.optimizations, ("Os", "O0"))


@unittest.skipUnless(sys.platform == "linux", "Linux backend required")
class EngineTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        shutil.copytree(ROOT / "config", self.repo / "config")
        shutil.copytree(ROOT / "benchmarks", self.repo / "benchmarks")

    def tearDown(self):
        self.temporary.cleanup()

    def test_single_process_session_lock_and_release(self):
        with experiment_session(self.repo, self.root / "out"):
            with self.assertRaises(ExecutionError) as caught:
                with experiment_session(self.repo, self.root / "out2"):
                    self.fail("Concurrent session allowed")
            self.assertEqual(caught.exception.code, "EXPERIMENT_BUSY")
        with experiment_session(self.repo, self.root / "out") as context:
            self.assertTrue(context.workspace.is_dir())

    def test_artifact_root_cross_process_lock(self):
        worker = (
            "import pathlib,sys; "
            "from backend.app.execution import experiment_session; "
            "from backend.app.execution_types import ExecutionError; "
            "exec(\"try:\\n with experiment_session(pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])): "
            "print('ready')\\nexcept ExecutionError as e: print(e.code)\")"
        )
        argv = [sys.executable, "-c", worker, str(self.repo), str(self.root / "out")]
        with experiment_session(self.repo, self.root / "out"):
            result = subprocess.run(argv, cwd=ROOT, capture_output=True, timeout=5, check=True)
            self.assertEqual(result.stdout, b"EXPERIMENT_BUSY\n")
        result = subprocess.run(argv, cwd=ROOT, capture_output=True, timeout=5, check=True)
        self.assertEqual(result.stdout, b"ready\n")

    def test_session_required_and_failed_request_cannot_reuse_directory(self):
        context = ExecutionContext(self.root, time.monotonic() + 5)
        with self.assertRaises(ExecutionError):
            execute(ExecutionRequest("sum_u32", ("O2",)), repo_root=self.repo, context=context)
        with experiment_session(self.repo, self.root / "out") as context:
            with self.assertRaises(ExecutionError) as caught:
                execute(ExecutionRequest("missing", ("O2",)), repo_root=self.repo, context=context)
            self.assertEqual(caught.exception.code, "UNKNOWN_BENCHMARK")
            with self.assertRaises(ExecutionError):
                execute(ExecutionRequest("sum_u32", ("O2",)), repo_root=self.repo, context=context)

    def test_missing_tools_is_explicit_and_no_completed_bundle(self):
        with experiment_session(self.repo, self.root / "out") as context:
            with patch("backend.app.execution.engine.shutil.which", return_value=None):
                with self.assertRaises(ExecutionError) as caught:
                    execute(ExecutionRequest("sum_u32", ("O2",)), repo_root=self.repo, context=context)
            self.assertEqual(caught.exception.code, "TOOLCHAIN_UNAVAILABLE")
            self.assertFalse((context.workspace / "execution.json").exists())
            self.assertEqual(json.loads((context.workspace / "error.json").read_text())
                             ["error"]["code"], "TOOLCHAIN_UNAVAILABLE")

    def test_registry_path_escape_and_duplicate_cases(self):
        path = self.repo / "benchmarks/manifest.json"
        manifest = json.loads(path.read_text())
        manifest["benchmarks"][0]["source"] = "../outside.c"
        path.write_text(json.dumps(manifest))
        (self.root / "outside.c").write_text("int main(void) {return 0;}")
        with experiment_session(self.repo, self.root / "out") as context:
            with self.assertRaises(ExecutionError) as caught:
                execute(ExecutionRequest("sum_u32", ("O2",)), repo_root=self.repo, context=context)
            self.assertEqual(caught.exception.code, "INVALID_REQUEST")
        manifest["benchmarks"][0]["cases"] *= 2
        path.write_text(json.dumps(manifest))
        with self.assertRaises(ExecutionError):
            _load_assets(self.repo)

    def test_asset_symlink_escape_and_baseline_flag_drift(self):
        source = self.repo / "benchmarks/sum_u32/main.c"
        source.unlink()
        outside = self.root / "outside.c"
        outside.write_text("int main(void) {return 0;}")
        source.symlink_to(outside)
        with experiment_session(self.repo, self.root / "out") as context:
            with self.assertRaises(ExecutionError) as caught:
                execute(ExecutionRequest("sum_u32", ("O2",)), repo_root=self.repo, context=context)
            self.assertEqual(caught.exception.code, "INVALID_REQUEST")
        path = self.repo / "config/baseline.json"
        config = json.loads(path.read_text())
        config["profiles"]["O2"].append("-march=native")
        path.write_text(json.dumps(config))
        with self.assertRaises(ExecutionError):
            _load_assets(self.repo)

    @unittest.skipUnless(shutil.which("riscv64-linux-gnu-gcc") and shutil.which("qemu-riscv64"),
                         "Real RISC-V tools not installed")
    def test_real_wrong_answer_continues_remaining_cases_and_profiles(self):
        (self.repo / "benchmarks/sum_u32/cases/empty.out").write_bytes(b"incorrect\n")
        with experiment_session(self.repo, self.root / "out") as context:
            bundle = execute(ExecutionRequest("sum_u32", ("Os", "O2")),
                             repo_root=self.repo, context=context)
            self.assertEqual([v.optimization for v in bundle.variants], ["Os", "O2"])
            self.assertFalse(bundle.is_mock)
            for variant in bundle.variants:
                self.assertEqual(variant.status, "wrong_answer")
                self.assertEqual([r.status for r in variant.runs], ["wrong_answer", "passed", "passed"])
                self.assertEqual(variant.runs[0].process.stdout, b"0\n")
            self.assertEqual(json.loads((context.workspace / "execution.json").read_text())
                             ["variants"][0]["status"], "wrong_answer")
            with self.assertRaises(ExecutionError):
                execute(ExecutionRequest("sum_u32", ("O2",)), repo_root=self.repo, context=context)

    @unittest.skipUnless(shutil.which("riscv64-linux-gnu-gcc") and shutil.which("qemu-riscv64"),
                         "Real RISC-V tools not installed")
    def test_real_compile_failure_never_runs(self):
        (self.repo / "benchmarks/sum_u32/main.c").write_text("#error deliberate compile failure\n")
        with experiment_session(self.repo, self.root / "out") as context:
            bundle = execute(ExecutionRequest("sum_u32", ("O2",)), repo_root=self.repo, context=context)
            variant = bundle.variants[0]
            self.assertEqual(variant.status, "compile_error")
            self.assertFalse(variant.runs)
            self.assertIsNone(variant.run_argv)
            self.assertIsNone(variant.elf_path)
            self.assertIn(b"deliberate", variant.compilation.stderr)

    @unittest.skipUnless(shutil.which("riscv64-linux-gnu-gcc") and shutil.which("qemu-riscv64"),
                         "Real RISC-V tools not installed")
    def test_real_runtime_error_preserves_all_cases(self):
        (self.repo / "benchmarks/sum_u32/main.c").write_text("int main(void) {return 9;}\n")
        with experiment_session(self.repo, self.root / "out") as context:
            bundle = execute(ExecutionRequest("sum_u32", ("O2",)), repo_root=self.repo, context=context)
            self.assertEqual(bundle.variants[0].status, "runtime_error")
            self.assertEqual([r.process.exit_code for r in bundle.variants[0].runs], [9, 9, 9])

    @unittest.skipUnless(shutil.which("riscv64-linux-gnu-gcc") and shutil.which("qemu-riscv64"),
                         "Real RISC-V tools not installed")
    def test_real_stderr_and_invalid_utf8_are_not_normalized(self):
        (self.repo / "benchmarks/sum_u32/main.c").write_text(
            '#include <stdio.h>\nint main(void) {fputc(255,stdout); fputs("unexpected",stderr); return 0;}\n')
        with experiment_session(self.repo, self.root / "out") as context:
            bundle = execute(ExecutionRequest("sum_u32", ("O2",)), repo_root=self.repo, context=context)
            variant = bundle.variants[0]
            self.assertEqual(variant.status, "wrong_answer")
            self.assertEqual(variant.runs[0].process.stdout, b"\xff")
            self.assertEqual(variant.runs[0].stdout_path.read_bytes(), b"\xff")
            self.assertEqual(variant.runs[0].process.stderr, b"unexpected")

    @unittest.skipUnless(shutil.which("riscv64-linux-gnu-gcc") and shutil.which("qemu-riscv64"),
                         "Real RISC-V tools not installed")
    def test_real_qemu_timeout_and_output_limit(self):
        programs = [
            ("int main(void) {for (;;) {}}\n", "timeout"),
            ('#include <stdio.h>\nint main(void) {for (;;) fputc(120,stdout);}\n', "output_limit"),
        ]
        for source, state in programs:
            with self.subTest(state=state):
                (self.repo / "benchmarks/sum_u32/main.c").write_text(source)
                with experiment_session(self.repo, self.root / "out") as context:
                    bundle = execute(ExecutionRequest("sum_u32", ("O2",)),
                                     repo_root=self.repo, context=context)
                    variant = bundle.variants[0]
                    self.assertEqual(variant.status, state)
                    self.assertEqual([r.status for r in variant.runs], [state] * 3)
                    self.assertTrue(all(r.process.exit_code is None for r in variant.runs))


if __name__ == "__main__":
    unittest.main()
