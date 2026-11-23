"""Write-once records, content-addressed evidence, derived finding status, verification gates."""

import pytest

from qa_superteam import models as m
from qa_superteam.findings import EvidenceIndex, classify_attempts, effective_status, finding_views, verification_checks
from qa_superteam.store import RunStore, StoreError

S, FS = m.Status, m.FindingStatus
ENV = m.EnvironmentInfo(platform="t", python="3", hostname_hash="h")


def execution(store, ident, status, repro=None, eid=None, actor=None, started="2026-01-01T00:00:00Z"):
    eid = eid or store.execution_id("pytest", ident + str(store.next_sequence("executions")))
    e = m.TestExecution(
        id=eid, run_id=store.run_id, adapter="pytest", status=status, started_at=started, finished_at=started, duration_s=0.1, actor=actor,
        command=["pytest", ident], cwd=".", exit_code=0 if status == S.PASSED else 1, timed_out=False,
        counts={status.value: 1}, results=[m.TestResult(id="tr-" + eid, identifier=ident, status=status)],
        environment=ENV, reproduction_of=repro,
    )
    store.save_execution(e)
    return e


def add_finding(store, ex_ids, ev_ids, tests=("tests/t.py::test_x",), reporter="backend-qa-engineer", sev="high"):
    f = m.DefectFinding(
        id=store.finding_id("bug", [], list(tests)), title="bug", category=m.Category.SECURITY, severity=m.Severity(sev),
        summary="s", expected="403", actual="200", reproduction_steps=["call"], reported_by=reporter, created_at="2026-01-01T00:00:00Z",
        execution_ids=list(ex_ids), evidence_ids=list(ev_ids), test_identifiers=list(tests),
    )
    store.save_finding(f)
    return f


def test_records_are_write_once(store):
    e = execution(store, "tests/t.py::test_x", S.PASSED)
    with pytest.raises(StoreError, match="write-once"):
        store.save_execution(e)


def test_artifacts_are_content_addressed_redacted_and_hashed(store):
    a = store.add_artifact("out.log", b"password=supersecret123 ok", m.ArtifactKind.LOG)
    b = store.add_artifact("again.log", b"password=supersecret123 ok", m.ArtifactKind.LOG)
    assert a.id == b.id and a.redacted and a.redactions == 1
    assert b"supersecret123" not in (store.dir / a.path).read_bytes()
    assert store.verify_artifact(a) is None


def test_tampered_artifact_is_detected(store):
    a = store.add_artifact("out.log", b"hello", m.ArtifactKind.LOG)
    (store.dir / a.path).write_text("changed")
    assert "sha256 mismatch" in store.verify_artifact(a)


def test_binary_artifacts_are_not_rewritten(store):
    png = b"\x89PNG\r\n\x1a\npassword=abc12345"
    a = store.add_artifact("shot.png", png, m.ArtifactKind.SCREENSHOT)
    assert (store.dir / a.path).read_bytes() == png and not a.redacted


def test_artifact_budget_enforced(store):
    store.config.budgets.max_artifact_bytes = 10
    with pytest.raises(StoreError, match="over budget"):
        store.add_artifact("big.bin", b"x" * 11, m.ArtifactKind.OTHER)


def test_singletons_supersede_keeps_history(store):
    reg = m.RiskRegister(risks=[])
    store.save_singleton("risks", reg)
    with pytest.raises(StoreError, match="--supersede"):
        store.save_singleton("risks", reg)
    store.save_singleton("risks", reg, supersede=True)
    assert (store.dir / "history" / "risks.v1.json").exists()


def test_resolve_prefers_active_run(project):
    from qa_superteam.config import load_config

    cfg = load_config(project)
    a = RunStore.create(cfg, "adhoc", "a")
    b = RunStore.create(cfg, "adhoc", "b", activate=False)
    assert RunStore.resolve(cfg).run_id == a.run_id
    assert RunStore.resolve(cfg, b.run_id).run_id == b.run_id
    a.deactivate()
    assert RunStore.resolve(cfg).run_id in (a.run_id, b.run_id)


