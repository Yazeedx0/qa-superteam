"""Findings: evidence integrity, reproduction classification, derived status, verification gates.

A finding's status is never edited in place.  It is derived from the records that
support it (executions, reproduction attempts, verification results), so a report
can always show *why* a finding has the status it has.

Verification gates enforced by ``qast verify`` (and re-checked by the policy engine):

* CONFIRMED requires a verifier different from the reporter (independence),
* at least one execution with a FAILED result for the finding's tests (code
  inspection alone never confirms a defect),
* intact evidence (artifact files exist and their sha256 matches), and
* no intermittent reproduction (flaky evidence cannot confirm).
"""

from __future__ import annotations

from dataclasses import dataclass

from . import models as m
from .store import RunStore

FS, S = m.FindingStatus, m.Status


@dataclass
class EvidenceIndex:
    executions: dict[str, m.TestExecution]
    artifacts: dict[str, m.EvidenceArtifact]
    artifact_problems: dict[str, str]

    @classmethod
    def build(cls, store: RunStore) -> "EvidenceIndex":
        arts = {a.id: a for a in store.artifacts()}
        problems = {}
        for a in arts.values():
            p = store.verify_artifact(a)
            if p:
                problems[a.id] = p
        return cls({e.id: e for e in store.executions()}, arts, problems)


def evidence_problems(f_evidence: list[str], f_execs: list[str], idx: EvidenceIndex) -> list[str]:
    out = []
    for eid in f_evidence:
        if eid not in idx.artifacts:
            out.append(f"evidence {eid} is not recorded in this run")
        elif eid in idx.artifact_problems:
            out.append(idx.artifact_problems[eid])
    for xid in f_execs:
        if xid not in idx.executions:
            out.append(f"execution {xid} is not recorded in this run")
    return out


def failing_results(f: m.DefectFinding, execs: list[m.TestExecution]) -> list[tuple[str, m.TestResult]]:
    """FAILED results that support the finding (matching its test identifiers when it has any)."""
    hits = []
    for ex in execs:
        for r in ex.results:
            if r.status != S.FAILED:
                continue
            if not f.test_identifiers or any(_id_match(t, r.identifier) for t in f.test_identifiers):
                hits.append((ex.id, r))
    return hits


def _id_match(wanted: str, actual: str) -> bool:
    return actual == wanted or actual.startswith(wanted + "::") or actual.startswith(wanted + "[")


def reproduction_for(f: m.DefectFinding, idx: EvidenceIndex) -> m.Reproduction | None:
    """Classify dedicated reproduction executions (``qast reproduce``) for the finding's tests."""
    if not f.test_identifiers:
        return f.reproduction
    attempts = [
        ex for ex in idx.executions.values() if ex.reproduction_of and any(_id_match(t, ex.reproduction_of) or _id_match(ex.reproduction_of, t) for t in f.test_identifiers)
    ]
    if not attempts:
        return f.reproduction
    return classify_attempts(attempts, f.test_identifiers)


def classify_attempts(attempts: list[m.TestExecution], identifiers: list[str]) -> m.Reproduction:
    outcomes = []
    for ex in attempts:
        rel = [r for r in ex.results if any(_id_match(t, r.identifier) for t in identifiers)]
        if ex.status == S.BLOCKED or not rel:
            outcomes.append("blocked" if ex.status == S.BLOCKED else "no-result")
        elif any(r.status == S.FAILED for r in rel):
            outcomes.append("fail")
        elif all(r.status == S.PASSED for r in rel):
            outcomes.append("pass")
        else:
            outcomes.append("other")
    fails = outcomes.count("fail")
    passes = outcomes.count("pass")
    if fails and not passes and fails == len(outcomes):
        cls = "consistent"
    elif fails and passes:
        cls = "intermittent"
    elif passes and not fails:
        cls = "not-reproduced"
    else:
        cls = "blocked"
    return m.Reproduction(attempts=len(attempts), failures=fails, execution_ids=[a.id for a in attempts], classification=cls)


