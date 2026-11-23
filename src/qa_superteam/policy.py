"""Deterministic release gate (Phase J).

``evaluate(policy, inputs) -> ReleaseDecision`` is a pure function of the policy and
the recorded QA evidence.  It never consults a model.  The same inputs always yield
the same decision and the same ``inputs_digest``.

Decision = the most severe outcome among triggered rules (BLOCK > REVIEW_REQUIRED >
PASS).  PASS additionally requires positive evidence: at least one mandatory check
executed and passed.  Skipped, blocked or not-run mandatory checks are never treated
as passed.
"""

from __future__ import annotations

import hashlib
import json
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import models as m
from .serde import to_dict
from .util import now_iso

D, S, FS, SEV = m.Decision, m.Status, m.FindingStatus, m.Severity
# Scanner hits are candidates (triaged via qa-security); AI eval cases have their own rules.
CANDIDATE_ADAPTERS = {"bandit", "pip-audit", "npm-audit", "semgrep", "gitleaks", "ai-eval"}
_DEC = {"PASS": D.PASS, "REVIEW_REQUIRED": D.REVIEW_REQUIRED, "REVIEW": D.REVIEW_REQUIRED, "BLOCK": D.BLOCK}


class PolicyError(ValueError):
    pass


@dataclass
class Policy:
    name: str
    version: str
    path: str
    sha256: str
    severity_definitions: dict[str, str]
    block_at: dict[str, SEV]
    review_at: dict[str, SEV]
    unverified_review_at: SEV
    mandatory_groups: list[str]
    mandatory_if_planned: list[str]
    critical_groups: list[str]
    on_fail: D
    on_missing: D
    on_error: D
    on_inconclusive: D
    max_skipped_in_mandatory: int
    ai_min_pass_rate: float | None
    ai_below_threshold: D
    ai_inconclusive: D
    untested_high_risk: D
    max_untested_high_risk: int
    require_executions: D
    integrity_violation: D
    untriaged_failures: D
    raw: dict[str, Any] = field(default_factory=dict)


def _sev(v: str, where: str) -> SEV:
    try:
        return SEV(v)
    except ValueError:
        raise PolicyError(f"{where}: unknown severity {v!r}") from None


def _dec(v: str, where: str) -> D:
    if v not in _DEC:
        raise PolicyError(f"{where}: unknown decision {v!r} (use PASS, REVIEW_REQUIRED or BLOCK)")
    return _DEC[v]


