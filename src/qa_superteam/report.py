"""Coverage assessment and report rendering (Phase K).

Reports are generated *only* from recorded records.  Nothing in a report is typed by
an agent directly: statuses come from executions, finding statuses are derived, the
decision comes from the policy engine, and coverage percentages appear only when a
coverage tool produced them.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import models as m
from .findings import EvidenceIndex, finding_views
from .policy import _latest_status
from .store import RunStore
from .util import now_iso

S = m.Status
STATUS_ORDER = [S.FAILED, S.ERROR, S.INCONCLUSIVE, S.BLOCKED, S.NOT_RUN, S.SKIPPED, S.PASSED]


def measured_metrics(store: RunStore, arts: list[m.EvidenceArtifact]) -> list[m.MeasuredMetric]:
    out = []
    for a in arts:
        name = a.path.rsplit("/", 1)[-1]
        if not name.endswith(".json") or "coverage" not in name:
            continue
        try:
            data = json.loads((store.dir / a.path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict) and "totals" in data and "percent_covered" in data["totals"]:
            out.append(m.MeasuredMetric("line coverage", round(float(data["totals"]["percent_covered"]), 2), "%", "coverage.py", a.id))
        elif isinstance(data, dict) and "total" in data and isinstance(data["total"], dict) and "lines" in data["total"]:
            out.append(m.MeasuredMetric("line coverage", float(data["total"]["lines"]["pct"]), "%", "istanbul json-summary", a.id))
    return out


def coverage_assessment(store: RunStore, executions: list[m.TestExecution], plan: m.TestPlan | None, reqs: m.RequirementSet | None, risks: list[m.RiskAssessment], impact: dict | None, arts) -> m.CoverageAssessment:
    primary = [e for e in executions if not e.reproduction_of]
    counts = {s.value: 0 for s in S}
    for e in primary:
        if not e.results:
            counts[e.status.value] += 1  # a BLOCKED/NOT_RUN execution counts once
        for r in e.results:
            counts[r.status.value] += 1
    trace: list[m.TraceRow] = []
    untested: list[m.UntestedArea] = []
    if plan:
        by_item: dict[str, list[m.TestCase]] = {}
        for tc in plan.test_cases:
            for iid in tc.requirement_ids + tc.invariant_ids + tc.risk_ids:
                by_item.setdefault(iid, []).append(tc)
        items = []
        if reqs:
            items += [r.id for r in reqs.requirements] + [i.id for i in reqs.invariants]
        items += [r.id for r in risks]
        for iid in list(dict.fromkeys(items + sorted(by_item))):
            tcs = by_item.get(iid, [])
            statuses = []
            for tc in tcs:
                st = _latest_status(primary, tc.test_ref) if tc.test_ref else None
                statuses.append(st or S.NOT_RUN)
            trace.append(m.TraceRow(item_id=iid, test_case_ids=[t.id for t in tcs], statuses=statuses))
            if not tcs:
                untested.append(m.UntestedArea(area=iid, reason="no planned test case traces to this item", risk=_item_risk(iid, reqs, risks)))
            elif not any(s in (S.PASSED, S.FAILED) for s in statuses):
                untested.append(m.UntestedArea(area=iid, reason="planned tests did not reach a pass/fail outcome: " + ", ".join(sorted({s.value for s in statuses})), risk=_item_risk(iid, reqs, risks)))
        for oos in plan.out_of_scope:
            untested.append(m.UntestedArea(area=oos.item, reason=f"out of scope: {oos.reason}", risk=m.Severity.INFO))
    if impact:
        for path in impact.get("changed_source_without_related_tests", []):
            untested.append(m.UntestedArea(area=path, reason="changed source file with no related test selected", risk=m.Severity.MEDIUM))
    for e in primary:
        if e.status == S.BLOCKED:
            untested.append(m.UntestedArea(area=f"{e.adapter} ({e.label or ' '.join(e.command)[:60]})", reason=f"BLOCKED: {e.status_reason}", risk=m.Severity.MEDIUM))
    return m.CoverageAssessment(measured=measured_metrics(store, arts), traceability=trace, untested=untested, status_counts=counts)


def _item_risk(iid: str, reqs: m.RequirementSet | None, risks: list[m.RiskAssessment]) -> m.Severity:
    for r in risks:
        if r.id == iid:
            return r.level
    if reqs:
        for q in reqs.requirements:
            if q.id == iid:
                return q.priority
        for inv in reqs.invariants:
            if inv.id == iid:
                return inv.criticality
    return m.Severity.MEDIUM


def build_report(store: RunStore) -> m.QAReport:
    idx = EvidenceIndex.build(store)
    views = finding_views(store, idx)
    execs = store.executions()
    plan = store.load_singleton("plan")
    reqs = store.load_singleton("requirements")
    risk_reg = store.load_singleton("risks")
    risks = risk_reg.risks if risk_reg else []
    impact = store.load_singleton("impact")
    profile = store.load_singleton("profile")
    decision = store.load_singleton("decision")
    arts = sorted(idx.artifacts.values(), key=lambda a: a.path)
    coverage = coverage_assessment(store, execs, plan, reqs, risks, impact, arts)
    limitations = []
    for ev in store.journal_events():
        if ev.get("event") == "note" and ev.get("kind") == "limitation":
            limitations.append(ev.get("text", ""))
    for e in execs:
        if e.status in (S.BLOCKED, S.NOT_RUN):
            limitations.append(f"{e.adapter} execution {e.id} {e.status.value}: {e.status_reason}")
    if profile:
        limitations += [f"Discovery: {u}" for u in profile.unknowns]
    phases = store.phase_states()
    skipped = [p for p, s in phases.items() if s == "skipped"]
    if skipped:
        limitations.append("Phases skipped in this run: " + ", ".join(skipped))
    limitations.append("Evidence redaction is pattern-based and best-effort; review artifacts before sharing externally.")
    integrity = sorted(set(idx.artifact_problems.values()))
    if decision is None:
        limitations.append("No release decision was computed (run `qast gate`).")
    elif decision.inputs_digest:
        from .policy import GateInputs, load_policy

        try:
            pol = load_policy(store.config.policy_path)
            cur = GateInputs(executions=execs, findings=views, plan=plan, risks=risks, artifact_problems=integrity).digest(pol)
            if cur != decision.inputs_digest:
                integrity.append("decision.json is stale: evidence changed after `qast gate` ran; re-run the gate")
        except Exception as e:  # noqa: BLE001
            integrity.append(f"could not re-check decision digest: {e}")
    profile_summary = {}
    if profile:
        profile_summary = {
            "project": profile.project_name,
            "languages": [f"{lang.name} ({lang.files})" for lang in profile.languages[:6]],
            "test_suites": [f"{s.framework}: {', '.join(s.paths)} ({s.test_files} files)" for s in profile.test_suites],
            "facts": len(profile.facts),
            "git_head": profile.git.head,
        }
    return m.QAReport(
        schema_version=m.SCHEMA_VERSION,
        run=store.info,
        generated_at=now_iso(),
        decision=decision,
        executions=execs,
        findings=views,
        verifications=store.verifications(),
        coverage=coverage,
        artifacts=arts,
        limitations=limitations,
        phases=phases,
        plan=plan,
        risks=risks,
        requirements=reqs,
        profile_summary=profile_summary,
        integrity_warnings=integrity,
    )


# --------------------------------------------------------------------------- markdown


def _esc(s: str | None, n: int = 160) -> str:
    s = (s or "").replace("|", "\\|").replace("\n", " ").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def render_markdown(rep: m.QAReport) -> str:
    L: list[str] = []
    run = rep.run
    L.append(f"# QA Report — {run.project_name} ({run.mode})")
    L.append("")
    L.append(f"Run `{run.run_id}` · scope: {run.scope} · generated {rep.generated_at}")
    if run.base_ref:
        L.append(f"Diff: `{run.base_ref}` → `{run.head_ref or 'working tree'}`")
    L.append("")
    if rep.decision:
        d = rep.decision
        icon = {"PASS": "✅", "REVIEW_REQUIRED": "⚠️", "BLOCK": "⛔"}[d.decision.value]
        L.append(f"## {icon} Release decision: **{d.decision.value}**")
        L.append("")
        L.append(f"Policy `{d.policy.name}` v{d.policy.version} (sha256 `{d.policy.sha256[:12]}`) · evaluated {d.evaluated_at} · inputs digest `{d.inputs_digest[:12]}`")
        L.append("")
        trig = [r for r in d.rules if r.triggered]
        if trig:
            L.append("| Rule | Outcome | Reason |")
            L.append("|---|---|---|")
            for r in trig:
                L.append(f"| `{r.rule_id}` | {r.outcome.value} | {_esc(r.reason, 300)} |")
            L.append("")
        ok = [r for r in d.rules if not r.triggered]
        if ok:
            L.append("<details><summary>Rules satisfied (" + str(len(ok)) + ")</summary>\n")
            for r in ok:
                L.append(f"- `{r.rule_id}` — {_esc(r.reason, 200)}")
            L.append("\n</details>\n")
    else:
        L.append("## Release decision: not evaluated")
        L.append("")
    if rep.integrity_warnings:
        L.append("> **Integrity warnings:** " + "; ".join(rep.integrity_warnings))
        L.append("")

    # summary
    L.append("## Summary")
    L.append("")
    c = rep.coverage.status_counts
    L.append("| " + " | ".join(s.value for s in STATUS_ORDER) + " |")
    L.append("|" + "---|" * len(STATUS_ORDER))
    L.append("| " + " | ".join(str(c.get(s.value, 0)) for s in STATUS_ORDER) + " |")
    L.append("")
    fcount: dict[str, int] = {}
    for v in rep.findings:
        fcount[v.effective_status.value] = fcount.get(v.effective_status.value, 0) + 1
    L.append(f"Executions: {len(rep.executions)} · Findings: {len(rep.findings)} " + (f"({', '.join(f'{k} {n}' for k, n in sorted(fcount.items()))})" if fcount else ""))
    L.append("")

    # findings
    L.append("## Findings")
    L.append("")
    if not rep.findings:
        L.append("No defect findings were recorded.")
        L.append("")
    order = {m.FindingStatus.CONFIRMED: 0, m.FindingStatus.REPRODUCED: 1, m.FindingStatus.INCONCLUSIVE: 2, m.FindingStatus.SUSPECTED: 3, m.FindingStatus.NOT_REPRODUCED: 4, m.FindingStatus.REJECTED: 5}
    for v in sorted(rep.findings, key=lambda v: (order[v.effective_status], -m.SEVERITY_RANK[v.finding.severity], v.finding.id)):
        f = v.finding
        L.append(f"### {f.id} · {f.title}")
        L.append("")
        L.append(f"**{v.effective_status.value}** · severity **{f.severity.value}** · {f.category.value} · reported by {f.reported_by}")
        L.append("")
        L.append(f"_Status basis:_ {v.status_basis}")
        if v.integrity_problems:
            L.append(f"\n> Evidence problems: {'; '.join(v.integrity_problems)}")
        L.append("")
        L.append(f"- **Expected:** {f.expected}")
        L.append(f"- **Actual:** {f.actual}")
        if f.affected:
            L.append("- **Location:** " + ", ".join(f"`{a.path}{':' + str(a.line) if a.line else ''}{' (' + a.symbol + ')' if a.symbol else ''}`" for a in f.affected))
        if f.test_identifiers:
            L.append("- **Tests:** " + ", ".join(f"`{t}`" for t in f.test_identifiers))
        if f.inputs:
            L.append(f"- **Inputs:** `{_esc(json.dumps(f.inputs), 300)}`")
        L.append("- **Reproduction steps:**")
        for i, step in enumerate(f.reproduction_steps, 1):
            L.append(f"  {i}. {step}")
        if f.hypotheses:
            L.append("- **Root-cause hypotheses** (not findings unless marked confirmed):")
            for h in f.hypotheses:
                tag = "CONFIRMED by " + ", ".join(h.evidence_ids) if h.confirmed else f"hypothesis, {h.confidence.value} confidence"
                L.append(f"  - {h.statement} — _{tag}_")
        ev = f.evidence_ids + [x for vr in rep.verifications if vr.finding_id == f.id for x in vr.evidence_ids]
        if ev:
            arts = {a.id: a for a in rep.artifacts}
            L.append("- **Evidence:** " + ", ".join(f"[`{e}`]({arts[e].path})" if e in arts else f"`{e}` (missing)" for e in dict.fromkeys(ev)))
        vs = [vr for vr in rep.verifications if vr.finding_id == f.id]
        for vr in vs:
            L.append(f"- **Verification {vr.id}:** {vr.verdict.value} by {vr.verifier} via {vr.method} — {_esc(vr.rationale, 300)}")
        if f.regression_test:
            L.append(f"- **Regression test:** `{f.regression_test}`")
        L.append("")

    # executions
    L.append("## Test executions")
    L.append("")
    L.append("| Execution | Adapter | Label / groups | Status | P/F/E/S/B/NR/I | Duration | Note |")
    L.append("|---|---|---|---|---|---|---|")
    for e in rep.executions:
        cc = e.counts
        counts = "/".join(str(cc.get(k, 0)) for k in ("PASSED", "FAILED", "ERROR", "SKIPPED", "BLOCKED", "NOT_RUN", "INCONCLUSIVE"))
        lab = (e.label or "") + (f" [{', '.join(e.groups)}]" if e.groups else "")
        if e.reproduction_of:
            lab += f" (repro attempt {e.attempt} of `{_esc(e.reproduction_of, 60)}`)"
        L.append(f"| `{e.id}` | {e.adapter} | {_esc(lab, 80)} | **{e.status.value}** | {counts} | {e.duration_s:.1f}s | {_esc(e.status_reason, 120)} |")
    L.append("")
    bad = [(e, r) for e in rep.executions for r in e.results if r.status in (S.FAILED, S.ERROR, S.INCONCLUSIVE) and not e.reproduction_of]
    if bad:
        L.append("<details><summary>Failing, errored and inconclusive results (" + str(len(bad)) + ")</summary>\n")
        for e, r in bad[:200]:
            L.append(f"- **{r.status.value}** `{r.identifier}` ({e.id}): {_esc(r.message, 400)}")
        L.append("\n</details>\n")

    # coverage
    cov = rep.coverage
    L.append("## Coverage & traceability")
    L.append("")
    if cov.measured:
        for mm in cov.measured:
            L.append(f"- {mm.metric}: **{mm.value}{mm.unit}** (measured by {mm.tool}, evidence `{mm.artifact_id}`)")
    else:
        L.append("- No coverage percentage reported: no coverage tool output was recorded. (QA Superteam never estimates coverage.)")
    L.append("")
    if cov.traceability:
        L.append("| Item | Test cases | Latest statuses |")
        L.append("|---|---|---|")
        for t in cov.traceability:
            L.append(f"| {t.item_id} | {', '.join(t.test_case_ids) or '—'} | {', '.join(s.value for s in t.statuses) or '—'} |")
        L.append("")
    if cov.untested:
        L.append("**Not verified by this run:**")
        L.append("")
        for u in cov.untested:
            L.append(f"- [{u.risk.value}] {u.area} — {u.reason}")
        L.append("")

    if rep.risks:
        L.append("## Risk register")
        L.append("")
        L.append("| Risk | Area | P×I | Level | Key factors |")
        L.append("|---|---|---|---|---|")
        for r in rep.risks:
            L.append(f"| {r.id} | {_esc(r.area, 40)} | {r.probability}×{r.impact}={r.score} | {r.level.value} | {_esc('; '.join(f'{f.name}: {f.rationale}' for f in r.factors), 160)} |")
        L.append("")

    if rep.plan:
        p = rep.plan
        L.append("## Test plan")
        L.append("")
        L.append(_esc(p.strategy_summary, 2000))
        L.append("")
        L.append("| Case | Title | Level / technique | Groups | Priority | Origin | Ref |")
        L.append("|---|---|---|---|---|---|---|")
        for tc in p.test_cases:
            L.append(f"| {tc.id} | {_esc(tc.title, 60)} | {tc.level} / {tc.technique} | {', '.join(tc.groups)} | {tc.priority.value} | {tc.origin.value} | `{_esc(tc.test_ref, 70)}` |")
        L.append("")

    L.append("## Workflow phases")
    L.append("")
    L.append(", ".join(f"{k}: {v}" for k, v in rep.phases.items()))
    L.append("")
    L.append("## Limitations & what was not verified")
    L.append("")
    for lim in dict.fromkeys(rep.limitations):
        L.append(f"- {lim}")
    L.append("")
    L.append("## Scope & environment")
    L.append("")
    env = rep.run.environment
    if rep.profile_summary:
        L.append(f"- Project: {rep.profile_summary.get('project')} · languages: {', '.join(rep.profile_summary.get('languages', []))}")
        if rep.profile_summary.get("test_suites"):
            L.append(f"- Test suites: {'; '.join(rep.profile_summary['test_suites'])}")
    if env:
        L.append(f"- Platform: {env.platform} · Python {env.python} · CI: {env.ci} · git HEAD `{(env.git_head or 'n/a')[:12]}` dirty={env.git_dirty}")
    tools: dict[str, str] = {}
    for e in rep.executions:
        tools.update(e.environment.tool_versions)
    if tools:
        L.append("- Tools: " + ", ".join(f"{k} `{_esc(v, 60)}`" for k, v in sorted(tools.items())))
    L.append("")
    L.append("## Evidence index")
    L.append("")
    L.append("| Artifact | Kind | Path | sha256 | Redactions |")
    L.append("|---|---|---|---|---|")
    for a in rep.artifacts:
        L.append(f"| `{a.id}` | {a.kind.value} | [{a.path.rsplit('/', 1)[-1]}]({a.path}) | `{a.sha256[:16]}` | {a.redactions} |")
    L.append("")
    L.append("_Generated by QA Superteam from recorded evidence. Statuses are normalized tool results; finding statuses are derived from reproduction and verification records; the decision is computed by the deterministic policy engine._")
    return "\n".join(L) + "\n"


def write_report(store: RunStore) -> tuple[Path, Path]:
    from .serde import to_dict
    from .util import write_json_atomic

    rep = build_report(store)
    jp = store.dir / "report.json"
    mp = store.dir / "report.md"
    write_json_atomic(jp, to_dict(rep))
    mp.write_text(render_markdown(rep), encoding="utf-8")
    store.journal("report.written", markdown=str(mp.name), json=str(jp.name))
    return jp, mp