def effective_status(f: m.DefectFinding, verifs: list[m.VerificationResult], idx: EvidenceIndex) -> tuple[FS, str, list[str]]:
    """Return (status, basis, integrity_problems)."""
    problems = evidence_problems(f.evidence_ids, f.execution_ids, idx)
    mine = [v for v in verifs if v.finding_id == f.id]
    if mine:
        v = mine[-1]
        vprob = evidence_problems(v.evidence_ids, v.execution_ids, idx)
        problems += vprob
        if v.verdict == m.Verdict.CONFIRMED:
            if problems:
                return FS.INCONCLUSIVE, f"verification {v.id} said CONFIRMED but evidence integrity failed", problems
            return FS.CONFIRMED, f"independently verified by {v.verifier} ({v.method}) in {v.id}", problems
        if v.verdict == m.Verdict.REJECTED:
            return FS.REJECTED, f"rejected by {v.verifier} in {v.id}: {v.rationale[:160]}", problems
        return FS.INCONCLUSIVE, f"verification {v.id} was inconclusive: {v.rationale[:160]}", problems
    rep = reproduction_for(f, idx)
    if rep:
        mapping = {"consistent": FS.REPRODUCED, "intermittent": FS.INCONCLUSIVE, "not-reproduced": FS.NOT_REPRODUCED, "blocked": FS.SUSPECTED}
        return mapping.get(rep.classification, FS.SUSPECTED), f"reproduction {rep.failures}/{rep.attempts} failing ({rep.classification}); not yet independently verified", problems
    execs = [idx.executions[x] for x in f.execution_ids if x in idx.executions]
    if failing_results(f, execs):
        return FS.REPRODUCED, "a linked execution shows the failure once; reproduce and verify before treating as confirmed", problems
    return FS.SUSPECTED, "no failing execution linked yet", problems


def finding_views(store: RunStore, idx: EvidenceIndex | None = None) -> list[m.FindingView]:
    idx = idx or EvidenceIndex.build(store)
    verifs = store.verifications()
    out = []
    for f in store.findings():
        st, basis, problems = effective_status(f, verifs, idx)
        out.append(m.FindingView(finding=f, effective_status=st, status_basis=basis, evidence_valid=not problems, integrity_problems=problems))
    return out


def verification_checks(
    f: m.DefectFinding,
    verdict: m.Verdict,
    verifier: str,
    method: str,
    execution_ids: list[str],
    evidence_ids: list[str],
    idx: EvidenceIndex,
    verifier_tests: list[str] | None = None,
) -> list[m.VerificationCheck]:
    """Machine checks for a proposed verdict. All must pass for the verdict to be recorded.

    For CONFIRMED the failure must show up in an execution the *verifier* ran
    (independent rerun of the same test, or an alternate oracle test of their own).
    """
    checks: list[m.VerificationCheck] = []
    probs = evidence_problems(f.evidence_ids + evidence_ids, f.execution_ids + execution_ids, idx)
    checks.append(m.VerificationCheck("evidence integrity", not probs, "; ".join(probs) or "all referenced evidence exists with matching sha256"))
    if verdict != m.Verdict.CONFIRMED:
        return checks
    checks.append(m.VerificationCheck("independent verifier", verifier.strip().lower() != f.reported_by.strip().lower(), f"reporter={f.reported_by} verifier={verifier}"))
    checks.append(m.VerificationCheck("execution-based method", method in ("independent-rerun", "alternate-oracle"), f"method={method}; code inspection or manual review alone cannot confirm a defect"))
    own = [idx.executions[x] for x in execution_ids if x in idx.executions and x not in f.execution_ids]
    checks.append(m.VerificationCheck("verifier ran own execution", bool(own), f"verifier executions: {[e.id for e in own] or 'none'}"))
    probe = m.DefectFinding(**{**f.__dict__, "test_identifiers": list(f.test_identifiers) + list(verifier_tests or [])})
    hits = failing_results(probe, own)
    checks.append(m.VerificationCheck("failing evidence", bool(hits), f"{len(hits)} FAILED result(s) in the verifier's own executions" if hits else "no FAILED result for the finding's (or verifier's) tests in the verifier's own executions"))
    rep = reproduction_for(f, idx)
    if rep is not None:
        checks.append(m.VerificationCheck("reproduction stable", rep.classification == "consistent", f"{rep.failures}/{rep.attempts} attempts failed ({rep.classification})"))
    return checks