def load_policy(path: Path) -> Policy:
    raw_bytes = path.read_bytes()
    try:
        data = tomllib.loads(raw_bytes.decode("utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise PolicyError(f"{path}: {e}") from None
    known = {"policy", "severity_definitions", "findings", "groups", "ai_eval", "coverage", "evidence"}
    unknown = set(data) - known
    if unknown:
        raise PolicyError(f"{path}: unknown section(s) {sorted(unknown)}")
    meta = data.get("policy", {})
    fnd = data.get("findings", {})
    grp = data.get("groups", {})
    ai = data.get("ai_eval", {})
    cov = data.get("coverage", {})
    ev = data.get("evidence", {})
    block_at = {k: _sev(v, f"findings.block_at.{k}") for k, v in (fnd.get("block_at") or {"default": "critical"}).items()}
    review_at = {k: _sev(v, f"findings.review_at.{k}") for k, v in (fnd.get("review_at") or {"default": "high"}).items()}
    for k in list(block_at) + list(review_at):
        if k != "default" and k not in {c.value for c in m.Category}:
            raise PolicyError(f"{path}: unknown finding category {k!r}")
    return Policy(
        name=str(meta.get("name", path.stem)),
        version=str(meta.get("version", "0")),
        path=str(path),
        sha256=hashlib.sha256(raw_bytes).hexdigest(),
        severity_definitions=dict(data.get("severity_definitions", {})),
        block_at=block_at,
        review_at=review_at,
        unverified_review_at=_sev(fnd.get("unverified_review_at", "high"), "findings.unverified_review_at"),
        mandatory_groups=list(grp.get("mandatory", [])),
        mandatory_if_planned=list(grp.get("mandatory_if_planned", [])),
        critical_groups=list(grp.get("critical", [])),
        on_fail=_dec(grp.get("on_fail", "BLOCK"), "groups.on_fail"),
        on_missing=_dec(grp.get("on_missing", "REVIEW_REQUIRED"), "groups.on_missing"),
        on_error=_dec(grp.get("on_error", "REVIEW_REQUIRED"), "groups.on_error"),
        on_inconclusive=_dec(grp.get("on_inconclusive", "REVIEW_REQUIRED"), "groups.on_inconclusive"),
        max_skipped_in_mandatory=int(grp.get("max_skipped_in_mandatory", 0)),
        ai_min_pass_rate=float(ai["min_pass_rate"]) if "min_pass_rate" in ai else None,
        ai_below_threshold=_dec(ai.get("below_threshold", "BLOCK"), "ai_eval.below_threshold"),
        ai_inconclusive=_dec(ai.get("inconclusive", "REVIEW_REQUIRED"), "ai_eval.inconclusive"),
        untested_high_risk=_dec(cov.get("untested_high_risk", "REVIEW_REQUIRED"), "coverage.untested_high_risk"),
        max_untested_high_risk=int(cov.get("max_untested_high_risk", 0)),
        require_executions=_dec(ev.get("no_executions", "REVIEW_REQUIRED"), "evidence.no_executions"),
        integrity_violation=_dec(ev.get("integrity_violation", "REVIEW_REQUIRED"), "evidence.integrity_violation"),
        untriaged_failures=_dec(ev.get("untriaged_failures", "REVIEW_REQUIRED"), "evidence.untriaged_failures"),
        raw=data,
    )


@dataclass
class GateInputs:
    executions: list[m.TestExecution]
    findings: list[m.FindingView]
    plan: m.TestPlan | None = None
    risks: list[m.RiskAssessment] = field(default_factory=list)
    artifact_problems: list[str] = field(default_factory=list)

    def digest(self, policy: Policy) -> str:
        payload = {
            "policy": policy.sha256,
            "executions": sorted((to_dict(e) for e in self.executions), key=lambda d: d["id"]),
            "findings": sorted(({"f": to_dict(v.finding), "s": v.effective_status.value, "ok": v.evidence_valid} for v in self.findings), key=lambda d: d["f"]["id"]),
            "plan": to_dict(self.plan) if self.plan else None,
            "risks": sorted((to_dict(r) for r in self.risks), key=lambda d: d["id"]),
            "artifact_problems": sorted(self.artifact_problems),
        }
        blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(blob).hexdigest()


def _threshold(table: dict[str, SEV], category: m.Category) -> SEV | None:
    return table.get(category.value, table.get("default"))


def _ge(a: SEV, b: SEV | None) -> bool:
    return b is not None and m.SEVERITY_RANK[a] >= m.SEVERITY_RANK[b]


def _results_in_group(execs: list[m.TestExecution], group: str) -> tuple[list[m.TestExecution], list[m.TestResult]]:
    exs = [e for e in execs if group in e.groups or any(group in r.groups for r in e.results)]
    res = [r for e in exs for r in e.results if group in e.groups or group in r.groups]
    return exs, res


def _matches(ref: str, ident: str) -> bool:
    return ident == ref or ident.startswith(ref.rstrip("/") + "::") or ident.startswith(ref.rstrip("/") + "/") or ident.startswith(ref + "[")


def _latest_status(execs: list[m.TestExecution], ref: str) -> S | None:
    """Status of the most recent result matching ``ref`` (later executions supersede earlier ones)."""
    found = None
    for e in execs:  # executions are in recording order
        rel = [r for r in e.results if _matches(ref, r.identifier)]
        if rel:
            sts = {r.status for r in rel}
            for s in (S.FAILED, S.ERROR, S.INCONCLUSIVE, S.BLOCKED, S.NOT_RUN, S.SKIPPED, S.PASSED):
                if s in sts:
                    found = s
                    break
        elif e.status == S.BLOCKED and ref in " ".join(e.command):
            found = S.BLOCKED
    return found


def evaluate(policy: Policy, inp: GateInputs) -> m.ReleaseDecision:
    rules: list[m.RuleOutcome] = []

    def rule(rid: str, outcome: D, triggered: bool, reason: str, refs: list[str] | None = None):
        rules.append(m.RuleOutcome(rule_id=rid, outcome=outcome if triggered else D.PASS, triggered=triggered, reason=reason, refs=sorted(refs or [])))

    # Exclude reproduction attempts from group accounting: they re-run single tests on purpose.
    primary = [e for e in inp.executions if not e.reproduction_of]

    # R1: evidence exists at all
    rule("R-EVIDENCE-EXISTS", policy.require_executions, not primary, "no test executions recorded" if not primary else f"{len(primary)} execution(s) recorded")

    # R2: evidence integrity
    integrity = list(inp.artifact_problems) + [p for v in inp.findings for p in v.integrity_problems]
    rule("R-EVIDENCE-INTEGRITY", policy.integrity_violation, bool(integrity), "; ".join(sorted(set(integrity)))[:800] or "all evidence hashes verified")

    # R3/R4: confirmed findings by severity and category
    confirmed = [v for v in inp.findings if v.effective_status == FS.CONFIRMED]
    blocking = [v for v in confirmed if _ge(v.finding.severity, _threshold(policy.block_at, v.finding.category))]
    rule(
        "R-CONFIRMED-BLOCKING",
        D.BLOCK,
        bool(blocking),
        "; ".join(f"{v.finding.id} [{v.finding.severity.value} {v.finding.category.value}] {v.finding.title}" for v in blocking) or "no confirmed finding at a blocking severity",
        [v.finding.id for v in blocking],
    )
    review = [v for v in confirmed if v not in blocking and _ge(v.finding.severity, _threshold(policy.review_at, v.finding.category))]
    rule(
        "R-CONFIRMED-REVIEW",
        D.REVIEW_REQUIRED,
        bool(review),
        "; ".join(f"{v.finding.id} [{v.finding.severity.value}] {v.finding.title}" for v in review) or "no confirmed finding at review severity",
        [v.finding.id for v in review],
    )

    # R5: unverified high-impact findings
    open_states = {FS.SUSPECTED, FS.REPRODUCED, FS.NOT_REPRODUCED, FS.INCONCLUSIVE}
    unverified = [v for v in inp.findings if v.effective_status in open_states and _ge(v.finding.severity, policy.unverified_review_at)]
    rule(
        "R-UNVERIFIED-HIGH-IMPACT",
        D.REVIEW_REQUIRED,
        bool(unverified),
        "; ".join(f"{v.finding.id} [{v.finding.severity.value}, {v.effective_status.value}] {v.finding.title}" for v in unverified) or "no unverified high-impact findings",
        [v.finding.id for v in unverified],
    )

    # R6: mandatory groups
    positive_mandatory = False
    for g in policy.mandatory_groups:
        exs, res = _results_in_group(primary, g)
        rid = f"R-MANDATORY-GROUP:{g}"
        if not exs:
            rule(rid, policy.on_missing, True, f"mandatory group '{g}' was not executed")
            continue
        if any(e.status == S.BLOCKED for e in exs) and not res:
            rule(rid, policy.on_missing, True, f"mandatory group '{g}' is BLOCKED: " + "; ".join(e.status_reason or "" for e in exs if e.status == S.BLOCKED))
            continue
        failed = [r.identifier for r in res if r.status == S.FAILED]
        errored = [r.identifier for r in res if r.status == S.ERROR] + [e.id for e in exs if e.status == S.ERROR and not e.results]
        inconc = [r.identifier for r in res if r.status == S.INCONCLUSIVE] + [e.id for e in exs if e.status == S.INCONCLUSIVE and not e.results]
        skipped = [r.identifier for r in res if r.status in (S.SKIPPED, S.NOT_RUN, S.BLOCKED)]
        passed = [r for r in res if r.status == S.PASSED]
        if failed:
            rule(rid, policy.on_fail, True, f"{len(failed)} failing test(s) in mandatory group '{g}'", failed[:20])
        elif errored:
            rule(rid, policy.on_error, True, f"{len(errored)} errored test(s)/execution(s) in mandatory group '{g}'", errored[:20])
        elif inconc:
            rule(rid, policy.on_inconclusive, True, f"{len(inconc)} inconclusive result(s) in mandatory group '{g}'", inconc[:20])
        elif not passed:
            rule(rid, policy.on_missing, True, f"mandatory group '{g}' produced no passing result (nothing was verified)")
        elif len(skipped) > policy.max_skipped_in_mandatory:
            rule(rid, policy.on_missing, True, f"{len(skipped)} skipped/not-run test(s) in mandatory group '{g}' (allowed: {policy.max_skipped_in_mandatory}); skipped tests are not counted as passed", skipped[:20])
        else:
            positive_mandatory = True
            rule(rid, D.PASS, False, f"mandatory group '{g}': {len(passed)} passed, {len(skipped)} skipped (within allowance)")

    # R7: planned test cases in mandatory_if_planned groups must have executed and passed
    if inp.plan:
        planned = [tc for tc in inp.plan.test_cases if set(tc.groups) & set(policy.mandatory_if_planned)]
        missing, failed_tc, other = [], [], []
        for tc in planned:
            if not tc.test_ref:
                missing.append(f"{tc.id} (no executable test_ref)")
                continue
            st = _latest_status(primary, tc.test_ref)
            if st is None or st in (S.NOT_RUN, S.SKIPPED, S.BLOCKED):
                missing.append(f"{tc.id} ({st.value if st else 'not executed'})")
            elif st == S.FAILED:
                failed_tc.append(tc.id)
            elif st in (S.ERROR, S.INCONCLUSIVE):
                other.append(f"{tc.id} ({st.value})")
            else:
                positive_mandatory = True
        if failed_tc:
            rule("R-PLANNED-MANDATORY-CASES", policy.on_fail, True, f"planned mandatory test cases failed: {', '.join(failed_tc)}", failed_tc)
        elif missing or other:
            worst = policy.on_missing if missing else policy.on_error
            rule("R-PLANNED-MANDATORY-CASES", worst, True, "planned mandatory test cases without a passing result: " + ", ".join(missing + other))
        else:
            rule("R-PLANNED-MANDATORY-CASES", D.PASS, False, f"{len(planned)} planned mandatory test case(s) passed" if planned else "no planned test cases in mandatory groups")

    # R7b: every failure must be explained by a finding (product defect, test defect, or rejected claim)
    def triaged(ex: m.TestExecution, r: m.TestResult) -> bool:
        for v in inp.findings:
            f = v.finding
            if any(_matches(t, r.identifier) or _matches(r.identifier, t) for t in f.test_identifiers):
                return True
            if not f.test_identifiers and ex.id in f.execution_ids:
                return True
        return False

    untriaged = [
        r.identifier
        for e in primary
        if e.adapter not in CANDIDATE_ADAPTERS
        for r in e.results
        if r.status in (S.FAILED, S.ERROR) and not triaged(e, r)
    ]
    rule(
        "R-UNTRIAGED-FAILURES",
        policy.untriaged_failures,
        bool(untriaged),
        f"{len(untriaged)} failing/errored result(s) not explained by any finding (triage each as product defect, test defect or invalid)" if untriaged else "every failure is linked to a finding",
        sorted(set(untriaged))[:20],
    )

    # R8: flaky critical tests (inconclusive results or intermittent reproductions in critical groups)
    flaky = []
    for g in policy.critical_groups:
        _, res = _results_in_group(inp.executions, g)
        flaky += [r.identifier for r in res if r.status == S.INCONCLUSIVE]
    flaky += [v.finding.id for v in inp.findings if v.finding.reproduction and v.finding.reproduction.classification == "intermittent"]
    rule("R-FLAKY-CRITICAL", D.REVIEW_REQUIRED, bool(flaky), f"flaky/inconclusive critical results: {sorted(set(flaky))[:10]}" if flaky else "no flaky critical tests observed", flaky[:20])

    # R9: AI evaluation
    ai = [r for e in primary if e.adapter == "ai-eval" for r in e.results]
    if ai:
        decided = [r for r in ai if r.status in (S.PASSED, S.FAILED)]
        rate = (sum(1 for r in decided if r.status == S.PASSED) / len(decided)) if decided else None
        inconc = [r.identifier for r in ai if r.status in (S.INCONCLUSIVE, S.ERROR)]
        if policy.ai_min_pass_rate is not None and (rate is None or rate < policy.ai_min_pass_rate):
            rule("R-AI-EVAL-PASS-RATE", policy.ai_below_threshold, True, f"AI eval pass rate {rate if rate is None else round(rate, 3)} below {policy.ai_min_pass_rate} over {len(decided)} decided case(s)")
        else:
            rule("R-AI-EVAL-PASS-RATE", D.PASS, False, f"AI eval pass rate {round(rate, 3) if rate is not None else 'n/a'} over {len(decided)} decided case(s)")
        rule("R-AI-EVAL-INCONCLUSIVE", policy.ai_inconclusive, bool(inconc), f"{len(inconc)} inconclusive/errored AI eval case(s)" if inconc else "no inconclusive AI eval cases", inconc[:20])

    # R10: untested high-risk areas
    untested = []
    if inp.plan:
        for tc in inp.plan.test_cases:
            if m.SEVERITY_RANK[tc.priority] >= m.SEVERITY_RANK[SEV.HIGH]:
                st = _latest_status(primary, tc.test_ref) if tc.test_ref else None
                if st not in (S.PASSED, S.FAILED):
                    untested.append(f"test case {tc.id}")
    covered_risks = {rid for tc in (inp.plan.test_cases if inp.plan else []) for rid in tc.risk_ids}
    high_risks = [r for r in inp.risks if m.SEVERITY_RANK[r.level] >= m.SEVERITY_RANK[SEV.HIGH]]
    if high_risks and not inp.plan:
        untested.append(f"no test plan recorded, so {len(high_risks)} high/critical risk(s) cannot be traced to tests")
    for r in high_risks:
        if inp.plan and r.id not in covered_risks:
            untested.append(f"risk {r.id} ({r.area}) has no planned test")
    rule(
        "R-UNTESTED-HIGH-RISK",
        policy.untested_high_risk,
        len(untested) > policy.max_untested_high_risk,
        (f"{len(untested)} high-priority item(s) without an executed outcome: " + ", ".join(untested[:10])) if untested else "every high-priority planned item has an executed outcome",
    )

    triggered = [r for r in rules if r.triggered]
    decision = max((r.outcome for r in triggered), key=lambda d: m.DECISION_RANK[d], default=D.PASS)
    if decision == D.PASS and not positive_mandatory:
        rules.append(
            m.RuleOutcome(
                rule_id="R-POSITIVE-EVIDENCE",
                outcome=D.REVIEW_REQUIRED,
                triggered=True,
                reason="no mandatory check executed and passed; PASS requires positive evidence (configure [groups] mandatory)",
            )
        )
        decision = D.REVIEW_REQUIRED
    summary_bits = [r.rule_id for r in rules if r.triggered]
    summary = f"{decision.value}: " + (", ".join(summary_bits) if summary_bits else "all rules satisfied")
    return m.ReleaseDecision(
        decision=decision,
        policy=m.PolicyRef(name=policy.name, version=policy.version, sha256=policy.sha256, path=Path(policy.path).name),
        rules=rules,
        evaluated_at=now_iso(),
        inputs_digest=inp.digest(policy),
        summary=summary,
    )


EXIT_CODES = {D.PASS: 0, D.REVIEW_REQUIRED: 10, D.BLOCK: 20}
