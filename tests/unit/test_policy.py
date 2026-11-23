"""Release gate: deterministic, policy-driven, never treats missing evidence as a pass."""

from pathlib import Path

import pytest

from qa_superteam import models as m
from qa_superteam.config import PLUGIN_ROOT
from qa_superteam.policy import GateInputs, PolicyError, evaluate, load_policy

S, D, FS = m.Status, m.Decision, m.FindingStatus
ENV = m.EnvironmentInfo(platform="test", python="3.12", hostname_hash="x")


@pytest.fixture
def default():
    return load_policy(PLUGIN_ROOT / "policies" / "default.toml")


@pytest.fixture
def strict():
    return load_policy(PLUGIN_ROOT / "policies" / "strict.toml")


def ex(eid, groups, *results, status=None, adapter="pytest", repro=None, reason=None):
    res = [m.TestResult(id=f"tr-{eid}-{i}", identifier=ident, status=st, groups=list(groups)) for i, (ident, st) in enumerate(results)]
    if status is None:
        sts = {r.status for r in res}
        status = S.FAILED if S.FAILED in sts else S.PASSED if res else S.NOT_RUN
    counts = {s.value: sum(1 for r in res if r.status == s) for s in S}
    return m.TestExecution(id=eid, run_id="r", adapter=adapter, status=status, started_at="t", finished_at="t", duration_s=1.0,
                           command=["x"], cwd=".", exit_code=0, timed_out=False, counts=counts, results=res, environment=ENV,
                           groups=list(groups), reproduction_of=repro, status_reason=reason)


def finding(fid, sev, cat, status, problems=()):
    f = m.DefectFinding(id=fid, title=f"finding {fid}", category=m.Category(cat), severity=m.Severity(sev), summary="s",
                        expected="e", actual="a", reproduction_steps=["1"], reported_by="agent", created_at="t")
    return m.FindingView(finding=f, effective_status=status, status_basis="test", evidence_valid=not problems, integrity_problems=list(problems))


def triggered(dec):
    return {r.rule_id: r.outcome for r in dec.rules if r.triggered}


GREEN = ex("e1", ["existing-suite"], ("tests/test_a.py::test_1", S.PASSED), ("tests/test_a.py::test_2", S.PASSED))


def test_clean_evidence_passes(default):
    dec = evaluate(default, GateInputs(executions=[GREEN], findings=[]))
    assert dec.decision == D.PASS, triggered(dec)


def test_no_executions_is_never_pass(default):
    dec = evaluate(default, GateInputs(executions=[], findings=[]))
    assert dec.decision == D.REVIEW_REQUIRED
    assert "R-EVIDENCE-EXISTS" in triggered(dec)


def test_decision_is_deterministic_and_digest_stable(default):
    inp = GateInputs(executions=[GREEN], findings=[finding("F1", "medium", "functional", FS.CONFIRMED)])
    a, b = evaluate(default, inp), evaluate(default, inp)
    assert (a.decision, a.inputs_digest, [r.reason for r in a.rules]) == (b.decision, b.inputs_digest, [r.reason for r in b.rules])


def test_digest_changes_when_evidence_changes(default):
    a = evaluate(default, GateInputs(executions=[GREEN], findings=[]))
    other = ex("e1", ["existing-suite"], ("tests/test_a.py::test_1", S.PASSED), ("tests/test_a.py::test_2", S.FAILED))
    b = evaluate(default, GateInputs(executions=[other], findings=[]))
    assert a.inputs_digest != b.inputs_digest


@pytest.mark.parametrize(
    "sev,cat,expected",
    [
        ("critical", "functional", D.BLOCK),
        ("high", "security", D.BLOCK),
        ("high", "data-integrity", D.BLOCK),
        ("high", "functional", D.REVIEW_REQUIRED),
        ("medium", "security", D.PASS),
        ("low", "functional", D.PASS),
    ],
)
def test_confirmed_findings_by_severity_and_category(default, sev, cat, expected):
    dec = evaluate(default, GateInputs(executions=[GREEN], findings=[finding("F1", sev, cat, FS.CONFIRMED)]))
    assert dec.decision == expected, triggered(dec)


@pytest.mark.parametrize("status", [FS.SUSPECTED, FS.REPRODUCED, FS.NOT_REPRODUCED, FS.INCONCLUSIVE])
def test_unverified_high_impact_findings_require_review_not_block(default, status):
    dec = evaluate(default, GateInputs(executions=[GREEN], findings=[finding("F1", "critical", "security", status)]))
    assert dec.decision == D.REVIEW_REQUIRED
    assert "R-UNVERIFIED-HIGH-IMPACT" in triggered(dec)


def test_rejected_findings_do_not_affect_decision(default):
    dec = evaluate(default, GateInputs(executions=[GREEN], findings=[finding("F1", "critical", "security", FS.REJECTED)]))
    assert dec.decision == D.PASS


