"""Adapters for nonfunctional checks: k6 (performance), axe-core (accessibility), AI evals."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .. import models as m
from ..env import find_axe
from ..procexec import ProcResult, tool_version
from .base import AdapterRequest, BlockedError, Parsed, blocked_execution, execute, make_result, plugin_pythonpath, prepare, read_optional

S = m.Status

# ----------------------------------------------------------------------------- k6

K6_PROFILES = {
    # smoke: proves the script and endpoints work; safe default, overrides script load options
    "smoke": ["--vus", "1", "--iterations", "5"],
    # load: script-defined options; requires permissions.allow_load_testing = true
    "load": [],
}
_URL_RE = re.compile(r"https?://[^\s'\"`)]+")


def check_k6_script(script: Path, cfg, target: str) -> str | None:
    """Return a blocking reason if the script would hit unauthorized hosts."""
    try:
        text = script.read_text(encoding="utf-8")
    except FileNotFoundError:
        return f"k6 script not found: {script}"
    for url in _URL_RE.findall(text):
        if not cfg.is_authorized_target(url):
            return f"script contains hard-coded URL not in permissions.authorized_targets: {url} (use __ENV.TARGET)"
    if "__ENV.TARGET" not in text:
        return "script must read its base URL from __ENV.TARGET so qast can enforce the target allowlist"
    return None


def run_k6(req: AdapterRequest) -> m.TestExecution:
    cfg = req.config
    profile = req.options.get("profile") or "smoke"
    target = req.targets[0] if req.targets else None
    if not req.args:
        raise ValueError("k6 adapter needs a script path after --")
    script = req.cwd / req.args[0]
    base_argv = ["k6", "run", *req.args]
    if profile not in K6_PROFILES:
        raise ValueError(f"unknown k6 profile {profile}; use one of {sorted(K6_PROFILES)}")
    if not target:
        return blocked_execution(req, "k6", base_argv, "no --target given; load tests require an explicit authorized target URL")
    if not cfg.is_authorized_target(target):
        return blocked_execution(req, "k6", base_argv, f"target {target} is not in permissions.authorized_targets")
    if profile == "load" and not cfg.permissions.allow_load_testing:
        return blocked_execution(req, "k6", base_argv, "profile 'load' requires permissions.allow_load_testing = true (explicit authorization)")
    problem = check_k6_script(script, cfg, target)
    if problem:
        return blocked_execution(req, "k6", base_argv, problem)

    ex_id, work = prepare(req, "k6", base_argv)
    summary = work / "k6-summary.json"
    argv = ["k6", "run", "--no-color", "--quiet", *K6_PROFILES[profile], "-e", f"TARGET={target}", f"--summary-export={summary}", *req.args]

    def parse(proc: ProcResult, w: Path) -> Parsed:
        raw = read_optional(summary)
        if raw is None:
            return Parsed(results=[], ok=False, note="k6 did not write a summary")
        return Parsed(
            results=parse_k6_summary(json.loads(raw), req.groups),
            extra_artifacts=[("k6-summary.json", raw, m.ArtifactKind.REPORT, f"k6 summary ({profile} profile)")],
            note=f"profile={profile}" + (" (smoke: functional check of the script, not a capacity measurement)" if profile == "smoke" else ""),
        )

    v = tool_version(["k6", "version"])
    # 99 = thresholds crossed: results carry the failure, so it is an expected exit code
    return execute(req, "k6", argv, parse, ok_codes=(0, 99), tool_versions={"k6": v} if v else {}, ex_id=ex_id)


def parse_k6_summary(data: dict, groups: list[str]) -> list[m.TestResult]:
    """k6 --summary-export: a threshold value of true means the threshold was CROSSED."""
    results = []
    for metric, vals in sorted((data.get("metrics") or {}).items()):
        for expr, crossed in sorted((vals.get("thresholds") or {}).items()):
            observed = {k: v for k, v in vals.items() if k != "thresholds"}
            results.append(
                make_result(
                    "k6",
                    f"threshold:{metric}:{expr}",
                    S.FAILED if crossed else S.PASSED,
                    groups,
                    name=f"{metric} {expr}",
                    message=f"observed {json.dumps(observed)}" if crossed else None,
                )
            )

    def walk(group: dict, prefix: str):
        for name, chk in sorted((group.get("checks") or {}).items()):
            fails, passes = chk.get("fails", 0), chk.get("passes", 0)
            results.append(
                make_result(
                    "k6",
                    f"check:{prefix}{name}",
                    S.FAILED if fails else S.PASSED,
                    groups,
                    name=name,
                    message=f"{fails} failed / {passes} passed" if fails else None,
                )
            )
        for gname, g in sorted((group.get("groups") or {}).items()):
            walk(g, f"{prefix}{gname}::")

    walk(data.get("root_group") or {}, "")
    return results


# ----------------------------------------------------------------------------- axe


def run_axe(req: AdapterRequest) -> m.TestExecution:
    if not req.targets:
        raise ValueError("axe adapter needs at least one --target URL")
    base_argv = [req.python, "-m", "qa_superteam.runners.axe_scan", *[f"--url={t}" for t in req.targets]]
    for t in req.targets:
        if not (req.config.is_authorized_target(t) or t.startswith("file://")):
            return blocked_execution(req, "axe", base_argv, f"target {t} is not in permissions.authorized_targets")
    axe = find_axe(req.cwd) or find_axe(req.config.project_root)
    if axe is None:
        return blocked_execution(req, "axe", base_argv, "axe-core not found: npm i -D axe-core (or set QAST_AXE_PATH to axe.min.js)")
    ex_id, work = prepare(req, "axe", base_argv)
    out = work / "axe-result.json"
    shots = work / "artifacts"
    argv = [
        *base_argv,
        f"--axe={axe}",
        f"--out={out}",
        f"--shots={shots}",
        f"--viewport={req.options.get('viewport') or '1280x800'}",
    ]

    def classify(proc: ProcResult):
        if proc.exit_code == 3:
            return S.BLOCKED, f"playwright is not installed for {req.python}: pip install playwright && python -m playwright install chromium"
        return None

    def parse(proc: ProcResult, w: Path) -> Parsed:
        raw = read_optional(out)
        if raw is None:
            return Parsed(results=[], ok=False, note="axe scan produced no result file")
        data = json.loads(raw)
        return Parsed(results=parse_axe_result(data, req.groups), extra_artifacts=[("axe-result.json", raw, m.ArtifactKind.REPORT, "axe-core results")])

    return execute(req, "axe", argv, parse, env={"PYTHONPATH": plugin_pythonpath()}, classify_process=classify, ex_id=ex_id)


def parse_axe_result(data: dict, groups: list[str]) -> list[m.TestResult]:
    """Violations -> FAILED, incomplete -> INCONCLUSIVE (needs manual review), passes -> PASSED."""
    results = []
    for pg in data.get("pages", []):
        url = pg["url"]
        if "error" in pg:
            results.append(make_result("axe", f"{url}::navigation", S.ERROR, groups, name="navigation", message=pg["error"]))
            continue
        for v in pg.get("violations", []):
            targets = "; ".join(" ".join(n.get("target") or []) for n in v.get("nodes", []))
            results.append(
                make_result(
                    "axe",
                    f"{url}::{v['id']}",
                    S.FAILED,
                    groups,
                    name=v["id"],
                    message=f"[{v.get('impact')}] {v.get('help')} — nodes: {targets} — {v.get('helpUrl')}",
                )
            )
        for v in pg.get("incomplete", []):
            results.append(
                make_result(
                    "axe",
                    f"{url}::{v['id']}",
                    S.INCONCLUSIVE,
                    groups,
                    name=v["id"],
                    message=f"needs manual review: {v.get('help')}",
                )
            )
        for rule in pg.get("passes", []):
            results.append(make_result("axe", f"{url}::{rule}", S.PASSED, groups, name=rule))
    return results


# ----------------------------------------------------------------------------- ai-eval


def run_ai_eval(req: AdapterRequest) -> m.TestExecution:
    opts = req.options
    dataset, target = opts.get("dataset"), opts.get("target")
    if not dataset or not target:
        raise ValueError("ai-eval adapter needs --dataset <jsonl> and --entry <module:function>")
    base_argv = [req.python, "-m", "qa_superteam.runners.ai_eval", "--dataset", dataset, "--target", target]
    if not (req.cwd / dataset).exists():
        return blocked_execution(req, "ai-eval", base_argv, f"dataset not found: {dataset}")
    ex_id, work = prepare(req, "ai-eval", base_argv)
    out = work / "ai-eval-results.jsonl"
    argv = [*base_argv, "--out", str(out), "--samples", str(opts.get("samples") or 1)]
    if opts.get("judge_model"):
        argv += ["--judge-model", opts["judge_model"]]
    if opts.get("calibration"):
        argv += ["--calibration", str((req.cwd / opts["calibration"]).resolve())]
    stem = Path(dataset).stem

    def parse(proc: ProcResult, w: Path) -> Parsed:
        raw = read_optional(out)
        if raw is None:
            return Parsed(results=[], ok=False, note="ai eval runner produced no results (see log)")
        results = []
        for line in raw.decode().splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            failed = [c for c in rec.get("checks", []) if c.get("passed") is False]
            msg = rec.get("reason") or ""
            if rec.get("usage_estimated"):
                msg = (msg + " " if msg else "") + "(token usage estimated)"
            results.append(
                make_result(
                    "ai-eval",
                    f"{stem}::{rec['id']}",
                    S(rec["status"]),
                    req.groups,
                    name=rec["id"],
                    duration_s=(rec["latency_ms"] / 1000.0) if rec.get("latency_ms") is not None else None,
                    message=(msg or ("; ".join(c["name"] for c in failed))) or None,
                )
            )
        extra = [("ai-eval-results.jsonl", raw, m.ArtifactKind.REPORT, "per-case AI eval outcomes with check details")]
        summ = read_optional(out.with_suffix(".summary.json"))
        if summ:
            extra.append(("ai-eval-summary.json", summ, m.ArtifactKind.REPORT, "AI eval aggregate metrics"))
        return Parsed(results=results, extra_artifacts=extra)

    return execute(req, "ai-eval", argv, parse, env={"PYTHONPATH": plugin_pythonpath([str(req.cwd)])}, ex_id=ex_id)


__all__ = ["run_k6", "run_axe", "run_ai_eval", "parse_k6_summary", "parse_axe_result", "BlockedError"]
