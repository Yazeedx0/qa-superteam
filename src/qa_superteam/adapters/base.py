"""Adapter framework: run a real tool, collect evidence, normalize results.

Every adapter follows the same evidence-first pipeline (``execute``):

1. Resolve the tool.  Missing tool -> ``BLOCKED`` with an install hint (never FAILED).
2. Run it via :mod:`procexec` (argv only, timeout, bounded output).
3. Store stdout/stderr and tool reports as redacted, hashed evidence artifacts.
4. Parse tool output into :class:`TestResult` records with deterministic ids.
5. Derive the execution status from parsed results *and* the exit code; any
   disagreement becomes ``INCONCLUSIVE`` rather than a guessed pass.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .. import models as m
from ..config import PLUGIN_ROOT, Config
from ..env import environment_info
from ..procexec import ProcResult, run
from ..redact import redact_argv
from ..store import RunStore
from ..util import now_iso, rel_to, slug, stable_id

S = m.Status


@dataclass
class AdapterRequest:
    store: RunStore
    config: Config
    args: list[str]
    cwd: Path
    groups: list[str] = field(default_factory=list)
    label: str | None = None
    timeout_s: int | None = None
    python: str = "python3"
    targets: list[str] = field(default_factory=list)
    options: dict = field(default_factory=dict)
    attempt: int = 1
    reproduction_of: str | None = None


@dataclass
class Parsed:
    results: list[m.TestResult]
    ok: bool = True  # parsing succeeded (a report file existed and was readable)
    note: str | None = None
    extra_artifacts: list[tuple[str, bytes, m.ArtifactKind, str]] = field(default_factory=list)
    tool_versions: dict[str, str] = field(default_factory=dict)


class BlockedError(Exception):
    """Raised by adapters before execution when preconditions are not met."""


def result_id(adapter: str, identifier: str) -> str:
    return stable_id("tr", adapter, identifier)


def make_result(adapter: str, identifier: str, status: m.Status, groups: list[str], **kw) -> m.TestResult:
    return m.TestResult(id=result_id(adapter, identifier), identifier=identifier, status=status, groups=list(groups), **kw)


def count_statuses(results: list[m.TestResult]) -> dict[str, int]:
    counts = {s.value: 0 for s in S}
    for r in results:
        counts[r.status.value] += 1
    return counts


def derive_status(
    results: list[m.TestResult],
    exit_code: int | None,
    timed_out: bool,
    ok_codes: tuple[int, ...] = (0,),
    parse_ok: bool = True,
    timeout_s: float | None = None,
) -> tuple[m.Status, str | None]:
    """Combine parsed results with the process outcome. Conservative by design."""
    if timed_out:
        return S.ERROR, f"timed out after {timeout_s}s; partial results are not trusted as a pass"
    if not parse_ok and not results:
        if exit_code in ok_codes:
            return S.INCONCLUSIVE, f"exit code {exit_code} but no machine-readable results were produced"
        return S.ERROR, f"exit code {exit_code} and no machine-readable results were produced"
    if not results:
        return S.NOT_RUN, f"no tests were executed (exit code {exit_code})"
    statuses = {r.status for r in results}
    if S.FAILED in statuses:
        reason = None if exit_code not in ok_codes else f"failures parsed although exit code was {exit_code}"
        return S.FAILED, reason
    if S.ERROR in statuses:
        return S.ERROR, "one or more tests errored during setup/teardown/collection"
    if S.INCONCLUSIVE in statuses:
        return S.INCONCLUSIVE, "one or more results are inconclusive (flaky or needs manual review)"
    if S.BLOCKED in statuses and S.PASSED not in statuses:
        return S.BLOCKED, "all results blocked"
    if S.PASSED not in statuses:
        if statuses <= {S.SKIPPED}:
            return S.SKIPPED, "every test was skipped; nothing was verified"
        return S.NOT_RUN, "no test reached a pass/fail outcome"
    if exit_code not in ok_codes:
        return S.INCONCLUSIVE, f"all parsed results passed but the tool exited with {exit_code}"
    return S.PASSED, None


def plugin_pythonpath(extra: list[str] | None = None) -> str:
    parts = [str(PLUGIN_ROOT / "src"), *(extra or [])]
    existing = os.environ.get("PYTHONPATH")
    if existing:
        parts.append(existing)
    return os.pathsep.join(parts)


def prepare(req: AdapterRequest, adapter: str, base_argv: list[str]) -> tuple[str, Path]:
    """Allocate the execution id and work dir before the final argv is known."""
    ex_id = req.store.execution_id(adapter, req.label or " ".join(base_argv))
    return ex_id, req.store.dir / "work" / ex_id


def blocked_execution(req: AdapterRequest, adapter: str, argv: list[str], reason: str, ex_id: str | None = None) -> m.TestExecution:
    """Record that an execution could not happen. Blocked is evidence too."""
    ts = now_iso()
    ex = m.TestExecution(
        id=ex_id or req.store.execution_id(adapter, req.label or " ".join(argv)),
        run_id=req.store.run_id,
        adapter=adapter,
        status=S.BLOCKED,
        started_at=ts,
        finished_at=ts,
        duration_s=0.0,
        command=redact_argv(argv, req.store.redactor),
        cwd=rel_to(req.cwd, req.config.project_root),
        exit_code=None,
        timed_out=False,
        counts=count_statuses([]),
        results=[],
        environment=environment_info(req.config.project_root),
        groups=list(req.groups),
        label=req.label,
        status_reason=reason,
        attempt=req.attempt,
        reproduction_of=req.reproduction_of,
    )
    req.store.save_execution(ex)
    return ex


def execute(
    req: AdapterRequest,
    adapter: str,
    argv: list[str],
    parse: Callable[[ProcResult, Path], Parsed],
    env: dict[str, str] | None = None,
    ok_codes: tuple[int, ...] = (0,),
    tool_versions: dict[str, str] | None = None,
    classify_process: Callable[[ProcResult], tuple[m.Status, str] | None] | None = None,
    ex_id: str | None = None,
) -> m.TestExecution:
    store = req.store
    timeout = req.timeout_s or req.config.budgets.command_timeout_s
    ex_id = ex_id or store.execution_id(adapter, req.label or " ".join(argv))
    work = store.dir / "work" / ex_id
    artifact_dir = work / "artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    full_env = {"QAST_ARTIFACT_DIR": str(artifact_dir), "QAST_RUN_ID": store.run_id, "QAST_WORK_DIR": str(work)}
    full_env.update(env or {})
    store.journal("exec.start", execution_id=ex_id, adapter=adapter, argv=redact_argv(argv, store.redactor))

    started = now_iso()
    proc = run(argv, req.cwd, timeout_s=timeout, env=full_env, max_output_bytes=req.config.budgets.max_output_bytes)
    finished = now_iso()

    if proc.not_found:
        shutil.rmtree(work, ignore_errors=True)
        return blocked_execution(req, adapter, argv, f"tool not available: {proc.stderr}", ex_id=ex_id)

    artifact_ids: list[str] = []
    log = f"$ {' '.join(argv)}\n[exit_code={proc.exit_code} timed_out={proc.timed_out} duration={proc.duration_s}s]\n--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}\n"
    art = store.add_artifact(f"{adapter}-output.log", log.encode(), m.ArtifactKind.LOG, ex_id, f"{adapter} stdout/stderr")
    artifact_ids.append(art.id)

    forced = classify_process(proc) if classify_process else None
    if forced is not None:
        status, reason = forced
        parsed = Parsed(results=[], ok=False)
    else:
        parsed = parse(proc, work)
        status, reason = derive_status(parsed.results, proc.exit_code, proc.timed_out, ok_codes, parsed.ok, timeout)
        if parsed.note:
            reason = f"{reason}; {parsed.note}" if reason else parsed.note

    for name, data, kind, desc in parsed.extra_artifacts:
        a = store.add_artifact(name, data, kind, ex_id, desc)
        artifact_ids.append(a.id)

    # Files tests dropped into $QAST_ARTIFACT_DIR (screenshots, traces, HAR, ...)
    by_result: dict[str, list[str]] = {}
    for f in sorted(artifact_dir.rglob("*")):
        if not f.is_file():
            continue
        kind = _kind_for(f)
        a = store.add_artifact(f.name, f.read_bytes(), kind, ex_id, f"collected from test artifact dir: {f.name}")
        artifact_ids.append(a.id)
        for r in parsed.results:
            if slug(r.identifier, 200) in slug(f.stem, 200) or slug(f.stem, 200) in slug(r.identifier, 200):
                by_result.setdefault(r.id, []).append(a.id)
    for r in parsed.results:
        r.artifact_ids = sorted(set(r.artifact_ids + by_result.get(r.id, [])))

    versions = dict(tool_versions or {})
    versions.update(parsed.tool_versions)
    ex = m.TestExecution(
        id=ex_id,
        run_id=store.run_id,
        adapter=adapter,
        status=status,
        started_at=started,
        finished_at=finished,
        duration_s=proc.duration_s,
        command=redact_argv(argv, store.redactor),
        cwd=rel_to(req.cwd, req.config.project_root),
        exit_code=proc.exit_code,
        timed_out=proc.timed_out,
        counts=count_statuses(parsed.results),
        results=parsed.results,
        environment=environment_info(req.config.project_root, versions),
        groups=list(req.groups),
        label=req.label,
        status_reason=reason,
        artifact_ids=artifact_ids,
        attempt=req.attempt,
        reproduction_of=req.reproduction_of,
    )
    for r in ex.results:
        if r.message:
            r.message = store.redactor.redact(r.message)
    store.save_execution(ex)
    shutil.rmtree(work, ignore_errors=True)
    store.journal("exec.finish", execution_id=ex_id, status=status.value, counts=ex.counts)
    return ex


def _kind_for(path: Path) -> m.ArtifactKind:
    suf = path.suffix.lower()
    if suf in (".png", ".jpg", ".jpeg", ".webp"):
        return m.ArtifactKind.SCREENSHOT
    if suf in (".webm", ".mp4"):
        return m.ArtifactKind.VIDEO
    if suf == ".zip" and "trace" in path.name:
        return m.ArtifactKind.TRACE
    if suf in (".har",):
        return m.ArtifactKind.TRACE
    if suf in (".log", ".txt"):
        return m.ArtifactKind.LOG
    if suf in (".json", ".jsonl", ".xml"):
        return m.ArtifactKind.REPORT
    return m.ArtifactKind.OTHER


def read_optional(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None
