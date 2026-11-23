"""Result normalization from real tool output (tests/data captured from actual runs)."""

from pathlib import Path

from conftest import load_json

from qa_superteam import models as m
from qa_superteam.adapters.base import derive_status, result_id
from qa_superteam.adapters.nonfunctional import parse_axe_result, parse_k6_summary
from qa_superteam.adapters.testrunners import parse_jest_json, parse_junit_xml, parse_playwright_json

S = m.Status


def statuses(results):
    return {r.identifier: r.status for r in results}


def test_vitest_real_report():
    res = parse_jest_json(load_json("vitest-report.json"), "vitest", ["g"], Path("/project"))
    st = statuses(res)
    assert st == {"tests/math.test.js::math adds": S.PASSED, "tests/math.test.js::math fails on purpose": S.FAILED,
                  "tests/math.test.js::math skipped one": S.SKIPPED}
    failed = next(r for r in res if r.status == S.FAILED)
    assert "expected 4 to be 5" in failed.message and failed.groups == ["g"]


def test_jest_real_report():
    st = statuses(parse_jest_json(load_json("jest-report.json"), "jest", [], Path("/project")))
    assert st == {"jtests/a.test.cjs::jest ok": S.PASSED, "jtests/a.test.cjs::jest bad": S.FAILED, "jtests/a.test.cjs::jest todo": S.SKIPPED}


def test_playwright_real_report():
    res, _ = parse_playwright_json(load_json("playwright-report.json"), [], Path("/project"))
    st = statuses(res)
    assert st == {"e2e/page.spec.js::static page > has title": S.PASSED, "e2e/page.spec.js::static page > wrong heading": S.FAILED}


def test_playwright_flaky_is_inconclusive_not_passed():
    data = {"suites": [{"title": "a.spec.ts", "file": "a.spec.ts", "specs": [{"title": "t", "file": "a.spec.ts", "line": 3, "tests": [
        {"projectName": "chromium", "status": "flaky", "results": [{"status": "failed", "duration": 10}, {"status": "passed", "duration": 9}]}]}]}]}
    (r,), _ = parse_playwright_json(data, [])
    assert r.status == S.INCONCLUSIVE and "flaky" in r.message and r.identifier == "a.spec.ts::t [chromium]"


def test_k6_real_summary_threshold_semantics():
    st = statuses(parse_k6_summary(load_json("k6-summary.json"), []))
    # captured run: checks rate 0.5 crossed 'rate>0.99'; latency and error-rate thresholds held
    assert st["threshold:checks:rate>0.99"] == S.FAILED
    assert st["threshold:http_req_duration:p(95)<500"] == S.PASSED
    assert st["threshold:http_req_failed:rate<0.01"] == S.PASSED
    assert st["check:never true"] == S.FAILED and st["check:status is 200"] == S.PASSED


def test_junit_mapping():
    xml = b"""<testsuites><testsuite name="s">
      <testcase classname="tests.test_a" name="ok" time="0.1"/>
      <testcase classname="tests.test_a" name="bad"><failure message="assert 1 == 2">trace</failure></testcase>
      <testcase classname="tests.test_a" name="crash"><error message="fixture boom"/></testcase>
      <testcase classname="tests.test_a" name="skip"><skipped message="later"/></testcase>
    </testsuite></testsuites>"""
    st = statuses(parse_junit_xml(xml, "junit", []))
    assert st == {"tests.test_a::ok": S.PASSED, "tests.test_a::bad": S.FAILED, "tests.test_a::crash": S.ERROR, "tests.test_a::skip": S.SKIPPED}


def test_axe_mapping_incomplete_needs_manual_review():
    data = {"pages": [{"url": "http://127.0.0.1/", "violations": [{"id": "label", "impact": "critical", "help": "Form elements must have labels", "nodes": [{"target": ["#promo"]}]}],
                       "incomplete": [{"id": "color-contrast", "help": "contrast"}], "passes": ["html-has-lang"]},
                      {"url": "http://127.0.0.1/x", "error": "navigation failed"}]}
    st = statuses(parse_axe_result(data, []))
    assert st["http://127.0.0.1/::label"] == S.FAILED
    assert st["http://127.0.0.1/::color-contrast"] == S.INCONCLUSIVE
    assert st["http://127.0.0.1/::html-has-lang"] == S.PASSED
    assert st["http://127.0.0.1/x::navigation"] == S.ERROR


def test_result_ids_are_deterministic():
    assert result_id("pytest", "t::a") == result_id("pytest", "t::a") != result_id("pytest", "t::b")


def r(st):
    return m.TestResult(id="x", identifier="i", status=st)


def test_derive_status_is_conservative():
    assert derive_status([r(S.PASSED)], 0, False) == (S.PASSED, None)
    assert derive_status([r(S.PASSED)], 1, False)[0] == S.INCONCLUSIVE  # exit code disagrees with results
    assert derive_status([], 0, False, parse_ok=False)[0] == S.INCONCLUSIVE  # success but no evidence
    assert derive_status([], 2, False, parse_ok=False)[0] == S.ERROR
    assert derive_status([r(S.PASSED)], None, True, timeout_s=5)[0] == S.ERROR  # timeout never passes
    assert derive_status([], 5, False)[0] == S.NOT_RUN
    assert derive_status([r(S.SKIPPED)], 0, False)[0] == S.SKIPPED
    assert derive_status([r(S.PASSED), r(S.FAILED)], 1, False)[0] == S.FAILED
    assert derive_status([r(S.PASSED), r(S.ERROR)], 1, False)[0] == S.ERROR
    assert derive_status([r(S.PASSED), r(S.INCONCLUSIVE)], 0, False)[0] == S.INCONCLUSIVE