def test_failing_mandatory_group_blocks(default):
    red = ex("e1", ["existing-suite"], ("t::a", S.PASSED), ("t::b", S.FAILED))
    dec = evaluate(default, GateInputs(executions=[red], findings=[]))
    assert dec.decision == D.BLOCK and "R-MANDATORY-GROUP:existing-suite" in triggered(dec)


def test_missing_mandatory_group_requires_review(default):
    other = ex("e1", ["exploratory"], ("t::a", S.PASSED))
    dec = evaluate(default, GateInputs(executions=[other], findings=[]))
    assert triggered(dec).get("R-MANDATORY-GROUP:existing-suite") == D.REVIEW_REQUIRED


def test_blocked_mandatory_group_is_not_a_pass(default):
    blocked = ex("e1", ["existing-suite"], status=S.BLOCKED, reason="pytest not installed")
    dec = evaluate(default, GateInputs(executions=[blocked], findings=[]))
    assert dec.decision == D.REVIEW_REQUIRED
    assert "BLOCKED" in next(r.reason for r in dec.rules if r.rule_id == "R-MANDATORY-GROUP:existing-suite")


def test_all_skipped_mandatory_group_is_not_a_pass(default):
    skipped = ex("e1", ["existing-suite"], ("t::a", S.SKIPPED), status=S.SKIPPED)
    dec = evaluate(default, GateInputs(executions=[skipped], findings=[]))
    assert dec.decision != D.PASS


def test_skipped_tests_in_mandatory_group_need_review_unless_allowed(default, tmp_path):
    one_skip = ex("e1", ["existing-suite"], ("t::a", S.PASSED), ("t::b", S.SKIPPED))
    assert evaluate(default, GateInputs(executions=[one_skip], findings=[])).decision == D.REVIEW_REQUIRED
    custom = (PLUGIN_ROOT / "policies" / "default.toml").read_text().replace("max_skipped_in_mandatory = 0", "max_skipped_in_mandatory = 1")
    p = tmp_path / "p.toml"
    p.write_text(custom)
    assert evaluate(load_policy(p), GateInputs(executions=[one_skip], findings=[])).decision == D.PASS


def test_errored_mandatory_tests_require_review(default):
    err = ex("e1", ["existing-suite"], ("t::a", S.PASSED), ("t::b", S.ERROR), status=S.ERROR)
    assert triggered(evaluate(default, GateInputs(executions=[err], findings=[])))["R-MANDATORY-GROUP:existing-suite"] == D.REVIEW_REQUIRED


def test_reproduction_attempts_do_not_count_as_group_runs(default):
    repro = ex("e2", ["existing-suite"], ("t::b", S.FAILED), repro="t::b")
    dec = evaluate(default, GateInputs(executions=[GREEN, repro], findings=[]))
    assert dec.decision == D.PASS


def plan(*cases):
    return m.TestPlan(id="TP", scope="s", strategy_summary="x", test_cases=list(cases))


def tc(i, ref, groups, prio="medium", risks=()):
    return m.TestCase(id=i, title=i, level="api", technique="boundary", oracle="o", test_ref=ref, groups=groups,
                      priority=m.Severity(prio), risk_ids=list(risks))


def test_planned_mandatory_case_not_executed_requires_review(default):
    p = plan(tc("TC1", "tests/qa/test_j.py::test_checkout", ["critical-journeys"]))
    dec = evaluate(default, GateInputs(executions=[GREEN], findings=[], plan=p))
    assert triggered(dec)["R-PLANNED-MANDATORY-CASES"] == D.REVIEW_REQUIRED


def test_planned_mandatory_case_failing_blocks(default):
    p = plan(tc("TC1", "tests/qa/test_j.py::test_checkout", ["critical-journeys"]))
    run = ex("e2", ["critical-journeys"], ("tests/qa/test_j.py::test_checkout", S.FAILED))
    assert evaluate(default, GateInputs(executions=[GREEN, run], findings=[], plan=p)).decision == D.BLOCK


def test_planned_case_file_ref_matches_node_ids(default):
    p = plan(tc("TC1", "tests/qa/test_j.py", ["critical-journeys"]))
    run = ex("e2", ["critical-journeys"], ("tests/qa/test_j.py::test_a", S.PASSED), ("tests/qa/test_j.py::test_b", S.PASSED))
    assert evaluate(default, GateInputs(executions=[GREEN, run], findings=[], plan=p)).decision == D.PASS


def test_later_rerun_supersedes_earlier_result_for_planned_case(default):
    p = plan(tc("TC1", "t::x", ["regression"]))
    first = ex("e2", ["regression"], ("t::x", S.FAILED))
    second = ex("e3", ["regression"], ("t::x", S.PASSED))
    assert "R-PLANNED-MANDATORY-CASES" not in triggered(evaluate(default, GateInputs(executions=[GREEN, first, second], findings=[], plan=p)))


