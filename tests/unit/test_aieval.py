"""AI eval logic: deterministic checks, strict tool-arg matching, judge calibration gating."""

import pytest

from qa_superteam import aieval as ae


def test_strict_equality_distinguishes_cents_from_dollars():
    assert not ae.strict_equal(4999, 49.99)
    assert not ae.strict_equal(1, True)
    assert not ae.strict_equal(5, 5.0)
    assert ae.strict_equal({"a": [1, "x"]}, {"a": [1, "x"]})


def test_tool_call_modes():
    exp = [{"name": "lookup_order", "args": {"order_id": "A1"}}, {"name": "issue_refund", "args": {"amount_cents": 4999}}]
    actual = [{"name": "lookup_order", "args": {"order_id": "A1", "x": 1}}, {"name": "log", "args": {}},
              {"name": "issue_refund", "args": {"order_id": "A1", "amount_cents": 4999}}]
    assert ae.match_tool_calls(exp, actual, "ordered-subset")[0]
    assert not ae.match_tool_calls(exp, actual, "exact")[0]
    assert not ae.match_tool_calls(list(reversed(exp)), actual, "ordered-subset")[0]
    assert ae.match_tool_calls(list(reversed(exp)), actual, "subset")[0]
    wrong = [{"name": "lookup_order", "args": {"order_id": "A1"}}, {"name": "issue_refund", "args": {"amount_cents": 49.99}}]
    ok, detail = ae.match_tool_calls(exp, wrong, "ordered-subset")
    assert not ok and "49.99" in detail


def test_deterministic_checks():
    out = {"answer": "Refunds take 5 business days. CANARY-1", "citations": ["refunds.md"], "retrieved": ["refunds.md", "faq.md"],
           "tool_calls": [{"name": "issue_refund", "args": {}}]}
    expect = {"contains": ["5 business days"], "not_contains": ["canary-1"], "citations_include": ["refunds.md"],
              "retrieved_include": ["shipping.md"], "forbidden_tools": ["issue_refund"], "max_output_tokens": 3}
    checks, usage, estimated = ae.deterministic_checks(expect, out, 10.0)
    result = {c.name: c.passed for c in checks}
    assert result == {"contains:5 business days": True, "not_contains:canary-1": False, "citations_include": True,
                      "retrieved_include": False, "forbidden_tool:issue_refund": False, "max_output_tokens": False}
    assert estimated and usage["output_tokens"] == 6


def test_refusal_heuristic():
    assert ae.is_refusal("I’m sorry, I can't share that.")
    assert not ae.is_refusal("Refunds are processed in 5 days.")


@pytest.mark.parametrize(
    "judge,verdict,expected",
    [
        (ae.JudgeConfig(available=False, reason="no key"), None, None),
        (ae.JudgeConfig(available=True), {"verdict": "fail"}, "INCONCLUSIVE"),
        (ae.JudgeConfig(available=True, kappa=0.4, calibration_n=50), {"verdict": "fail"}, "INCONCLUSIVE"),
        (ae.JudgeConfig(available=True, kappa=0.9, calibration_n=4), {"verdict": "fail"}, "INCONCLUSIVE"),
        (ae.JudgeConfig(available=True, kappa=0.9, calibration_n=50, model_matches=False), {"verdict": "fail"}, "INCONCLUSIVE"),
        (ae.JudgeConfig(available=True, kappa=0.8, calibration_n=50), {"verdict": "uncertain"}, "INCONCLUSIVE"),
        (ae.JudgeConfig(available=True, kappa=0.8, calibration_n=50), {"verdict": "fail"}, "FAILED"),
        (ae.JudgeConfig(available=True, kappa=0.8, calibration_n=50), {"verdict": "pass"}, "PASSED"),
    ],
)
def test_judge_is_never_trusted_without_calibration(judge, verdict, expected):
    override, check, info = ae.apply_judge(verdict, judge)
    assert override == expected
    if not judge.available:
        assert check.passed is None and info["status"] == "NOT_RUN"


def test_case_status_combinations():
    det_fail = [ae.CheckResult("contains:x", False, "missing")]
    assert ae.case_status(det_fail, None)[0] == "FAILED"
    assert ae.case_status([ae.CheckResult("contains:x", True)], "INCONCLUSIVE")[0] == "INCONCLUSIVE"
    assert ae.case_status([ae.CheckResult("judge", None, "not run")], None)[0] == "NOT_RUN"
    assert ae.case_status([ae.CheckResult("contains:x", True)], None)[0] == "PASSED"


def test_samples_disagreement_is_inconclusive():
    assert ae.combine_samples(["PASSED", "FAILED", "PASSED"])[0] == "INCONCLUSIVE"
    assert ae.combine_samples(["FAILED"] * 3)[0] == "FAILED"
    assert ae.combine_samples(["PASSED", "ERROR"])[0] == "ERROR"


def test_cohen_kappa_known_values():
    assert ae.cohen_kappa(["pass", "fail"] * 5, ["pass", "fail"] * 5) == pytest.approx(1.0)
    # 8 items, 6 agreements, both raters 4 pass / 4 fail -> po=.75, pe=.5, kappa=.5
    a = ["pass"] * 4 + ["fail"] * 4
    b = ["pass", "pass", "pass", "fail", "fail", "fail", "fail", "pass"]
    assert ae.cohen_kappa(a, b) == pytest.approx(0.5)
    assert ae.cohen_kappa([], []) is None


def test_calibrate_reports_disagreements():
    res = ae.calibrate({"a": "pass", "b": "fail", "c": "pass"}, {"a": "pass", "b": "pass", "c": "pass", "d": "fail"})
    assert res["n"] == 3 and res["disagreements"] == ["b"] and res["agreement"] == pytest.approx(2 / 3)


def test_dataset_validation():
    good = '{"id": "a", "input": "hi", "expect": {"contains": ["x"]}}\n'
    assert len(ae.parse_dataset(good)) == 1
    with pytest.raises(ae.DatasetError, match="unsupported expect keys"):
        ae.parse_dataset('{"id": "a", "input": "hi", "expect": {"contain": ["x"]}}')
    with pytest.raises(ae.DatasetError, match="no oracle"):
        ae.parse_dataset('{"id": "a", "input": "hi", "expect": {}}')
    with pytest.raises(ae.DatasetError, match="duplicate"):
        ae.parse_dataset(good + good)


def test_summary_marks_estimated_tokens():
    o = ae.CaseOutcome(case_id="a", status="PASSED", latency_ms=5.0, usage={"output_tokens": 4}, usage_estimated=True, tags=["rag"])
    s = ae.summarize([o, ae.CaseOutcome(case_id="b", status="FAILED", latency_ms=7.0, tags=["rag"])])
    assert s["pass_rate_over_decided"] == 0.5 and s["output_tokens_estimated"] and s["by_tag"]["rag"] == {"PASSED": 1, "FAILED": 1}
