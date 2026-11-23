"""Adapters for existing security scanners. Scanner output = *candidate* findings.

Each issue becomes a FAILED result so it is visible and traceable, but a scanner hit
is not a confirmed defect: the qa-security skill requires triage, reproduction and
verification before a DefectFinding is recorded.  A clean scan yields one PASSED
result so the execution still carries positive evidence that the scan ran.
"""

from __future__ import annotations

import json
from pathlib import Path

from .. import models as m
from ..procexec import ProcResult, tool_version, which
from .base import AdapterRequest, Parsed, blocked_execution, execute, make_result, prepare, read_optional

S = m.Status
NOTE = "scanner results are candidate findings; triage and verify before reporting defects"
EXCLUDES = ".venv,venv,node_modules,.git,.qa-superteam,dist,build,.tox"


def _resolve(req: AdapterRequest, tool: str) -> list[str] | None:
    if which(tool, req.cwd):
        return [tool]
    if req.options.get("via_uvx") and which("uvx"):
        return ["uvx", tool]
    return None


def _clean(adapter: str, tool: str, groups: list[str]) -> m.TestResult:
    return make_result(adapter, f"{tool}:scan", S.PASSED, groups, name=f"{tool} scan", message="no issues reported")


def run_bandit(req: AdapterRequest) -> m.TestExecution:
    base = _resolve(req, "bandit")
    paths = req.args or ["."]
    if base is None:
        return blocked_execution(req, "bandit", ["bandit", "-r", *paths], "bandit not installed (pipx install bandit, or pass --via-uvx)")
    ex_id, work = prepare(req, "bandit", base + paths)
    out = work / "bandit.json"
    argv = [*base, "-r", *paths, "-f", "json", "-o", str(out), "-q", "-x", EXCLUDES]

    def parse(proc: ProcResult, w: Path) -> Parsed:
        raw = read_optional(out)
        if raw is None:
            return Parsed(results=[], ok=False)
        data = json.loads(raw)
        res = [
            make_result(
                "bandit",
                f"bandit:{i['test_id']}:{i['filename'].lstrip('./')}:{i['line_number']}",
                S.FAILED,
                req.groups,
                name=f"{i['test_id']} {i.get('test_name', '')}",
                message=f"[severity={i.get('issue_severity')} confidence={i.get('issue_confidence')}] {i.get('issue_text')}",
                file=i["filename"].lstrip("./"),
                line=i.get("line_number"),
            )
            for i in data.get("results", [])
        ]
        return Parsed(results=res or [_clean("bandit", "bandit", req.groups)], note=NOTE, extra_artifacts=[("bandit.json", raw, m.ArtifactKind.REPORT, "bandit report")])

    return execute(req, "bandit", argv, parse, ok_codes=(0, 1), ex_id=ex_id)


def run_pip_audit(req: AdapterRequest) -> m.TestExecution:
    base = _resolve(req, "pip-audit")
    if base is None:
        return blocked_execution(req, "pip-audit", ["pip-audit", *req.args], "pip-audit not installed (pipx install pip-audit, or pass --via-uvx)")
    ex_id, work = prepare(req, "pip-audit", base + req.args)
    out = work / "pip-audit.json"
    argv = [*base, "-f", "json", "-o", str(out), "--progress-spinner", "off", *req.args]

    def parse(proc: ProcResult, w: Path) -> Parsed:
        raw = read_optional(out)
        if raw is None:
            return Parsed(results=[], ok=False)
        data = json.loads(raw)
        deps = data.get("dependencies", data if isinstance(data, list) else [])
        res = []
        for d in deps:
            for v in d.get("vulns", []):
                res.append(
                    make_result(
                        "pip-audit",
                        f"pip-audit:{d['name']}:{d.get('version')}:{v['id']}",
                        S.FAILED,
                        req.groups,
                        name=f"{d['name']} {d.get('version')} {v['id']}",
                        message=f"fix versions: {v.get('fix_versions') or 'none'}; aliases: {v.get('aliases') or []}; {(v.get('description') or '')[:300]}",
                    )
                )
        return Parsed(results=res or [_clean("pip-audit", "pip-audit", req.groups)], note=NOTE, extra_artifacts=[("pip-audit.json", raw, m.ArtifactKind.REPORT, "pip-audit report")])

    return execute(req, "pip-audit", argv, parse, ok_codes=(0, 1), ex_id=ex_id)


