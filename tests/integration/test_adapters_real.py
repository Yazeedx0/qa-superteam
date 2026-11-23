"""Adapters against real tools and the real reference fixtures. No mocks.

Each test skips (with the reason) when its tool is unavailable; a skip here is
reported by pytest as SKIPPED, never as a pass.
"""

from __future__ import annotations

import http.server
import json
import os
import shutil
import threading
from pathlib import Path

import pytest
from conftest import ROOT, copy_fixture

pytestmark = pytest.mark.integration
NODE_PROJECT = Path(__file__).parent / "node_project"


def has_module(mod: str) -> bool:
    import importlib.util

    return importlib.util.find_spec(mod) is not None


def chromium_env() -> dict:
    """Point Playwright at an installed Chromium when the pinned build is absent."""
    if os.environ.get("CHROMIUM_EXECUTABLE"):
        return {}
    import glob

    cands = sorted(glob.glob(os.path.expanduser("~/.cache/ms-playwright/chromium-*/chrome-*/chrome")), reverse=True)
    return {"CHROMIUM_EXECUTABLE": cands[0]} if cands else {}


@pytest.fixture
def run_in(tmp_path, monkeypatch, qast):
    def start(project: Path, mode="adhoc"):
        code, _ = qast("run", "start", "--mode", mode, "--scope", "integration", cwd=project)
        assert code == 0

        def call(*args):
            return qast(*args, cwd=project)

        return call

    return start


def last_execution(project: Path) -> dict:
    run = sorted((project / ".qa-superteam" / "runs").iterdir())[-1]
    files = sorted((run / "executions").glob("*.json"), key=lambda p: p.stat().st_mtime)
    return json.loads(files[-1].read_text())


# ----------------------------------------------------------------------------- pytest


def test_pytest_existing_suite_on_backend_fixture(tmp_path, run_in):
    proj = copy_fixture("backend-api", tmp_path)
    q = run_in(proj)
    code, out = q("exec", "pytest", "--group", "existing-suite", "--", "tests")
    ex = last_execution(proj)
    assert ex["status"] == "PASSED", out
    assert ex["counts"]["PASSED"] >= 10 and ex["counts"]["SKIPPED"] == 1
    assert all("::" in r["identifier"] for r in ex["results"])
    assert not (proj / ".pytest_cache").exists(), "audit must not write .pytest_cache into the project"
    assert not list(proj.rglob("__pycache__")), "audit must not write bytecode caches into the project"


def test_pytest_detects_planted_backend_defects(tmp_path, run_in):
    proj = copy_fixture("backend-api", tmp_path)
    shutil.copytree(ROOT / "evals/ground_truth/backend-api/reference_tests", proj / "tests" / "qa")
    q = run_in(proj)
    q("exec", "pytest", "--group", "critical-journeys", "--", "tests/qa")
    ex = last_execution(proj)
    failed = sorted(r["identifier"] for r in ex["results"] if r["status"] == "FAILED")
    assert ex["status"] == "FAILED" and len(failed) == 6, failed
    assert any("test_qa_authz" in f for f in failed) and any("test_qa_invariants" in f for f in failed)


def test_pytest_error_vs_failure_and_timeout(tmp_path, run_in):
    proj = tmp_path / "p"
    (proj / "tests").mkdir(parents=True)
    (proj / "tests" / "test_x.py").write_text(
        "import pytest, time\n"
        "@pytest.fixture\ndef broken():\n    raise RuntimeError('db not reachable')\n"
        "def test_setup_error(broken):\n    pass\n"
        "def test_assertion():\n    assert 1 == 2\n"
    )
    (proj / "tests" / "test_slow.py").write_text("import time\ndef test_slow():\n    time.sleep(30)\n")
    q = run_in(proj)
    q("exec", "pytest", "--", "tests/test_x.py")
    st = {r["identifier"].split("::")[-1]: r["status"] for r in last_execution(proj)["results"]}
    assert st == {"test_setup_error": "ERROR", "test_assertion": "FAILED"}
    q("exec", "pytest", "--timeout", "3", "--", "tests/test_slow.py")
    ex = last_execution(proj)
    assert ex["status"] == "ERROR" and ex["timed_out"] and "timed out" in ex["status_reason"]


def test_pytest_missing_in_interpreter_is_blocked(tmp_path, run_in):
    venv = tmp_path / "bare"
    import subprocess
    import sys

    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(venv)], check=True)
    proj = tmp_path / "p"
    (proj / "tests").mkdir(parents=True)
    (proj / "tests" / "test_a.py").write_text("def test_a():\n    assert True\n")
    q = run_in(proj)
    q("exec", "pytest", "--python", str(venv / "bin" / "python"), "--", "tests")
    ex = last_execution(proj)
    assert ex["status"] == "BLOCKED" and "not installed" in ex["status_reason"]


def test_junit_adapter_with_real_report(tmp_path, run_in):
    import sys

    proj = tmp_path / "p"
    (proj / "tests").mkdir(parents=True)
    (proj / "tests" / "test_a.py").write_text("def test_ok():\n    pass\n\ndef test_bad():\n    assert 0\n")
    q = run_in(proj)
    q("exec", "junit", "--report", "out/junit.xml", "--", sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "tests", "--junitxml", "out/junit.xml")
    ex = last_execution(proj)
    assert ex["counts"]["PASSED"] == 1 and ex["counts"]["FAILED"] == 1 and ex["status"] == "FAILED"


# ----------------------------------------------------------------------------- ai-eval


