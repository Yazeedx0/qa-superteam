"""``qast`` — the QA Superteam command line.

Deterministic tooling used by the skills and agents: run bookkeeping, discovery,
change impact, test execution through adapters, evidence capture, verification
gates, the release policy engine and reporting.  See docs/cli.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from . import models as m
from .config import CONFIG_TEMPLATE, ConfigError, load_config
from .serde import SchemaError, from_dict, json_schema, to_dict
from .store import PHASES, RunStore, StoreError
from .util import now_iso, read_json

EXIT_OK, EXIT_ERR, EXIT_REFUSED = 0, 1, 3
MODES = ["full-audit", "review-pr", "test-feature", "test-api", "test-e2e", "security-review", "eval-ai", "explore", "verify-bug", "regression", "release-check", "improve-suite", "adhoc"]
ADAPTERS = ["pytest", "junit", "vitest", "jest", "playwright", "command", "k6", "axe", "ai-eval", "bandit", "pip-audit", "npm-audit", "semgrep", "gitleaks"]


def _out(args, data, human: str) -> None:
    if getattr(args, "json", False):
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(human)


def _cfg(args):
    return load_config(Path(args.project))


def _store(args) -> RunStore:
    return RunStore.resolve(_cfg(args), getattr(args, "run", None))


def _read_input(path: str):
    text = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise SystemExit(f"error: input is not valid JSON: {e}") from None


# ----------------------------------------------------------------------------- commands


def cmd_doctor(args) -> int:
    from .env import capabilities_as_dicts, detect_capabilities, project_python

    cfg = _cfg(args)
    caps = detect_capabilities(cfg.project_root, cfg.python)
    data = {"plugin_version": __version__, "python": sys.version.split()[0], "project_python": project_python(cfg.project_root, cfg.python), "config": cfg.source, "capabilities": capabilities_as_dicts(caps)}
    lines = [f"qast {__version__} · config: {cfg.source}", ""]
    for c in caps:
        mark = "ok " if c.available else "-- "
        extra = c.version or ""
        if c.detail:
            extra += f" ({c.detail})"
        lines.append(f"  [{mark}] {c.name:<22} {extra}")
        if not c.available and c.install_hint:
            lines.append(f"        missing -> {c.install_hint}")
    lines += ["", "Unavailable tools make dependent checks BLOCKED (reported, never treated as passed)."]
    _out(args, data, "\n".join(lines))
    return EXIT_OK


def cmd_init(args) -> int:
    cfg = _cfg(args)
    target = cfg.project_root / ".qa-superteam" / "config.toml"
    if target.exists() and not args.force:
        print(f"{target} already exists (use --force to overwrite)")
        return EXIT_ERR
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(CONFIG_TEMPLATE.read_text(encoding="utf-8"), encoding="utf-8")
    from .store import _ensure_gitignore

    _ensure_gitignore(target.parent)
    print(f"wrote {target} (read-only defaults: no app-code edits, no load/active security testing, local targets only)")
    return EXIT_OK


def cmd_run(args) -> int:
    cfg = _cfg(args)
    if args.run_cmd == "start":
        from .env import environment_info

        st = RunStore.create(cfg, args.mode, args.scope, args.base, args.head, environment_info(cfg.project_root))
        _out(args, {"run_id": st.run_id, "dir": str(st.dir)}, f"run started: {st.run_id}\nrecords: {st.dir}")
        return EXIT_OK
    if args.run_cmd == "list":
        runs = sorted(p.name for p in cfg.runs_dir.glob("*") if (p / "run.json").exists()) if cfg.runs_dir.exists() else []
        _out(args, runs, "\n".join(runs) or "no runs")
        return EXIT_OK
    st = RunStore.resolve(cfg, args.run)
    if args.run_cmd == "phase":
        if args.phase not in PHASES:
            print(f"unknown phase {args.phase}; phases: {', '.join(PHASES)}")
            return EXIT_ERR
        st.journal("phase", phase=args.phase, state=args.state, note=args.note)
        print(f"{st.run_id}: phase {args.phase} -> {args.state}")
    elif args.run_cmd == "note":
        st.journal("note", kind=args.kind, text=args.text)
        print(f"{st.run_id}: {args.kind} noted")
    elif args.run_cmd == "finish":
        st.journal("run.finished")
        st.deactivate()
        print(f"{st.run_id}: finished (active-run marker cleared)")
    elif args.run_cmd == "status":
        execs = st.executions()
        from .findings import finding_views

        views = finding_views(st)
        data = {
            "dir": str(st.dir),
            "run": to_dict(st.info),
            "phases": st.phase_states(),
            "executions": [{"id": e.id, "adapter": e.adapter, "status": e.status.value, "counts": {k: v for k, v in e.counts.items() if v}, "groups": e.groups, "label": e.label} for e in execs],
            "findings": [{"id": v.finding.id, "title": v.finding.title, "severity": v.finding.severity.value, "status": v.effective_status.value} for v in views],
            "records": {k: (st.dir / f"{k}.json").exists() for k in ("profile", "requirements", "impact", "risks", "plan", "decision")},
        }
        lines = [f"run {st.run_id} ({st.info.mode}) — {st.info.scope}", "phases: " + ", ".join(f"{k}={v}" for k, v in data["phases"].items()), "records: " + ", ".join(k for k, v in data["records"].items() if v)]
        for e in data["executions"]:
            lines.append(f"  {e['id']} {e['adapter']:<10} {e['status']:<12} {e['counts']} {e['groups']} {e['label'] or ''}")
        for f in data["findings"]:
            lines.append(f"  {f['id']} [{f['severity']}] {f['status']}: {f['title']}")
        _out(args, data, "\n".join(lines))
    return EXIT_OK


def cmd_discover(args) -> int:
    from .discovery import discover

    cfg = _cfg(args)
    prof = discover(cfg.project_root, cfg.budgets.max_scan_files, cfg.project_name)
    try:
        st = RunStore.resolve(cfg, args.run)
        st.save_singleton("profile", prof, supersede=args.supersede)
        where = f"saved to {st.dir / 'profile.json'}"
    except StoreError as e:
        if "already exists" in str(e):
            print(f"error: {e}")
            return EXIT_ERR
        where = "not saved (no active run)"
    lines = [f"project: {prof.project_name} · files scanned: {prof.files_scanned} · {where}"]
    lines.append("languages: " + ", ".join(f"{lang.name}({lang.files})" for lang in prof.languages[:8]))
    for s in prof.test_suites:
        lines.append(f"test suite: {s.framework} {s.paths} files={s.test_files} -> {' '.join(s.suggested_command)}")
    for f in prof.facts:
        ev = f.evidence[0].path if f.evidence else ""
        lines.append(f"  [{f.basis.value}/{f.confidence.value}] {f.kind.value}: {f.name}  ({ev})")
    for u in prof.unknowns:
        lines.append(f"  UNKNOWN: {u}")
    _out(args, to_dict(prof), "\n".join(lines))
    return EXIT_OK


def cmd_impact(args) -> int:
    from .impact import analyze

    cfg = _cfg(args)
    try:
        data = analyze(cfg.project_root, args.base, args.head, not args.no_worktree)
    except RuntimeError as e:
        print(f"error: {e}")
        return EXIT_ERR
    try:
        st = RunStore.resolve(cfg, args.run)
        st.save_singleton("impact", data, supersede=args.supersede)
    except StoreError as e:
        if "already exists" in str(e):
            print(f"error: {e}")
            return EXIT_ERR
    lines = [f"diff {data['base']} -> {data['head']} ({len(data['files'])} files)"]
    for f in data["files"]:
        lines.append(f"  {f['status']} {f['path']} +{f['added']}/-{f['removed']} [{f['kind']}] {', '.join(f['signals'])}")
    lines.append("selected tests:")
    for t in data["selected_tests"]:
        lines.append(f"  {t['test']}  <- {'; '.join(t['reasons'])}")
    if data["changed_source_without_related_tests"]:
        lines.append("changed source with NO related tests: " + ", ".join(data["changed_source_without_related_tests"]))
    _out(args, data, "\n".join(lines))
    return EXIT_OK


def cmd_risk(args) -> int:
    from .impact import baseline_risks

    st = _store(args)
    reg = baseline_risks(st.load_singleton("profile"), st.load_singleton("impact"), st.config.critical_paths)
    st.save_singleton("risks", reg, supersede=args.supersede)
    lines = [f"baseline risk register ({len(reg.risks)} risks; refine with `qast record risks --supersede`):"]
    for r in reg.risks:
        lines.append(f"  {r.id} {r.level.value:<8} P{r.probability}xI{r.impact}={r.score:<3} {r.area}: " + "; ".join(f"{f.name}={f.value}" for f in r.factors))
    _out(args, to_dict(reg), "\n".join(lines))
    return EXIT_OK


RECORD_KINDS = {"requirements": m.RequirementSet, "risks": m.RiskRegister, "plan": m.TestPlan}


def cmd_record(args) -> int:
    st = _store(args)
    data = _read_input(args.file)
    if args.kind == "plan" and isinstance(data, dict):
        data.setdefault("id", f"TP-{st.run_id}")
    try:
        obj = from_dict(RECORD_KINDS[args.kind], data)
    except SchemaError as e:
        print(f"invalid {args.kind}: {e}\n(see `qast schema {RECORD_KINDS[args.kind].__name__} --template`)")
        return EXIT_ERR
    path = st.save_singleton(args.kind, obj, supersede=args.supersede)
    print(f"recorded {args.kind}: {path}")
    return EXIT_OK


def cmd_finding(args) -> int:
    st = _store(args)
    if args.finding_cmd == "add":
        data = _read_input(args.file)
        if not isinstance(data, dict):
            print("finding must be a JSON object")
            return EXIT_ERR
        data.setdefault("created_at", now_iso())
        paths = [a.get("path", "") for a in data.get("affected", []) if isinstance(a, dict)]
        data["id"] = st.finding_id(str(data.get("title", "")), paths, list(data.get("test_identifiers", [])))
        try:
            f = from_dict(m.DefectFinding, data)
        except SchemaError as e:
            print(f"invalid finding: {e}\n(see `qast schema DefectFinding --template`)")
            return EXIT_ERR
        from .findings import EvidenceIndex, evidence_problems

        probs = evidence_problems(f.evidence_ids, f.execution_ids, EvidenceIndex.build(st))
        if probs:
            print("refused: finding references evidence that does not exist or was modified:\n  " + "\n  ".join(probs))
            return EXIT_REFUSED
        st.save_finding(f)
        from .findings import finding_views

        view = next(v for v in finding_views(st) if v.finding.id == f.id)
        print(f"recorded finding {f.id} [{f.severity.value}] — derived status {view.effective_status.value}: {view.status_basis}")
        return EXIT_OK
    from .findings import finding_views

    views = finding_views(st)
    if args.finding_cmd == "list":
        _out(args, [to_dict(v) for v in views], "\n".join(f"{v.finding.id} [{v.finding.severity.value}/{v.finding.category.value}] {v.effective_status.value}: {v.finding.title}" for v in views) or "no findings")
    elif args.finding_cmd == "show":
        v = next((v for v in views if v.finding.id == args.id), None)
        if not v:
            print(f"no finding {args.id}")
            return EXIT_ERR
        print(json.dumps(to_dict(v), indent=2, ensure_ascii=False))
    return EXIT_OK


def _adapter_options(args) -> dict:
    return {
        "report": args.report,
        "ok_codes": args.ok_codes,
        "profile": args.profile,
        "viewport": args.viewport,
        "dataset": args.dataset,
        "target": args.entry,
        "samples": args.samples,
        "judge_model": args.judge_model,
        "calibration": args.calibration,
        "config": args.config,
        "via_uvx": args.via_uvx,
    }


def cmd_exec(args) -> int:
    from .adapters import ADAPTER_FUNCS
    from .adapters.base import AdapterRequest
    from .env import project_python

    cfg = _cfg(args)
    st = RunStore.resolve(cfg, args.run)
    cwd = (cfg.project_root / args.cwd).resolve() if args.cwd else cfg.project_root
    opts = _adapter_options(args)
    req = AdapterRequest(
        store=st,
        config=cfg,
        args=list(args.args or []),
        cwd=cwd,
        groups=args.group or [],
        label=args.label,
        timeout_s=args.timeout,
        python=args.python or project_python(cwd, cfg.python),
        targets=args.target or [],
        options=opts,
    )
    try:
        ex = ADAPTER_FUNCS[args.adapter](req)
    except ValueError as e:
        print(f"error: {e}")
        return EXIT_ERR
    _print_execution(args, ex)
    return EXIT_OK


def _print_execution(args, ex: m.TestExecution) -> None:
    counts = ", ".join(f"{k} {v}" for k, v in ex.counts.items() if v) or "no results"
    lines = [f"execution {ex.id}: {ex.status.value} ({counts}) in {ex.duration_s:.1f}s exit={ex.exit_code}"]
    if ex.status_reason:
        lines.append(f"  reason: {ex.status_reason}")
    for r in ex.results:
        if r.status in (m.Status.FAILED, m.Status.ERROR, m.Status.INCONCLUSIVE, m.Status.BLOCKED):
            msg = (r.message or "").strip().splitlines()
            e_lines = [ln[1:].strip() for ln in msg if ln.startswith("E ")]
            first = next((ln.strip() for ln in msg if ln.strip()), "")
            tail = (e_lines[0] if e_lines else first)[:200]
            lines.append(f"  {r.status.value}: {r.identifier} — {tail}")
    lines.append(f"  evidence: {', '.join(ex.artifact_ids) or 'none'}")
    _out(args, to_dict(ex), "\n".join(lines))


def cmd_reproduce(args) -> int:
    from .adapters import ADAPTER_FUNCS
    from .adapters.base import AdapterRequest
    from .env import project_python
    from .findings import classify_attempts

    cfg = _cfg(args)
    st = RunStore.resolve(cfg, args.run)
    times = min(args.times, cfg.budgets.max_reproduce_attempts)
    if times < args.times:
        print(f"note: attempts capped at budgets.max_reproduce_attempts={cfg.budgets.max_reproduce_attempts}")
    cwd = (cfg.project_root / args.cwd).resolve() if args.cwd else cfg.project_root
    extra = list(args.args or [])
    run_args = extra if extra else ([args.test] if args.adapter == "pytest" else [])
    if not run_args and args.adapter in ("junit", "command", "vitest", "jest", "playwright", "k6"):
        print("error: pass the command arguments that run only this test after --")
        return EXIT_ERR
    execs = []
    for i in range(1, times + 1):
        req = AdapterRequest(
            store=st, config=cfg, args=run_args, cwd=cwd, groups=args.group or [], label=f"reproduce {args.test} #{i}",
            timeout_s=args.timeout, python=args.python or project_python(cwd, cfg.python), attempt=i, reproduction_of=args.test,
            targets=args.target or [], options=_adapter_options(args),
        )
        ex = ADAPTER_FUNCS[args.adapter](req)
        execs.append(ex)
        if ex.status == m.Status.BLOCKED:
            break
    rep = classify_attempts(execs, [args.test])
    st.journal("reproduce", test=args.test, attempts=rep.attempts, failures=rep.failures, classification=rep.classification)
    data = to_dict(rep)
    _out(args, data, f"reproduction of {args.test}: {rep.failures}/{rep.attempts} attempts failed -> {rep.classification}\n  executions: {', '.join(rep.execution_ids)}")
    return EXIT_OK


def cmd_verify(args) -> int:
    from .findings import EvidenceIndex, verification_checks

    st = _store(args)
    f = next((x for x in st.findings() if x.id == args.finding), None)
    if f is None:
        print(f"no finding {args.finding}")
        return EXIT_ERR
    verdict = m.Verdict(args.verdict)
    idx = EvidenceIndex.build(st)
    checks = verification_checks(f, verdict, args.verifier, args.method, args.execution or [], args.evidence or [], idx, args.test or [])
    failed = [c for c in checks if not c.passed]
    if failed:
        print(f"refused: {verdict.value} is not supported by the evidence:")
        for c in failed:
            print(f"  ✗ {c.check}: {c.detail}")
        print("Record INCONCLUSIVE (with the reason) if the evidence cannot be completed.")
        return EXIT_REFUSED
    v = m.VerificationResult(
        id=st.verification_id(f.id, args.verifier),
        finding_id=f.id,
        verdict=verdict,
        method=args.method,
        verifier=args.verifier,
        rationale=args.rationale,
        created_at=now_iso(),
        evidence_ids=args.evidence or [],
        execution_ids=args.execution or [],
        test_identifiers=args.test or [],
        checks=checks,
    )
    st.save_verification(v)
    print(f"recorded verification {v.id}: {f.id} -> {verdict.value}")
    for c in checks:
        print(f"  ✓ {c.check}: {c.detail}")
    return EXIT_OK


def cmd_gate(args) -> int:
    from .findings import EvidenceIndex, finding_views
    from .policy import EXIT_CODES, GateInputs, evaluate, load_policy

    st = _store(args)
    pol_path = st.config.policy_path
    if args.policy:
        from .config import PLUGIN_ROOT

        cand = Path(args.policy)
        if not cand.is_absolute():
            for base in (Path.cwd(), st.config.project_root, PLUGIN_ROOT):
                if (base / cand).exists():
                    cand = base / cand
                    break
        pol_path = cand
    policy = load_policy(pol_path)
    idx = EvidenceIndex.build(st)
    reg = st.load_singleton("risks")
    inp = GateInputs(
        executions=st.executions(),
        findings=finding_views(st, idx),
        plan=st.load_singleton("plan"),
        risks=reg.risks if reg else [],
        artifact_problems=sorted(set(idx.artifact_problems.values())),
        verifications=st.verifications(),
    )
    dec = evaluate(policy, inp)
    st.save_singleton("decision", dec, supersede=True)
    lines = [f"DECISION: {dec.decision.value}  (policy {policy.name} v{policy.version})"]
    for r in dec.rules:
        mark = "!!" if r.triggered else "ok"
        lines.append(f"  [{mark}] {r.rule_id}: {r.outcome.value if r.triggered else 'satisfied'} — {r.reason[:220]}")
    _out(args, to_dict(dec), "\n".join(lines))
    return EXIT_CODES[dec.decision] if args.exit_code else EXIT_OK


def cmd_report(args) -> int:
    from .report import write_report

    st = _store(args)
    jp, mp = write_report(st)
    if args.print:
        print(mp.read_text(encoding="utf-8"))
    else:
        print(f"report: {mp}\njson:   {jp}")
    return EXIT_OK


def cmd_validate(args) -> int:
    st = _store(args)
    problems = []
    checked = 0
    for sub, cls in (("executions", m.TestExecution), ("findings", m.DefectFinding), ("verifications", m.VerificationResult), ("evidence", m.EvidenceArtifact)):
        d = st.dir / sub
        for p in sorted(d.glob("*.json")) if d.exists() else []:
            checked += 1
            try:
                from_dict(cls, read_json(p))
            except SchemaError as e:
                problems.append(f"{sub}/{p.name}: {e}")
    from .store import SINGLETONS

    for name, cls in SINGLETONS.items():
        p = st.dir / f"{name}.json"
        if p.exists() and cls is not dict:
            checked += 1
            try:
                from_dict(cls, read_json(p))
            except SchemaError as e:
                problems.append(f"{name}.json: {e}")
    for a in st.artifacts():
        pr = st.verify_artifact(a)
        if pr:
            problems.append(pr)
    print(f"validated {checked} records and {len(st.artifacts())} artifacts: {len(problems)} problem(s)")
    for p in problems:
        print("  " + p)
    return EXIT_OK if not problems else EXIT_ERR


def cmd_schema(args) -> int:
    if not args.name:
        print("\n".join(sorted(m.EXPORTED_MODELS)))
        return EXIT_OK
    cls = m.EXPORTED_MODELS.get(args.name)
    if cls is None:
        print(f"unknown model {args.name}; choose from: {', '.join(sorted(m.EXPORTED_MODELS))}")
        return EXIT_ERR
    if args.template:
        from .templates import TEMPLATES

        tpl = TEMPLATES.get(args.name)
        if tpl is None:
            print(f"no template for {args.name}; schema follows")
        else:
            print(json.dumps(tpl, indent=2))
            return EXIT_OK
    print(json.dumps(json_schema(cls), indent=2))
    return EXIT_OK


def cmd_redact(args) -> int:
    from .redact import Redactor

    cfg = _cfg(args)
    r = Redactor.from_config(cfg.redaction_patterns, cfg.redact_emails)
    text = sys.stdin.read() if args.file in (None, "-") else Path(args.file).read_text(encoding="utf-8", errors="replace")
    sys.stdout.write(r.redact(text))
    print(f"\n[qast redact: {r.count} redaction(s) {r.by_label}]", file=sys.stderr)
    return EXIT_OK


def cmd_ai_eval(args) -> int:
    from . import aieval

    if args.ai_cmd == "validate":
        try:
            cases = aieval.parse_dataset(Path(args.dataset).read_text(encoding="utf-8"))
        except aieval.DatasetError as e:
            print(f"invalid dataset: {e}")
            return EXIT_ERR
        judged = sum(1 for c in cases if c.get("judge"))
        print(f"{args.dataset}: {len(cases)} valid case(s), {judged} with model-graded checks")
        return EXIT_OK
    if args.ai_cmd == "calibrate":

        def load(p):
            out = {}
            for line in Path(p).read_text(encoding="utf-8").splitlines():
                if line.strip():
                    rec = json.loads(line)
                    out[rec["id"]] = str(rec["label"]).lower()
            return out

        res = aieval.calibrate(load(args.judgments), load(args.labels))
        res["judge_model"] = args.judge_model
        res["rubric_id"] = args.rubric_id
        Path(args.out).write_text(json.dumps(res, indent=2), encoding="utf-8")
        k = res["kappa"]
        print(f"calibration over {res['n']} case(s): agreement {res['agreement']}, kappa {None if k is None else round(k, 3)} -> {args.out}")
        if res["n"] < aieval.MIN_CALIBRATION_N:
            print(f"warning: n < {aieval.MIN_CALIBRATION_N}; this calibration will NOT make the judge trusted")
        return EXIT_OK
    return EXIT_ERR


# ----------------------------------------------------------------------------- parser


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="qast", description="QA Superteam deterministic tooling (evidence, execution, policy, reports).")
    p.add_argument("--version", action="version", version=f"qast {__version__}")
    p.add_argument("--project", default=".", help="project root (default: current directory)")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp, run=True, js=True):
        if run:
            sp.add_argument("--run", help="run id (default: active run)")
        if js:
            sp.add_argument("--json", action="store_true", help="machine-readable output")

    sp = sub.add_parser("doctor", help="detect available test tools and capabilities")
    common(sp, run=False)
    sp.set_defaults(func=cmd_doctor)

    sp = sub.add_parser("init", help="write .qa-superteam/config.toml with safe defaults")
    sp.add_argument("--force", action="store_true")
    sp.set_defaults(func=cmd_init)

    sp = sub.add_parser("run", help="start/inspect/finish a QA run (checkpointed, resumable)")
    rs = sp.add_subparsers(dest="run_cmd", required=True)
    x = rs.add_parser("start")
    x.add_argument("--mode", required=True, choices=MODES)
    x.add_argument("--scope", required=True, help="what is under test, in words")
    x.add_argument("--base", help="base git ref for diff-based modes")
    x.add_argument("--head", help="head git ref (default: working tree)")
    common(x, run=False)
    x = rs.add_parser("status")
    common(x)
    x = rs.add_parser("phase")
    x.add_argument("phase", choices=PHASES)
    x.add_argument("state", choices=["started", "done", "skipped", "blocked"])
    x.add_argument("--note")
    common(x, js=False)
    x = rs.add_parser("note")
    x.add_argument("text")
    x.add_argument("--kind", choices=["limitation", "assumption", "decision"], default="limitation")
    common(x, js=False)
    x = rs.add_parser("finish")
    common(x, js=False)
    x = rs.add_parser("list")
    common(x, run=False)
    sp.set_defaults(func=cmd_run)

    sp = sub.add_parser("discover", help="deterministic project profile (Phase A)")
    sp.add_argument("--supersede", action="store_true")
    common(sp)
    sp.set_defaults(func=cmd_discover)

    sp = sub.add_parser("impact", help="change impact from a git diff (Phase C)")
    sp.add_argument("--base", required=True)
    sp.add_argument("--head")
    sp.add_argument("--no-worktree", action="store_true", help="ignore uncommitted changes")
    sp.add_argument("--supersede", action="store_true")
    common(sp)
    sp.set_defaults(func=cmd_impact)

    sp = sub.add_parser("risk", help="baseline risk register from profile + impact (Phase D)")
    sp.add_argument("--supersede", action="store_true")
    common(sp)
    sp.set_defaults(func=cmd_risk)

    sp = sub.add_parser("record", help="validate and store requirements | risks | plan JSON")
    sp.add_argument("kind", choices=sorted(RECORD_KINDS))
    sp.add_argument("--file", required=True, help="JSON file or - for stdin")
    sp.add_argument("--supersede", action="store_true")
    common(sp, js=False)
    sp.set_defaults(func=cmd_record)

    sp = sub.add_parser("finding", help="record and inspect defect findings")
    fs = sp.add_subparsers(dest="finding_cmd", required=True)
    x = fs.add_parser("add")
    x.add_argument("--file", required=True)
    common(x, js=False)
    x = fs.add_parser("list")
    common(x)
    x = fs.add_parser("show")
    x.add_argument("id")
    common(x, js=False)
    sp.set_defaults(func=cmd_finding)

    def exec_opts(sp):
        sp.add_argument("--group", action="append", help="policy group tag (repeatable), e.g. existing-suite")
        sp.add_argument("--label")
        sp.add_argument("--timeout", type=int)
        sp.add_argument("--cwd", help="directory to run in, relative to project root")
        sp.add_argument("--python", help="interpreter for Python-based tools (default: project venv or python3)")
        sp.add_argument("--report", help="junit: path of the JUnit XML the command writes")

    def adapter_opts(sp):
        sp.add_argument("--target", action="append", help="URL under test (must be in permissions.authorized_targets)")
        sp.add_argument("--ok-codes", help="command: comma-separated success exit codes (default 0)")
        sp.add_argument("--profile", choices=["smoke", "load"], help="k6 profile (default smoke)")
        sp.add_argument("--viewport", help="axe: WIDTHxHEIGHT")
        sp.add_argument("--dataset", help="ai-eval: JSONL dataset")
        sp.add_argument("--entry", help="ai-eval: module:function under test")
        sp.add_argument("--samples", type=int, help="ai-eval: samples per case (nondeterminism check)")
        sp.add_argument("--judge-model", help="ai-eval: enable model-graded checks")
        sp.add_argument("--calibration", help="ai-eval: calibration.json for the judge")
        sp.add_argument("--config", help="semgrep: rules config")
        sp.add_argument("--via-uvx", action="store_true", help="security scanners: run via uvx if not installed (downloads the tool)")

    sp = sub.add_parser("exec", help="run a real test tool through an adapter and record evidence")
    sp.add_argument("adapter", choices=ADAPTERS)
    exec_opts(sp)
    adapter_opts(sp)
    common(sp)
    sp.set_defaults(func=cmd_exec)

    sp = sub.add_parser("reproduce", help="re-run one test N times and classify (consistent/intermittent/not-reproduced)")
    sp.add_argument("--test", required=True, help="test identifier, e.g. tests/test_x.py::test_y")
    sp.add_argument("--adapter", default="pytest", choices=ADAPTERS)
    sp.add_argument("--times", type=int, default=3)
    exec_opts(sp)
    adapter_opts(sp)
    common(sp)
    sp.set_defaults(func=cmd_reproduce)

    sp = sub.add_parser("verify", help="record an independent verification verdict (evidence-gated)")
    sp.add_argument("finding")
    sp.add_argument("--verdict", required=True, choices=[v.value for v in m.Verdict])
    sp.add_argument("--method", required=True, choices=["independent-rerun", "alternate-oracle", "code-inspection", "manual"])
    sp.add_argument("--verifier", required=True, help="agent or person performing verification (must differ from reporter to confirm)")
    sp.add_argument("--rationale", required=True)
    sp.add_argument("--execution", action="append", help="execution id run by the verifier (repeatable)")
    sp.add_argument("--evidence", action="append", help="artifact id (repeatable)")
    sp.add_argument("--test", action="append", help="test identifier the verifier used (alternate oracle)")
    common(sp, js=False)
    sp.set_defaults(func=cmd_verify)

    sp = sub.add_parser("gate", help="deterministic release decision from recorded evidence (Phase J)")
    sp.add_argument("--policy", help="policy TOML (default: config [policy] path or plugin default)")
    sp.add_argument("--exit-code", action="store_true", help="exit 0 PASS / 10 REVIEW_REQUIRED / 20 BLOCK (for CI)")
    common(sp)
    sp.set_defaults(func=cmd_gate)

    sp = sub.add_parser("report", help="render report.md and report.json from records (Phase K)")
    sp.add_argument("--print", action="store_true")
    common(sp, js=False)
    sp.set_defaults(func=cmd_report)

    sp = sub.add_parser("validate", help="validate run records against schemas and artifact hashes")
    common(sp, js=False)
    sp.set_defaults(func=cmd_validate)

    sp = sub.add_parser("schema", help="print a JSON Schema or fill-in template")
    sp.add_argument("name", nargs="?")
    sp.add_argument("--template", action="store_true")
    sp.set_defaults(func=cmd_schema)

    sp = sub.add_parser("redact", help="redact secrets/PII from a file or stdin")
    sp.add_argument("file", nargs="?")
    sp.set_defaults(func=cmd_redact)

    sp = sub.add_parser("ai-eval", help="AI eval utilities")
    ai = sp.add_subparsers(dest="ai_cmd", required=True)
    x = ai.add_parser("validate")
    x.add_argument("dataset")
    x = ai.add_parser("calibrate", help="judge vs human labels -> agreement and Cohen's kappa")
    x.add_argument("--judgments", required=True, help="JSONL {id, label}")
    x.add_argument("--labels", required=True, help="human JSONL {id, label}")
    x.add_argument("--judge-model", required=True, help="model id the judgments came from (calibration is bound to it)")
    x.add_argument("--rubric-id", default="", help="identifier/hash of the rubric version the judgments used")
    x.add_argument("--out", default="calibration.json")
    sp.set_defaults(func=cmd_ai_eval)
    return p


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    tool_args: list[str] = []
    if "--" in argv:  # everything after the first "--" belongs to the wrapped tool
        i = argv.index("--")
        argv, tool_args = argv[:i], argv[i + 1 :]
    parser = build_parser()
    args = parser.parse_args(argv)
    args.args = tool_args
    try:
        return args.func(args)
    except (StoreError, ConfigError) as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_ERR
    except Exception as e:  # noqa: BLE001
        from .policy import PolicyError

        if isinstance(e, PolicyError):
            print(f"policy error: {e}", file=sys.stderr)
            return EXIT_ERR
        raise


if __name__ == "__main__":
    raise SystemExit(main())