def run_npm_audit(req: AdapterRequest) -> m.TestExecution:
    argv = ["npm", "audit", "--json", *req.args]
    if not (req.cwd / "package-lock.json").exists() and not (req.cwd / "npm-shrinkwrap.json").exists():
        return blocked_execution(req, "npm-audit", argv, "npm audit needs a package-lock.json")

    def parse(proc: ProcResult, w: Path) -> Parsed:
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError:
            return Parsed(results=[], ok=False, note="npm audit output was not JSON (offline registry?)")
        if "error" in data and "vulnerabilities" not in data:
            return Parsed(results=[], ok=False, note=f"npm audit error: {data['error'].get('summary', '')}")
        res = []
        for name, v in sorted((data.get("vulnerabilities") or {}).items()):
            via = [x.get("title") if isinstance(x, dict) else str(x) for x in v.get("via", [])]
            res.append(
                make_result(
                    "npm-audit",
                    f"npm-audit:{name}",
                    S.FAILED,
                    req.groups,
                    name=name,
                    message=f"[{v.get('severity')}] range {v.get('range')}; via {via}; fix available: {bool(v.get('fixAvailable'))}",
                )
            )
        return Parsed(
            results=res or [_clean("npm-audit", "npm-audit", req.groups)],
            note=NOTE,
            extra_artifacts=[("npm-audit.json", proc.stdout.encode(), m.ArtifactKind.REPORT, "npm audit report")],
        )

    v = tool_version(["npm", "--version"])
    return execute(req, "npm-audit", argv, parse, ok_codes=(0, 1), tool_versions={"npm": v} if v else {})


def run_semgrep(req: AdapterRequest) -> m.TestExecution:
    config = req.options.get("config")
    base = _resolve(req, "semgrep")
    argv0 = ["semgrep", "scan", *req.args]
    if base is None:
        return blocked_execution(req, "semgrep", argv0, "semgrep not installed (pipx install semgrep)")
    if not config:
        return blocked_execution(req, "semgrep", argv0, "semgrep needs an explicit --config (a local rules file or registry pack); 'auto' is not used because it requires sending metrics")
    argv = [*base, "scan", "--json", "--metrics=off", "--quiet", "--config", config, *(req.args or ["."])]

    def parse(proc: ProcResult, w: Path) -> Parsed:
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError:
            return Parsed(results=[], ok=False)
        res = [
            make_result(
                "semgrep",
                f"semgrep:{r['check_id']}:{r['path']}:{r['start']['line']}",
                S.FAILED,
                req.groups,
                name=r["check_id"],
                message=f"[{r.get('extra', {}).get('severity')}] {r.get('extra', {}).get('message', '')[:500]}",
                file=r["path"],
                line=r["start"]["line"],
            )
            for r in data.get("results", [])
        ]
        return Parsed(results=res or [_clean("semgrep", "semgrep", req.groups)], note=NOTE, extra_artifacts=[("semgrep.json", proc.stdout.encode(), m.ArtifactKind.REPORT, "semgrep report")])

    return execute(req, "semgrep", argv, parse, ok_codes=(0, 1))


def run_gitleaks(req: AdapterRequest) -> m.TestExecution:
    base = _resolve(req, "gitleaks")
    argv0 = ["gitleaks", "detect", *req.args]
    if base is None:
        return blocked_execution(req, "gitleaks", argv0, "gitleaks not installed (https://github.com/gitleaks/gitleaks#installing)")
    ex_id, work = prepare(req, "gitleaks", argv0)
    out = work / "gitleaks.json"
    # --redact keeps secret values out of the report; qast redaction runs again on top
    argv = [*base, "detect", "--no-banner", "--redact", "--report-format", "json", "--report-path", str(out), *req.args]

    def parse(proc: ProcResult, w: Path) -> Parsed:
        raw = read_optional(out)
        if raw is None:
            return Parsed(results=[], ok=False)
        data = json.loads(raw or b"[]") or []
        res = [
            make_result(
                "gitleaks",
                f"gitleaks:{f.get('RuleID')}:{f.get('File')}:{f.get('StartLine')}",
                S.FAILED,
                req.groups,
                name=f.get("RuleID"),
                message=f"{f.get('Description')} (commit {str(f.get('Commit'))[:10]})",
                file=f.get("File"),
                line=f.get("StartLine"),
            )
            for f in data
        ]
        return Parsed(results=res or [_clean("gitleaks", "gitleaks", req.groups)], note=NOTE, extra_artifacts=[("gitleaks.json", raw, m.ArtifactKind.REPORT, "gitleaks report (redacted)")])

    return execute(req, "gitleaks", argv, parse, ok_codes=(0, 1), ex_id=ex_id)