def test_ai_eval_golden_and_reference_datasets(tmp_path, run_in):
    proj = copy_fixture("ai-support-bot", tmp_path)
    shutil.copy(ROOT / "evals/ground_truth/ai-support-bot/reference_evals.jsonl", proj / "evals" / "qa_cases.jsonl")
    q = run_in(proj)
    q("exec", "ai-eval", "--group", "ai-eval", "--dataset", "evals/golden.jsonl", "--entry", "support_bot.bot:answer")
    golden = last_execution(proj)
    st = {r["identifier"]: r["status"] for r in golden["results"]}
    assert "FAILED" not in st.values(), st
    assert "NOT_RUN" in st.values() or "PASSED" in st.values()  # judge-only checks stay NOT_RUN without credentials
    q("exec", "ai-eval", "--group", "ai-eval", "--dataset", "evals/qa_cases.jsonl", "--entry", "support_bot.bot:answer", "--samples", "2")
    ref = last_execution(proj)
    failed = sorted(r["name"] for r in ref["results"] if r["status"] == "FAILED")
    gt = json.loads((ROOT / "evals/ground_truth/ai-support-bot/ground_truth.json").read_text())
    expected = sorted(c for d in gt["defects"] for c in d.get("reference_eval_cases", []))
    assert failed == expected, (failed, expected)
    tool_case = next(r for r in ref["results"] if "refund-tool" in r["name"])
    assert "49.99" in tool_case["message"]


# ----------------------------------------------------------------------------- axe (Playwright)


@pytest.mark.skipif(not has_module("playwright"), reason="python playwright not installed")
def test_axe_scan_of_running_web_fixture(tmp_path, run_in, monkeypatch):
    for k, v in chromium_env().items():
        monkeypatch.setenv(k, v)
    proj = copy_fixture("web-checkout", tmp_path)
    if not (proj / "node_modules" / "axe-core" / "axe.min.js").exists():
        pytest.skip("axe-core not installed in examples/web-checkout (npm install)")
    import importlib.util

    spec = importlib.util.spec_from_file_location("serve_fixture", proj / "serve.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    server, base = mod.make_server(port=0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        q = run_in(proj)
        q("exec", "axe", "--group", "accessibility", "--target", base + "/", "--viewport", "375x812")
        ex = last_execution(proj)
    finally:
        server.shutdown()
    assert ex["status"] in ("PASSED", "FAILED", "INCONCLUSIVE"), ex["status_reason"]
    assert any(r["status"] == "PASSED" for r in ex["results"])
    kinds = []
    run = sorted((proj / ".qa-superteam/runs").iterdir())[-1]
    for a in ex["artifact_ids"]:
        kinds.append(json.loads((run / "evidence" / f"{a}.json").read_text())["kind"])
    assert "screenshot" in kinds and "report" in kinds


def test_axe_blocked_without_axe_core(tmp_path, run_in):
    proj = tmp_path / "p"
    proj.mkdir()
    q = run_in(proj)
    q("exec", "axe", "--target", "http://127.0.0.1:9/")
    ex = last_execution(proj)
    assert ex["status"] == "BLOCKED" and "axe-core not found" in ex["status_reason"]


# ----------------------------------------------------------------------------- k6


@pytest.mark.skipif(shutil.which("k6") is None, reason="k6 not installed")
def test_k6_smoke_against_local_server(tmp_path, run_in):
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), http.server.SimpleHTTPRequestHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    proj = tmp_path / "p"
    proj.mkdir()
    (proj / "smoke.js").write_text(
        "import http from 'k6/http';\nimport { check } from 'k6';\n"
        "export const options = { thresholds: { http_req_failed: ['rate<0.01'], http_req_duration: ['p(95)<2000'] } };\n"
        "export default function () { const r = http.get(`${__ENV.TARGET}/`); check(r, { 'status 200': (x) => x.status === 200 }); }\n"
    )
    try:
        q = run_in(proj)
        q("exec", "k6", "--group", "performance", "--target", f"http://127.0.0.1:{srv.server_address[1]}", "--", "smoke.js")
        ex = last_execution(proj)
    finally:
        srv.shutdown()
    st = {r["identifier"]: r["status"] for r in ex["results"]}
    assert st["check:status 200"] == "PASSED" and st["threshold:http_req_failed:rate<0.01"] == "PASSED", st
    assert ex["status"] == "PASSED" and "smoke" in ex["status_reason"]


# ----------------------------------------------------------------------------- node runners


needs_node = pytest.mark.skipif(not (NODE_PROJECT / "node_modules" / ".bin" / "vitest").exists(), reason="run `npm ci` in tests/integration/node_project")


@needs_node
@pytest.mark.parametrize(
    "adapter,args,expected",
    [
        ("vitest", ["tests/math"], {"PASSED": 1, "FAILED": 1, "SKIPPED": 1}),
        ("jest", ["--rootDir", "jtests", "--testMatch", "**/*.test.cjs"], {"PASSED": 1, "FAILED": 1, "SKIPPED": 1}),
        ("playwright", [], {"PASSED": 1, "FAILED": 1}),
    ],
)
def test_node_runners(tmp_path, run_in, monkeypatch, adapter, args, expected):
    for k, v in chromium_env().items():
        monkeypatch.setenv(k, v)
    proj = tmp_path / "np"
    shutil.copytree(NODE_PROJECT, proj, ignore=shutil.ignore_patterns("node_modules"))
    (proj / "node_modules").symlink_to(NODE_PROJECT / "node_modules")
    q = run_in(proj)
    q("exec", adapter, "--", *args)
    ex = last_execution(proj)
    got = {k: v for k, v in ex["counts"].items() if v}
    assert got == expected, (ex["status_reason"], got)
    if adapter == "playwright":
        assert not (proj / "test-results").exists()