def test_flaky_critical_test_requires_review(default):
    flaky = ex("e2", ["critical-journeys"], ("e2e::checkout", S.INCONCLUSIVE), status=S.INCONCLUSIVE)
    dec = evaluate(default, GateInputs(executions=[GREEN, flaky], findings=[]))
    assert "R-FLAKY-CRITICAL" in triggered(dec) and dec.decision == D.REVIEW_REQUIRED


def test_ai_eval_pass_rate_and_inconclusive(default):
    cases = [(f"golden::c{i}", S.PASSED) for i in range(9)] + [("golden::c9", S.FAILED)]
    ok = ex("e2", ["ai-eval"], *cases, adapter="ai-eval")
    assert "R-AI-EVAL-PASS-RATE" not in triggered(evaluate(default, GateInputs(executions=[GREEN, ok], findings=[])))
    low = ex("e3", ["ai-eval"], ("g::a", S.PASSED), ("g::b", S.FAILED), adapter="ai-eval")
    assert triggered(evaluate(default, GateInputs(executions=[GREEN, low], findings=[])))["R-AI-EVAL-PASS-RATE"] == D.BLOCK
    unsure = ex("e4", ["ai-eval"], *cases, ("g::judge", S.INCONCLUSIVE), adapter="ai-eval")
    assert triggered(evaluate(default, GateInputs(executions=[GREEN, unsure], findings=[])))["R-AI-EVAL-INCONCLUSIVE"] == D.REVIEW_REQUIRED


def test_high_risk_without_plan_or_tests_requires_review(default):
    risk = m.RiskAssessment(id="R-01", area="payments", description="d", probability=4, impact=5, score=20, level=m.Severity.CRITICAL)
    assert "R-UNTESTED-HIGH-RISK" in triggered(evaluate(default, GateInputs(executions=[GREEN], findings=[], risks=[risk])))
    p = plan(tc("TC1", "tests/test_a.py::test_1", ["existing-suite"], prio="critical", risks=["R-01"]))
    assert "R-UNTESTED-HIGH-RISK" not in triggered(evaluate(default, GateInputs(executions=[GREEN], findings=[], plan=p, risks=[risk])))


def test_evidence_integrity_problems_require_review(default):
    dec = evaluate(default, GateInputs(executions=[GREEN], findings=[], artifact_problems=["ev-1: sha256 mismatch"]))
    assert triggered(dec)["R-EVIDENCE-INTEGRITY"] == D.REVIEW_REQUIRED


def test_pass_requires_positive_mandatory_evidence(tmp_path):
    p = tmp_path / "nomand.toml"
    p.write_text("[policy]\nname='x'\n[groups]\nmandatory=[]\n")
    dec = evaluate(load_policy(p), GateInputs(executions=[ex("e", ["other"], ("t::a", S.PASSED))], findings=[]))
    assert dec.decision == D.REVIEW_REQUIRED and "R-POSITIVE-EVIDENCE" in triggered(dec)


def test_strict_policy_blocks_on_uncertainty(strict):
    blocked = ex("e1", ["existing-suite"], status=S.BLOCKED, reason="no env")
    assert evaluate(strict, GateInputs(executions=[blocked], findings=[])).decision == D.BLOCK
    dec = evaluate(strict, GateInputs(executions=[GREEN], findings=[finding("F", "medium", "security", FS.CONFIRMED)]))
    assert dec.decision == D.BLOCK


@pytest.mark.parametrize(
    "body,msg",
    [
        ("[findings]\nblock_at={default='urgent'}", "unknown severity"),
        ("[findings]\nblock_at={payments='high'}", "unknown finding category"),
        ("[groups]\non_fail='MAYBE'", "unknown decision"),
        ("[weird]\nx=1", "unknown section"),
    ],
)
def test_invalid_policies_are_rejected(tmp_path, body, msg):
    p = tmp_path / "bad.toml"
    p.write_text(body)
    with pytest.raises(PolicyError, match=msg):
        load_policy(p)


def test_shipped_policies_load():
    for p in (PLUGIN_ROOT / "policies").glob("*.toml"):
        load_policy(Path(p))


def test_untriaged_failures_require_review(default):
    red = ex("e2", ["exploratory"], ("tests/qa/test_x.py::test_a", S.FAILED))
    dec = evaluate(default, GateInputs(executions=[GREEN, red], findings=[]))
    assert triggered(dec)["R-UNTRIAGED-FAILURES"] == D.REVIEW_REQUIRED
    f = finding("F1", "low", "functional", FS.REPRODUCED)
    f.finding.test_identifiers = ["tests/qa/test_x.py::test_a"]
    assert "R-UNTRIAGED-FAILURES" not in triggered(evaluate(default, GateInputs(executions=[GREEN, red], findings=[f])))


def test_scanner_candidates_are_not_untriaged_failures(default):
    scan = ex("e2", ["security"], ("bandit:B105:app.py:3", S.FAILED), adapter="bandit")
    assert "R-UNTRIAGED-FAILURES" not in triggered(evaluate(default, GateInputs(executions=[GREEN, scan], findings=[])))
