"""The guard hook only acts during an active QA run and only ever asks (never allows)."""

import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HOOK = ROOT / "hooks" / "qa-guard"


def run_hook(project: Path, phase: str, tool: str, tool_input: dict) -> dict | None:
    event = {"tool_name": tool, "tool_input": tool_input, "cwd": str(project)}
    out = subprocess.run([str(HOOK), phase], input=json.dumps(event), capture_output=True, text=True,
                         env={"CLAUDE_PROJECT_DIR": str(project), "PATH": "/usr/bin:/bin:/usr/local/bin"}, timeout=20)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout) if out.stdout.strip() else None


@pytest.fixture
def active(project, qast):
    code, _ = qast("run", "start", "--mode", "adhoc", "--scope", "guard")
    assert code == 0
    return project


def decision(res):
    return res and res["hookSpecificOutput"]["permissionDecision"]


def test_inactive_outside_qa_runs(project):
    assert run_hook(project, "pre", "Bash", {"command": "git push --force"}) is None


@pytest.mark.parametrize(
    "cmd",
    [
        "git push origin main",
        "git reset --hard HEAD~3",
        "psql -c 'DROP TABLE users'",
        "kubectl delete deployment api",
        "terraform apply -auto-approve",
        "npm publish",
        "cat .env",
        "k6 run --vus 500 script.js https://api.prod.example.com",
        "rm -rf /",
    ],
)
def test_risky_commands_force_a_permission_prompt(active, cmd):
    res = run_hook(active, "pre", "Bash", {"command": cmd})
    assert decision(res) == "ask"
    assert "QA Superteam guard" in res["hookSpecificOutput"]["permissionDecisionReason"]


@pytest.mark.parametrize("cmd", ["qast exec pytest -- tests", "pytest -q", "git status", "git diff main...HEAD", "ls -la"])
def test_ordinary_qa_commands_pass_through(active, cmd):
    assert run_hook(active, "pre", "Bash", {"command": cmd}) is None


def test_never_returns_allow(active):
    for cmd in ["ls", "git push", "qast gate"]:
        res = run_hook(active, "pre", "Bash", {"command": cmd})
        assert res is None or decision(res) != "allow"


def test_app_code_edits_need_permission_by_default(active):
    (active / "app.py").write_text("x = 1\n")
    assert decision(run_hook(active, "pre", "Edit", {"file_path": str(active / "app.py")})) == "ask"


def test_test_writes_respect_config(active):
    assert decision(run_hook(active, "pre", "Write", {"file_path": str(active / "tests/qa/test_new.py")})) == "ask"
    (active / ".qa-superteam" / "config.toml").write_text('[permissions]\nwrite_tests = true\ntest_dir = "tests/qa"\n')
    assert run_hook(active, "pre", "Write", {"file_path": str(active / "tests/qa/test_new.py")}) is None
    assert decision(run_hook(active, "pre", "Write", {"file_path": str(active / "tests/other/test_x.py")})) == "ask"
    (active / "tests" / "qa").mkdir(parents=True)
    (active / "tests/qa/test_old.py").write_text("def test(): assert True\n")
    res = run_hook(active, "pre", "Edit", {"file_path": str(active / "tests/qa/test_old.py")})
    assert decision(res) == "ask" and "EXISTING test" in res["hookSpecificOutput"]["permissionDecisionReason"]


def test_golden_baselines_are_protected(active):
    (active / ".qa-superteam" / "config.toml").write_text("[permissions]\nwrite_tests = true\nmodify_app_code = true\n")
    res = run_hook(active, "pre", "Write", {"file_path": str(active / "tests/__snapshots__/home.snap")})
    assert decision(res) == "ask" and "baseline" in res["hookSpecificOutput"]["permissionDecisionReason"]


def test_recorded_evidence_cannot_be_edited_directly(active):
    run_dir = next((active / ".qa-superteam" / "runs").iterdir())
    res = run_hook(active, "pre", "Edit", {"file_path": str(run_dir / "executions" / "ex-1.json")})
    assert decision(res) == "ask" and "write-once" in res["hookSpecificOutput"]["permissionDecisionReason"]
    assert run_hook(active, "pre", "Write", {"file_path": str(active / ".qa-superteam" / "plan-draft.json")}) is None


def test_post_hook_journals_commands_redacted(active):
    run_hook(active, "post", "Bash", {"command": "curl -H 'Authorization: Bearer abcdefghijklmnopqrstu' http://127.0.0.1"})
    run_dir = next((active / ".qa-superteam" / "runs").iterdir())
    journal = (run_dir / "journal.jsonl").read_text()
    assert "tool.bash" in journal and "abcdefghijklmnopqrstu" not in journal


def test_stale_marker_is_ignored(active):
    import os

    marker = active / ".qa-superteam" / "active-run"
    old = marker.stat().st_mtime - 13 * 3600
    os.utime(marker, (old, old))
    assert run_hook(active, "pre", "Bash", {"command": "git push"}) is None


@pytest.mark.parametrize(
    "tool,inp",
    [
        ("Write", {"file_path": ".qa-superteam/config.toml"}),
        ("Edit", {"file_path": ".qa-superteam/active-run"}),
        ("Write", {"file_path": "policies/lenient.toml"}),
        ("Bash", {"command": "sed -i 's/False/True/' .qa-superteam/config.toml"}),
        ("Bash", {"command": "sed -i 's/>= amount/> amount/' ledger/transfers.py"}),
        ("Bash", {"command": "perl -pi -e 's/a/b/' app.py"}),
        ("Bash", {"command": "echo 'x = 1' > app.py"}),
        ("Bash", {"command": "cat patch.txt | tee src/main.py"}),
    ],
)
def test_permission_and_shell_write_bypasses_are_caught(active, tool, inp):
    if "file_path" in inp:
        inp = {"file_path": str(active / inp["file_path"])}
    assert decision(run_hook(active, "pre", tool, inp)) == "ask"


@pytest.mark.parametrize(
    "cmd",
    [
        "qast exec pytest -- tests > /tmp/out.txt",
        "python3 -m pytest 2>&1 | tail -5",
        "cat > .qa-superteam/runs/x/drafts/plan.json <<'EOF'",
        "echo done >/dev/null",
    ],
)
def test_harmless_redirections_pass(active, cmd):
    assert run_hook(active, "pre", "Bash", {"command": cmd}) is None


def test_session_start_hook_emits_valid_context():
    out = subprocess.run([str(ROOT / "hooks" / "session-start")], capture_output=True, text=True, timeout=10)
    data = json.loads(out.stdout)
    ctx = data["hookSpecificOutput"]["additionalContext"]
    assert data["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert "using-qa-superteam" in ctx and "secret" in ctx and len(ctx) < 800
