"""CLI behaviour and report generation from records only."""

import json

from qa_superteam.cli import build_parser


def test_every_documented_command_exists():
    from pathlib import Path

    doc = (Path(__file__).resolve().parents[2] / "docs" / "cli.md").read_text()
    parser = build_parser()
    cmds = set(parser._subparsers._group_actions[0].choices)
    import re

    for cmd in set(re.findall(r"`qast ([a-z-]+)", doc)):
        assert cmd in cmds, cmd


def test_run_lifecycle(qast, project):
    code, out = qast("run", "start", "--mode", "full-audit", "--scope", "demo")
    assert code == 0 and "run started" in out
    assert (project / ".qa-superteam" / "active-run").exists()
    assert (project / ".qa-superteam" / ".gitignore").read_text().count("runs/") == 1
    assert qast("run", "phase", "discovery", "done", "--note", "ok")[0] == 0
    code, out = qast("run", "status", "--json")
    assert json.loads(out)["phases"]["discovery"] == "done"
    assert qast("run", "note", "no staging environment", "--kind", "limitation")[0] == 0
    assert qast("run", "finish")[0] == 0
    assert not (project / ".qa-superteam" / "active-run").exists()


def test_record_validation_errors_are_explained(qast, project, tmp_path):
    qast("run", "start", "--mode", "adhoc", "--scope", "x")
    bad = tmp_path / "plan.json"
    bad.write_text(json.dumps({"scope": "s", "strategy_summary": "x", "test_cases": [{"id": "TC1", "title": "t", "level": "api", "technique": "b", "oracle": ""}]}))
    code, out = qast("record", "plan", "--file", str(bad))
    assert code == 1 and "no oracle" in out


def test_finding_with_missing_evidence_is_refused(qast, project, tmp_path):
    from qa_superteam.templates import TEMPLATES

    qast("run", "start", "--mode", "adhoc", "--scope", "x")
    f = tmp_path / "f.json"
    f.write_text(json.dumps(TEMPLATES["DefectFinding"]))
    code, out = qast("finding", "add", "--file", str(f))
    assert code == 3 and "refused" in out


def test_blocked_execution_for_missing_tool(qast, project):
    qast("run", "start", "--mode", "adhoc", "--scope", "x")
    code, out = qast("exec", "command", "--label", "lint", "--", "definitely-not-a-real-tool-xyz", "--check")
    assert code == 0 and "BLOCKED" in out and "tool not available" in out


def test_k6_blocked_for_unauthorized_target(qast, project):
    qast("run", "start", "--mode", "adhoc", "--scope", "x")
    (project / "s.js").write_text("import http from 'k6/http'; export default () => http.get(__ENV.TARGET);")
    code, out = qast("exec", "k6", "--target", "https://api.example-prod.com", "--", "s.js")
    assert "BLOCKED" in out and "authorized_targets" in out
    code, out = qast("exec", "k6", "--target", "http://127.0.0.1:9", "--profile", "load", "--", "s.js")
    assert "BLOCKED" in out and "allow_load_testing" in out


def test_k6_script_with_hardcoded_url_is_blocked(qast, project):
    qast("run", "start", "--mode", "adhoc", "--scope", "x")
    (project / "s.js").write_text("import http from 'k6/http'; export default () => http.get('https://prod.example.com/');")
    _, out = qast("exec", "k6", "--target", "http://127.0.0.1:9", "--", "s.js")
    assert "BLOCKED" in out and "hard-coded URL" in out


def test_gate_and_report_with_no_evidence(qast, project):
    qast("run", "start", "--mode", "release-check", "--scope", "x")
    code, out = qast("gate", "--exit-code")
    assert code == 10 and "REVIEW_REQUIRED" in out
    code, out = qast("report", "--print")
    assert "Release decision: **REVIEW_REQUIRED**" in out
    assert "No coverage percentage reported" in out
    assert qast("validate")[0] == 0


def test_report_flags_stale_decision(qast, project):
    qast("run", "start", "--mode", "adhoc", "--scope", "x")
    qast("gate")
    qast("exec", "command", "--label", "true", "--", "true")
    _, out = qast("report", "--print")
    assert "decision.json is stale" in out


