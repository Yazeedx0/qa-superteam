"""End-to-end pipelines on the reference fixtures: real executions -> findings -> verification -> gate -> report."""

import json
import subprocess
import sys

import jsonschema
import pytest
from conftest import ROOT

from qa_superteam.models import QAReport
from qa_superteam.serde import json_schema

pytestmark = pytest.mark.integration


def run_demo(name, tmp_path):
    out = subprocess.run([sys.executable, str(ROOT / "scripts" / "demo_pipeline.py"), "--scenario", name, "--out", str(tmp_path)],
                         capture_output=True, text=True, timeout=900)
    assert out.returncode == 0, out.stdout[-3000:] + out.stderr[-3000:]
    d = tmp_path / name
    report = json.loads((d / "report.json").read_text())
    jsonschema.validate(report, json_schema(QAReport))
    return d, report


def statuses(report):
    return {v["finding"]["title"]: v["effective_status"] for v in report["findings"]}


def test_full_audit_backend_blocks_on_verified_defects(tmp_path):
    d, rep = run_demo("backend-full-audit", tmp_path)
    assert rep["decision"]["decision"] == "BLOCK"
    st = statuses(rep)
    assert sum(1 for s in st.values() if s == "CONFIRMED") == 2  # BOLA + negative balance, independently verified
    assert "REPRODUCED" in st.values()  # medium email finding reproduced but not escalated to verification
    triggered = {r["rule_id"] for r in rep["decision"]["rules"] if r["triggered"]}
    assert "R-CONFIRMED-BLOCKING" in triggered
    md = (d / "report.md").read_text()
    assert "Release decision: **BLOCK**" in md and "REQ-LARGE" in md and "No coverage percentage reported" in md


def test_pr_review_detects_regression_from_real_git_diff(tmp_path):
    d, rep = run_demo("backend-pr-review", tmp_path)
    impact = json.loads((d / "impact.json").read_text())
    assert [f["path"] for f in impact["files"]] == ["ledger/transfers.py"]
    assert rep["run"]["base_ref"] == "main"
    assert rep["decision"]["decision"] == "BLOCK"
    assert list(statuses(rep).values()) == ["CONFIRMED"]
