"""Adapters for test runners: pytest, generic JUnit XML, Jest/Vitest, Playwright Test, plain commands."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

from .. import models as m
from ..procexec import ProcResult, tool_version, which
from .base import AdapterRequest, Parsed, execute, make_result, plugin_pythonpath, prepare, read_optional

S = m.Status


# ----------------------------------------------------------------------------- pytest


def run_pytest(req: AdapterRequest) -> m.TestExecution:
    """Run pytest with the project's interpreter and the qast reporter plugin.

    ``-p no:cacheprovider`` keeps the audit read-only (no .pytest_cache in the project).
    """
    argv = [req.python, "-m", "pytest", *req.args, "-p", "qa_superteam.pytest_reporter", "-p", "no:cacheprovider", "-q", "-rN"]

    def parse(proc: ProcResult, work: Path) -> Parsed:
        report = work / "pytest-report.jsonl"
        junit = work / "junit.xml"
        raw = read_optional(report)
        extra = []
        if raw:
            extra.append(("pytest-report.jsonl", raw, m.ArtifactKind.REPORT, "per-test outcomes (qast reporter)"))
        jraw = read_optional(junit)
        if jraw:
            extra.append(("junit.xml", jraw, m.ArtifactKind.JUNIT, "pytest JUnit XML"))
        if raw is None:
            return Parsed(results=[], ok=False, extra_artifacts=extra)
        results = []
        seen: set[str] = set()
        for line in raw.decode("utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            nodeid = rec["nodeid"]
            if nodeid in seen:
                continue
            seen.add(nodeid)
            loc = rec.get("location") or [None, None, None]
            results.append(
                make_result(
                    "pytest",
                    nodeid,
                    S(rec["status"]),
                    req.groups,
                    name=nodeid.split("::")[-1],
                    duration_s=rec.get("duration_s"),
                    message=rec.get("message"),
                    file=loc[0] if loc else None,
                    line=(loc[1] + 1) if loc and isinstance(loc[1], int) else None,
                )
            )
        note = None
        if proc.exit_code == 5:
            note = "pytest collected no tests (exit code 5)"
        return Parsed(results=results, ok=True, note=note, extra_artifacts=extra)

    def classify(proc: ProcResult):
        # `python -m pytest` without pytest exits 1, like a test failure: decide by the
        # missing report plus the interpreter's own error, never by exit code alone.
        report_written = (work / "pytest-report.jsonl").exists() or (work / "junit.xml").exists()
        if not report_written and "No module named pytest" in proc.stderr:
            return S.BLOCKED, f"pytest is not installed for interpreter {req.python}; install it or set [python] interpreter"
        return None

    # The execution id (and therefore the work dir) is deterministic, so the report
    # paths can be computed before execute() creates the directory.
    ex_id, work = prepare(req, "pytest", argv)
    argv = argv + ["--junitxml", str(work / "junit.xml")]
    env = {
        "PYTHONPATH": plugin_pythonpath([str(req.cwd)]),
        "QAST_PYTEST_REPORT": str(work / "pytest-report.jsonl"),
    }
    tv = {}
    v = tool_version([req.python, "-m", "pytest", "--version"], req.cwd)
    if v:
        tv["pytest"] = v
    return execute(req, "pytest", argv, parse, env=env, ok_codes=(0,), tool_versions=tv, classify_process=classify, ex_id=ex_id)


# ----------------------------------------------------------------------------- junit


def parse_junit_xml(data: bytes, adapter: str, groups: list[str]) -> list[m.TestResult]:
    root = ET.fromstring(data)
    results = []
    for tc in root.iter("testcase"):
        name = tc.get("name", "?")
        cls = tc.get("classname") or ""
        file = tc.get("file")
        ident = f"{file}::{name}" if file else (f"{cls}::{name}" if cls else name)
        status, msg = S.PASSED, None
        for child in tc:
            tag = child.tag.lower()
            if tag == "failure":
                status, msg = S.FAILED, (child.get("message") or "") + "\n" + (child.text or "")
            elif tag == "error":
                status, msg = S.ERROR, (child.get("message") or "") + "\n" + (child.text or "")
            elif tag == "skipped":
                status, msg = S.SKIPPED, child.get("message") or child.text
        t = tc.get("time")
        results.append(
            make_result(
                adapter,
                ident,
                status,
                groups,
                name=name,
                duration_s=float(t) if t else None,
                message=(msg or "").strip()[:4000] or None,
                file=file,
                line=int(tc.get("line")) if tc.get("line", "").isdigit() else None,
            )
        )
    return results


def run_junit(req: AdapterRequest) -> m.TestExecution:
    """Run any command that writes a JUnit XML report: ``qast exec junit --report path -- cmd ...``"""
    report = req.options.get("report")
    if not report:
        raise ValueError("junit adapter needs --report <path to JUnit XML written by the command>")
    report_path = (req.cwd / report).resolve()
    if report_path.exists():
        report_path.unlink()  # never parse a stale report from an earlier run

    def parse(proc: ProcResult, work: Path) -> Parsed:
        raw = read_optional(report_path)
        if raw is None:
            return Parsed(results=[], ok=False, note=f"report {report} was not written")
        try:
            results = parse_junit_xml(raw, "junit", req.groups)
        except ET.ParseError as e:
            return Parsed(results=[], ok=False, note=f"invalid JUnit XML: {e}")
        return Parsed(results=results, extra_artifacts=[("junit.xml", raw, m.ArtifactKind.JUNIT, "JUnit XML report")])

    return execute(req, "junit", list(req.args), parse)


# ----------------------------------------------------------------------------- jest / vitest

_JEST_STATUS = {"passed": S.PASSED, "failed": S.FAILED, "pending": S.SKIPPED, "skipped": S.SKIPPED, "todo": S.SKIPPED, "disabled": S.SKIPPED}


def parse_jest_json(data: dict, adapter: str, groups: list[str], root: Path) -> list[m.TestResult]:
    results = []
    for suite in data.get("testResults", []):
        file = suite.get("name") or suite.get("testFilePath") or "?"
        try:
            rel = Path(file).resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            rel = file
        assertions = suite.get("assertionResults") or suite.get("testResults") or []
        if not assertions and suite.get("status") == "failed":
            results.append(make_result(adapter, rel, S.ERROR, groups, name=rel, message=(suite.get("message") or "suite failed to run")[:4000], file=rel))
            continue
        for a in assertions:
            full = a.get("fullName") or " ".join([*a.get("ancestorTitles", []), a.get("title", "")]).strip()
            st = _JEST_STATUS.get(a.get("status", ""), S.INCONCLUSIVE)
            msgs = a.get("failureMessages") or []
            dur = a.get("duration")
            loc = a.get("location") or {}
            results.append(
                make_result(
                    adapter,
                    f"{rel}::{full}",
                    st,
                    groups,
                    name=a.get("title"),
                    duration_s=(dur / 1000.0) if isinstance(dur, (int, float)) else None,
                    message="\n".join(msgs)[:4000] or None,
                    file=rel,
                    line=loc.get("line") if isinstance(loc, dict) else None,
                )
            )
    return results


def _js_runner(req: AdapterRequest, runner: str) -> m.TestExecution:
    binary = which(runner, req.cwd)
    out_rel = "{work}/" + runner + "-report.json"
    if runner == "vitest":
        argv = [binary or runner, "run", "--reporter=json", f"--outputFile={out_rel}", *req.args]
    else:
        argv = [binary or runner, "--json", f"--outputFile={out_rel}", *req.args]

    ex_id, work = prepare(req, runner, argv)
    argv = [a.replace("{work}", str(work)) for a in argv]
    out_path = work / f"{runner}-report.json"

    def parse(proc: ProcResult, w: Path) -> Parsed:
        raw = read_optional(out_path)
        if raw is None:
            return Parsed(results=[], ok=False, note=f"{runner} did not write a JSON report")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            return Parsed(results=[], ok=False, note=f"invalid {runner} JSON: {e}")
        return Parsed(
            results=parse_jest_json(data, runner, req.groups, req.cwd),
            extra_artifacts=[(f"{runner}-report.json", raw, m.ArtifactKind.REPORT, f"{runner} JSON report")],
        )

    tv = {}
    if binary:
        v = tool_version([binary, "--version"], req.cwd)
        if v:
            tv[runner] = v
    return execute(req, runner, argv, parse, tool_versions=tv, ex_id=ex_id)


def run_vitest(req: AdapterRequest) -> m.TestExecution:
    return _js_runner(req, "vitest")


def run_jest(req: AdapterRequest) -> m.TestExecution:
    return _js_runner(req, "jest")


# ----------------------------------------------------------------------------- playwright test (node)

_PW_STATUS = {"expected": S.PASSED, "unexpected": S.FAILED, "flaky": S.INCONCLUSIVE, "skipped": S.SKIPPED}


def parse_playwright_json(data: dict, groups: list[str], project_root: Path | None = None) -> tuple[list[m.TestResult], list[str]]:
    results: list[m.TestResult] = []
    attachments: list[str] = []
    root_dir = (data.get("config") or {}).get("rootDir")

    def project_rel(file: str) -> str:
        if not root_dir or not project_root:
            return file
        try:
            return (Path(root_dir) / file).resolve().relative_to(project_root.resolve()).as_posix()
        except ValueError:
            return file

    def walk(suite: dict, titles: list[str]):
        for spec in suite.get("specs", []):
            for t in spec.get("tests", []):
                project = t.get("projectName") or ""
                file = project_rel(spec.get("file") or suite.get("file") or "?")
                title = " > ".join([*titles, spec.get("title", "")]).strip(" >")
                ident = f"{file}::{title}" + (f" [{project}]" if project else "")
                st = _PW_STATUS.get(t.get("status", ""), S.INCONCLUSIVE)
                runs = t.get("results") or []
                last = runs[-1] if runs else {}
                if st == S.FAILED and last.get("status") == "timedOut":
                    msg = "test timed out"
                else:
                    err = last.get("error") or {}
                    msg = err.get("message") or err.get("stack")
                if st == S.INCONCLUSIVE and t.get("status") == "flaky":
                    msg = f"flaky: failed then passed on retry ({len(runs)} attempts)"
                if st == S.FAILED and msg and any(k in msg for k in ("Executable doesn't exist", "browserType.launch", "Failed to launch")):
                    st = S.ERROR  # the browser could not start: an environment problem, not product behaviour
                for r in runs:
                    for a in r.get("attachments", []) or []:
                        if a.get("path"):
                            attachments.append(a["path"])
                results.append(
                    make_result(
                        "playwright",
                        ident,
                        st,
                        groups,
                        name=spec.get("title"),
                        duration_s=(sum(r.get("duration", 0) for r in runs) / 1000.0) if runs else None,
                        message=(msg or "")[:4000] or None,
                        file=file,
                        line=spec.get("line"),
                    )
                )
        for child in suite.get("suites", []) or []:
            walk(child, [*titles, child.get("title", "")] if child.get("title") and child.get("title") != child.get("file") else titles)

    for s in data.get("suites", []):
        walk(s, [])
    return results, attachments


def run_playwright(req: AdapterRequest) -> m.TestExecution:
    binary = which("playwright", req.cwd)
    argv0 = [binary or "playwright", "test", "--reporter=json"]
    ex_id, work = prepare(req, "playwright", argv0 + req.args)
    out_path = work / "playwright-report.json"
    # --output keeps Playwright's test-results/ out of the project tree (read-only audit)
    argv = [*argv0, f"--output={work / 'test-results'}", *req.args]

    def parse(proc: ProcResult, w: Path) -> Parsed:
        raw = read_optional(out_path)
        if raw is None:
            return Parsed(results=[], ok=False, note="playwright did not write a JSON report")
        data = json.loads(raw)
        results, attachment_paths = parse_playwright_json(data, req.groups, req.cwd)
        extra = [("playwright-report.json", raw, m.ArtifactKind.REPORT, "Playwright JSON report")]
        for p in attachment_paths:
            ap = Path(p)
            b = read_optional(ap)
            if b is not None:
                kind = m.ArtifactKind.TRACE if ap.suffix == ".zip" else (m.ArtifactKind.SCREENSHOT if ap.suffix == ".png" else m.ArtifactKind.OTHER)
                extra.append((ap.name, b, kind, f"Playwright attachment {ap.name}"))
        return Parsed(results=results, extra_artifacts=extra)

    tv = {}
    if binary:
        v = tool_version([binary, "--version"], req.cwd)
        if v:
            tv["playwright"] = v
    return execute(req, "playwright", argv, parse, env={"PLAYWRIGHT_JSON_OUTPUT_NAME": str(out_path)}, tool_versions=tv, ex_id=ex_id)


# ----------------------------------------------------------------------------- generic command


def run_command(req: AdapterRequest) -> m.TestExecution:
    """Coarse adapter: one result from the exit code. Use only when no structured output exists."""
    if not req.args:
        raise ValueError("command adapter needs a command after --")
    ok_codes = tuple(int(c) for c in str(req.options.get("ok_codes") or "0").split(","))
    # during `qast reproduce` the result must carry the identifier being reproduced
    ident = req.reproduction_of or req.label or " ".join(req.args)
    module = req.args[req.args.index("-m") + 1] if "-m" in req.args[:-1] else None

    def classify(proc: ProcResult):
        if module and proc.exit_code not in ok_codes and f"No module named {module}" in proc.stderr:
            return S.BLOCKED, f"python module '{module}' is not installed for {req.args[0]}"
        return None

    def parse(proc: ProcResult, work: Path) -> Parsed:
        if proc.timed_out:
            return Parsed(results=[])
        st = S.PASSED if proc.exit_code in ok_codes else S.FAILED
        tail = (proc.stderr or proc.stdout)[-2000:] if st == S.FAILED else None
        return Parsed(
            results=[make_result("command", ident, st, req.groups, name=ident, message=tail)],
            note="coarse result: derived from exit code only, no per-test detail",
        )

    return execute(req, "command", list(req.args), parse, ok_codes=ok_codes, classify_process=classify)