def test_status_suspected_without_failing_evidence(store):
    f = add_finding(store, [], [])
    st, _, _ = effective_status(f, [], EvidenceIndex.build(store))
    assert st == FS.SUSPECTED


def test_status_reproduced_from_linked_failure(store):
    e = execution(store, "tests/t.py::test_x", S.FAILED)
    f = add_finding(store, [e.id], [])
    assert effective_status(f, [], EvidenceIndex.build(store))[0] == FS.REPRODUCED


def test_reproduction_classification():
    def att(st):
        return m.TestExecution(id="e" + st.value, run_id="r", adapter="pytest", status=st, started_at="t", finished_at="t", duration_s=0,
                               command=[], cwd=".", exit_code=0, timed_out=False, counts={}, environment=ENV,
                               results=[m.TestResult(id="x", identifier="t::a", status=st)])

    assert classify_attempts([att(S.FAILED)] * 3, ["t::a"]).classification == "consistent"
    assert classify_attempts([att(S.FAILED), att(S.PASSED)], ["t::a"]).classification == "intermittent"
    assert classify_attempts([att(S.PASSED)] * 2, ["t::a"]).classification == "not-reproduced"


def test_intermittent_reproduction_makes_finding_inconclusive(store):
    e = execution(store, "tests/t.py::test_x", S.FAILED)
    f = add_finding(store, [e.id], [])
    execution(store, "tests/t.py::test_x", S.FAILED, repro="tests/t.py::test_x")
    execution(store, "tests/t.py::test_x", S.PASSED, repro="tests/t.py::test_x")
    assert effective_status(f, [], EvidenceIndex.build(store))[0] == FS.INCONCLUSIVE


def _gate(store, f, verifier, method, ex_ids, verifier_tests=(), verdict=m.Verdict.CONFIRMED):
    checks = verification_checks(f, verdict, verifier, method, ex_ids, [], EvidenceIndex.build(store), list(verifier_tests), store.verifications())
    return {c.check: c.passed for c in checks}


def test_reporter_cannot_confirm_own_finding(store):
    e = execution(store, "tests/t.py::test_x", S.FAILED)
    f = add_finding(store, [e.id], [])
    own = execution(store, "tests/t.py::test_x", S.FAILED, actor="backend-qa-engineer")
    assert _gate(store, f, "backend-qa-engineer", "independent-rerun", [own.id])["independent verifier"] is False


def test_code_inspection_cannot_confirm(store):
    e = execution(store, "tests/t.py::test_x", S.FAILED)
    f = add_finding(store, [e.id], [])
    own = execution(store, "tests/t.py::test_x", S.FAILED, actor="verifier")
    assert _gate(store, f, "verifier", "code-inspection", [own.id])["execution-based method"] is False


def test_confirm_needs_verifier_owned_failing_execution(store):
    e = execution(store, "tests/t.py::test_x", S.FAILED)
    f = add_finding(store, [e.id], [])
    assert _gate(store, f, "verifier", "independent-rerun", [e.id])["verifier ran own execution"] is False
    passing = execution(store, "tests/t.py::test_x", S.PASSED, actor="verifier")
    assert _gate(store, f, "verifier", "independent-rerun", [passing.id])["failing evidence"] is False
    borrowed = execution(store, "tests/t.py::test_x", S.FAILED, actor="backend-qa-engineer")  # reporter's rerun under a borrowed name
    assert _gate(store, f, "verifier", "independent-rerun", [borrowed.id])["verifier ran own execution"] is False
    early = execution(store, "tests/t.py::test_x", S.FAILED, actor="verifier", started="2025-12-31T23:59:00Z")  # before the finding existed
    assert _gate(store, f, "verifier", "independent-rerun", [early.id])["verifier ran own execution"] is False
    failing = execution(store, "tests/t.py::test_x", S.FAILED, actor="verifier")
    assert all(_gate(store, f, "verifier", "independent-rerun", [failing.id]).values())


