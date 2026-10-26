"""Run registered evaluation programs through the production execution pipeline."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
from importlib.metadata import distributions
import json
from pathlib import Path, PureWindowsPath
import subprocess
import sys
from threading import Lock
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.execution.engine import atomic_json
from backend.app.execution_types import ExecutionError
from backend.app.pipeline import load_baseline, run_experiment
from backend.app.reporting import load_result
from scripts.evaluate_attribution import _corpus_issues
from scripts.evaluation_registry import ProgramAssets, asset, digest, prepare_program, read_registry

IMPLEMENTATION_FILES = (
    *(path.relative_to(ROOT).as_posix() for path in sorted((ROOT / "backend/app").rglob("*.py"))),
    *(path.relative_to(ROOT).as_posix() for path in sorted((ROOT / "optipilot").glob("*.py"))),
    *(path.relative_to(ROOT).as_posix() for path in sorted((ROOT / "contracts").glob("*.schema.json"))),
    "scripts/run_evaluation_corpus.py", "scripts/evaluation_registry.py", "scripts/evaluate_attribution.py",
    "scripts/check_execution_integration.py", "scripts/elf_reference.py", "scripts/render_evaluation_report.py",
    "config/baseline.json", "config/attribution-policy.json", "evaluation/corpus.json", "requirements-foundation.txt",
)
_BATCH_LOCK = Lock()


class CorpusNotReady(ValueError):
    pass


@contextmanager
def evaluation_slot(output_root: Path):
    if sys.platform != "linux":
        raise ExecutionError("TOOLCHAIN_UNAVAILABLE", "Evaluation execution requires Linux or WSL2")
    import fcntl
    if not _BATCH_LOCK.acquire(blocking=False):
        raise ExecutionError("EXPERIMENT_BUSY", "An evaluation batch is already running")
    try:
        output_root.mkdir(parents=True, exist_ok=True)
        with (output_root / ".evaluation.lock").open("a+b") as lock:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise ExecutionError("EXPERIMENT_BUSY", "Evaluation artifact root is in use") from error
            try:
                yield
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
    finally:
        _BATCH_LOCK.release()


def implementation_snapshot(destination: Path) -> dict:
    # Worktrees created by Windows Git contain an absolute Windows gitdir path.
    # Resolve that pointer for read-only Git object queries under WSL as well.
    marker = ROOT / ".git"
    git_directory = marker
    if marker.is_file():
        pointer = marker.read_text(encoding="utf-8").strip()
        if not pointer.startswith("gitdir: "):
            raise ValueError("Invalid implementation worktree pointer")
        value = pointer[8:]
        win = PureWindowsPath(value)
        if sys.platform == "linux" and win.drive and len(win.drive) == 2 and win.drive[1] == ":":
            git_directory = Path("/mnt") / win.drive[0].lower() / Path(*win.parts[1:])
        else:
            git_directory = Path(value)
            if not git_directory.is_absolute():
                git_directory = ROOT / git_directory
    prefix = ["git", "--git-dir", str(git_directory)]
    git = subprocess.run([*prefix, "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, timeout=5)
    if git.returncode != 0:
        raise ValueError("Implementation Git revision is unavailable: " + git.stderr.decode("utf-8", "replace"))
    commit = git.stdout.decode("ascii").strip()
    if len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit):
        raise ValueError("Invalid implementation Git revision")
    hashes, modified = {}, []
    for name in IMPLEMENTATION_FILES:
        source = (ROOT / name).resolve(strict=True)
        if not source.is_relative_to(ROOT):
            raise ValueError("Implementation source escapes repository")
        raw = source.read_bytes()
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        hashes[name] = digest(raw)
        tracked = subprocess.run([*prefix, "cat-file", "blob", f"{commit}:{name}"], cwd=ROOT,
                                 capture_output=True, timeout=5)
        # Windows worktrees may materialize tracked text as CRLF. Compare the
        # normalized bytes for commit integrity while preserving the exact
        # working-tree bytes in the evidence snapshot.
        normalized_tracked = tracked.stdout.replace(b"\r\n", b"\n")
        normalized_raw = raw.replace(b"\r\n", b"\n")
        if tracked.returncode != 0 or normalized_tracked != normalized_raw:
            modified.append(name)
    packages = sorted({(package.metadata["Name"], package.version) for package in distributions()
                       if package.metadata["Name"]})
    return {"git_commit": commit, "modified_files": modified, "file_sha256": hashes,
            "python_packages": [{"name": name, "version": version} for name, version in packages]}


def materialize_registry(root: Path, destination: Path, corpus: dict, programs: list[ProgramAssets],
                         *, diagnostic: bool) -> dict:
    destination.mkdir()
    (destination / "config").mkdir()
    (destination / "config/baseline.json").write_bytes(asset(root, "config/baseline.json").read_bytes())
    manifest = {"schema_version": "0.1.0", "corpus_version": (
        ("diagnostic-evaluation-" if diagnostic else "evaluation-") + corpus["corpus_version"]), "benchmarks": []}
    for program in programs:
        directory = destination / "benchmarks" / program.program_id
        (directory / "cases").mkdir(parents=True)
        (directory / "main.c").write_bytes(program.source)
        prefix = f"benchmarks/{program.program_id}"
        cases = []
        for case in program.cases:
            (directory / "cases" / (case.case_id + ".in")).write_bytes(case.stdin)
            (directory / "cases" / (case.case_id + ".out")).write_bytes(case.expected_stdout)
            cases.append({"id": case.case_id, "stdin": f"{prefix}/cases/{case.case_id}.in",
                          "stdout": f"{prefix}/cases/{case.case_id}.out"})
        manifest["benchmarks"].append({"id": program.program_id, "source": f"{prefix}/main.c",
                                       "kernel_symbol": "kernel", "expected_exit_code": 0,
                                       "expected_stderr": "", "cases": cases})
    (destination / "benchmarks").mkdir(exist_ok=True)
    atomic_json(destination / "benchmarks/manifest.json", manifest)
    return manifest


def run_batch(root: Path, corpus_path: Path, output_root: Path, *, diagnostic=False,
              selected: tuple[str, ...] = ()) -> tuple[Path, int]:
    root = root.resolve(strict=True)
    corpus, raw = read_registry(root, corpus_path)
    issues = _corpus_issues(corpus, root=root)
    if issues and not diagnostic:
        raise CorpusNotReady("; ".join(issues))
    by_id = {entry["program_id"]: entry for entry in corpus["entries"]}
    if len(set(selected)) != len(selected) or not set(selected) <= by_id.keys():
        raise ValueError("Duplicate or unregistered selected program")
    if selected and not diagnostic and set(selected) != by_id.keys():
        raise ValueError("A formal evaluation must execute the complete frozen registry")
    entries = [entry for entry in corpus["entries"] if not selected or entry["program_id"] in selected]
    # Seal all input bytes before creating output or invoking any compiler.
    programs = [prepare_program(root, entry, diagnostic=diagnostic) for entry in entries]
    with evaluation_slot(output_root.resolve()):
        return _execute_batch(root, corpus, raw, entries, programs, output_root, issues=issues, diagnostic=diagnostic)


def _execute_batch(root, corpus, raw, entries, programs, output_root, *, issues, diagnostic):
    batch = output_root.resolve() / ("evaluation-" + uuid.uuid4().hex)
    batch.mkdir(parents=True, exist_ok=False)
    summary = {"schema_version": "0.1.0", "is_mock": False, "batch_id": batch.name,
               "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
               "mode": "diagnostic" if diagnostic else "formal", "corpus_status": corpus.get("status"),
               "corpus_sha256": digest(raw), "corpus_issues": issues,
               "requested_programs": [entry["program_id"] for entry in entries],
               "unattempted_programs": [entry["program_id"] for entry in entries],
               "active_program": None, "programs": [], "completed": False,
               "all_passed": False, "acceptance_ready": False, "exit_code": None}
    (batch / "corpus.json").write_bytes(raw)
    status_path = batch / "batch.json"
    atomic_json(status_path, summary)
    code = 0
    try:
        implementation = implementation_snapshot(batch / "implementation")
        atomic_json(batch / "implementation.json", implementation)
        repository = batch / "registry-repository"
        materialize_registry(root, repository, corpus, programs, diagnostic=diagnostic)
        manifest_sha = digest((repository / "benchmarks/manifest.json").read_bytes())
        for program in programs:
            summary["active_program"] = program.program_id
            summary["unattempted_programs"].remove(program.program_id)
            atomic_json(status_path, summary)
            result, result_path, outcome = run_experiment(
                repository, batch / "experiments", program.program_id, ("O0", "O2", "Os"),
                load_baseline(repository), require_attribution=True)
            load_result(result_path)
            if result["source_sha256"] != digest(program.source) or result["inputs"] != program.input_hashes():
                raise ValueError("Pipeline result differs from sealed registry assets")
            (result_path.parent / "evaluation-corpus.json").write_bytes(raw)
            atomic_json(result_path.parent / "evaluation-implementation.json", implementation)
            atomic_json(result_path.parent / "evaluation.json", {
                "mode": summary["mode"], "batch_id": batch.name, "corpus_sha256": digest(raw),
                "case_binding_origin": program.case_binding_origin, "manifest_sha256": manifest_sha,
                "implementation_sha256": digest((batch / "implementation.json").read_bytes()),
            })
            row = {"program_id": program.program_id, "exit_code": outcome,
                   "status": "passed" if outcome == 0 else "failed", "result_path": str(result_path),
                   "variant_statuses": {v["optimization"]: v["status"] for v in result["variants"]}}
            summary["programs"].append(row)
            summary["active_program"] = None
            if outcome == 3 or (outcome == 4 and code == 0):
                code = outcome
            atomic_json(status_path, summary)
            print(f"{'PASS' if outcome == 0 else 'FAIL'}: {program.program_id} exit={outcome} {result_path}", flush=True)
        summary["completed"] = True
        summary["all_passed"] = all(row["exit_code"] == 0 for row in summary["programs"])
    except KeyboardInterrupt:
        code = 5
        summary["error"] = {"code": "EXPERIMENT_CANCELLED", "message": "Evaluation interrupted"}
    except Exception as error:
        code = 5
        summary["error"] = {"code": getattr(error, "code", "INTERNAL_ERROR"), "message": str(error)}
    summary["exit_code"] = code
    inventory = {path.relative_to(batch).as_posix(): digest(path.read_bytes()) for path in sorted(batch.rglob("*"))
                 if path.is_file() and path != status_path and path.name not in {".execution.lock", ".execution-started"}}
    summary["artifact_sha256"] = inventory
    atomic_json(status_path, summary)
    return status_path, code


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--diagnostic", action="store_true", help="Run draft registry without claiming formal evaluation")
    parser.add_argument("--program", action="append", default=[], help="Registered ID; subset selection is diagnostic only")
    args = parser.parse_args(argv)
    try:
        path, code = run_batch(ROOT, args.corpus, args.output, diagnostic=args.diagnostic,
                               selected=tuple(args.program))
    except CorpusNotReady as error:
        print(f"NOT READY: {error}", file=sys.stderr)
        return 3
    except ExecutionError as error:
        print(json.dumps({"error": {"code": error.code, "message": str(error)}}, ensure_ascii=False), file=sys.stderr)
        return 5
    except (OSError, ValueError) as error:
        print(f"INVALID INPUT: {error}", file=sys.stderr)
        return 2
    print(f"batch_path={path}", file=sys.stderr)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