def test_schema_and_template(qast):
    code, out = qast("schema", "DefectFinding")
    assert code == 0 and json.loads(out)["title"] == "DefectFinding"
    code, out = qast("schema", "TestPlan", "--template")
    assert "test_cases" in json.loads(out)


def test_redact_command(qast, project, capsys):
    f = project / "log.txt"
    f.write_text("password=hunter2hunter2\n")
    code, out = qast("redact", str(f))
    assert code == 0 and "hunter2hunter2" not in out


def test_ai_eval_calibrate(qast, project):
    j = project / "j.jsonl"
    h = project / "h.jsonl"
    j.write_text("\n".join(json.dumps({"id": str(i), "label": lab}) for i, lab in enumerate(["pass", "fail", "pass", "fail"])))
    h.write_text("\n".join(json.dumps({"id": str(i), "label": lab}) for i, lab in enumerate(["pass", "fail", "pass", "pass"])))
    code, out = qast("ai-eval", "calibrate", "--judgments", str(j), "--labels", str(h), "--judge-model", "m1", "--out", str(project / "cal.json"))
    cal = json.loads((project / "cal.json").read_text())
    assert code == 0 and cal["n"] == 4 and cal["judge_model"] == "m1" and "will NOT make the judge trusted" in out


def test_cli_launcher_runs_isolated():
    import subprocess
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    out = subprocess.run([str(root / "bin" / "qast"), "--version"], capture_output=True, text=True, env={"PATH": "/usr/bin:/bin", "PYTHONPATH": "/nonexistent"})
    assert out.returncode == 0 and out.stdout.startswith("qast ")


def test_reproduce_with_command_adapter_classifies(qast, project):
    qast("run", "start", "--mode", "adhoc", "--scope", "x")
    code, out = qast("reproduce", "--adapter", "command", "--test", "smoke-check", "--times", "2", "--", "false")
    assert code == 0 and "2/2 attempts failed -> consistent" in out


def test_command_adapter_missing_python_module_is_blocked(qast, project):
    import sys

    qast("run", "start", "--mode", "adhoc", "--scope", "x")
    _, out = qast("exec", "command", "--label", "coverage", "--", sys.executable, "-m", "definitely_missing_module_xyz")
    assert "BLOCKED" in out and "not installed" in out


def test_coverage_json_artifact_becomes_measured_metric(store):
    import json as _json

    from qa_superteam import models as m
    from qa_superteam.report import measured_metrics

    cov = {"meta": {"version": "7.6.1", "branch_coverage": True}, "totals": {"percent_covered": 88.57142857142857, "num_statements": 35}}
    a = store.add_artifact("coverage.json", _json.dumps(cov).encode(), m.ArtifactKind.COVERAGE)
    (metric,) = measured_metrics(store, [a])
    assert metric.value == 88.57 and metric.metric == "statement+branch coverage" and metric.artifact_id == a.id


def test_run_lifecycle_refuses_writes_to_finished_runs(qast, project):
    code, out = qast("run", "start", "--mode", "adhoc", "--scope", "a")
    rid = out.split()[2]
    code, out = qast("run", "start", "--mode", "adhoc", "--scope", "b")
    assert code == 1 and "still active" in out
    qast("run", "finish")
    code, _ = qast("exec", "command", "--", "true")
    assert code == 1  # no active run: evidence is never written into a finished run
    _, out = qast("run", "status")
    assert "finished" in out  # read-only commands still work
    assert qast("run", "resume", rid)[0] == 0
    code, out = qast("exec", "command", "--", "true")
    assert code == 0 and "PASSED" in out


def test_identifiers_are_normalized_to_project_relative(qast, project):
    qast("run", "start", "--mode", "adhoc", "--scope", "x")
    _, out = qast("reproduce", "--adapter", "command", "--test", f"{project}/probe-x", "--times", "2", "--", "false")
    assert "reproduction of probe-x: 2/2 attempts failed -> consistent" in out


def test_config_change_during_run_is_an_integrity_problem(qast, project):
    qast("run", "start", "--mode", "adhoc", "--scope", "x")
    qast("exec", "command", "--", "true")
    (project / ".qa-superteam" / "config.toml").write_text("[permissions]\nmodify_app_code = true\n")
    _, out = qast("gate")
    assert "R-EVIDENCE-INTEGRITY" in out and "config.toml changed" in out