def test_alternate_oracle_uses_verifier_tests(store):
    e = execution(store, "tests/t.py::test_x", S.FAILED)
    f = add_finding(store, [e.id], [])
    alt = execution(store, "tests/qa/test_alt.py::test_property", S.FAILED, actor="verifier")
    assert _gate(store, f, "verifier", "alternate-oracle", [alt.id])["failing evidence"] is False
    assert all(_gate(store, f, "verifier", "alternate-oracle", [alt.id], ["tests/qa/test_alt.py::test_property"]).values())


def test_missing_evidence_fails_integrity_gate(store):
    f = add_finding(store, ["ex-doesnotexist"], ["ev-missing"])
    checks = verification_checks(f, m.Verdict.INCONCLUSIVE, "v", "manual", [], [], EvidenceIndex.build(store))
    assert checks[0].check == "evidence integrity" and not checks[0].passed


def test_confirmed_with_tampered_evidence_degrades_to_inconclusive(store):
    e = execution(store, "tests/t.py::test_x", S.FAILED)
    art = store.add_artifact("log.txt", b"boom", m.ArtifactKind.LOG)
    f = add_finding(store, [e.id], [art.id])
    v = m.VerificationResult(id="V-1", finding_id=f.id, verdict=m.Verdict.CONFIRMED, method="independent-rerun", verifier="v",
                             rationale="r", created_at="t", execution_ids=[e.id])
    store.save_verification(v)
    assert finding_views(store)[0].effective_status == FS.CONFIRMED
    (store.dir / art.path).write_text("edited")
    view = finding_views(store)[0]
    assert view.effective_status == FS.INCONCLUSIVE and view.integrity_problems


def test_finding_without_tests_needs_verifier_test(store):
    e = execution(store, "tests/t.py::test_x", S.FAILED)
    f = add_finding(store, [e.id], [], tests=())
    own = execution(store, "tests/t.py::test_x", S.FAILED, actor="verifier")
    g = _gate(store, f, "verifier", "independent-rerun", [own.id])
    assert g["tests identified"] is False and g["failing evidence"] is False


def test_reporter_cannot_reject_or_downgrade_own_finding(store):
    e = execution(store, "tests/t.py::test_x", S.FAILED)
    f = add_finding(store, [e.id], [])
    for verdict in (m.Verdict.REJECTED, m.Verdict.INCONCLUSIVE):
        assert _gate(store, f, "backend-qa-engineer", "manual", [], verdict=verdict)["independent verifier"] is False


def _confirm(store, f):
    own = execution(store, "tests/t.py::test_x", S.FAILED, actor="verifier")
    store.save_verification(m.VerificationResult(id="V-1", finding_id=f.id, verdict=m.Verdict.CONFIRMED, method="independent-rerun",
                                                 verifier="verifier", rationale="r", created_at="t", execution_ids=[own.id]))


def test_overturning_confirmed_needs_passing_execution(store):
    e = execution(store, "tests/t.py::test_x", S.FAILED)
    f = add_finding(store, [e.id], [])
    _confirm(store, f)
    g = _gate(store, f, "second-verifier", "manual", [], verdict=m.Verdict.REJECTED)
    assert g["overturning CONFIRMED needs executed evidence"] is False
    ok = execution(store, "tests/t.py::test_x", S.PASSED, actor="second-verifier")
    assert all(_gate(store, f, "second-verifier", "independent-rerun", [ok.id], verdict=m.Verdict.REJECTED).values())


def test_conflicting_verdicts_need_human_review(store):
    e = execution(store, "tests/t.py::test_x", S.FAILED)
    f = add_finding(store, [e.id], [])
    _confirm(store, f)
    store.save_verification(m.VerificationResult(id="V-2", finding_id=f.id, verdict=m.Verdict.REJECTED, method="independent-rerun",
                                                 verifier="other", rationale="passes now", created_at="t"))
    view = finding_views(store)[0]
    assert view.effective_status == FS.INCONCLUSIVE and "conflicting" in view.status_basis
