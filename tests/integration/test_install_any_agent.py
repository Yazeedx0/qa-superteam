"""Install the skills the way other agents' users do (`npx skills add`) and run the bundled qast.

Needs Node >= 22.20 and network access to fetch the `skills` CLI; skips with the reason otherwise.
"""

import os
import shutil
import subprocess

import pytest
from conftest import ROOT

pytestmark = pytest.mark.integration
SKILLS_CLI = "skills@1.9.0"


def node_ok() -> bool:
    if not shutil.which("npx") or not shutil.which("node"):
        return False
    v = subprocess.run(["node", "--version"], capture_output=True, text=True).stdout.strip().lstrip("v").split(".")
    return (int(v[0]), int(v[1])) >= (22, 20)


@pytest.mark.skipif(not node_ok(), reason="npx skills needs Node >= 22.20")
def test_npx_skills_install_works_for_multiple_agents(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=proj, check=True)
    env = {**os.environ, "DISABLE_TELEMETRY": "1", "DO_NOT_TRACK": "1"}
    out = subprocess.run(
        ["npx", "-y", SKILLS_CLI, "add", str(ROOT), "--skill", "*", "-a", "claude-code", "-a", "codex", "-a", "cursor",
         "-a", "gemini-cli", "-a", "github-copilot", "-a", "opencode", "-y", "--copy"],
        cwd=proj, env=env, capture_output=True, text=True, timeout=300,
    )
    if out.returncode != 0 and ("ENOTFOUND" in out.stderr or "network" in out.stderr.lower()):
        pytest.skip("no network access to fetch the skills CLI")
    assert out.returncode == 0, out.stdout[-2000:] + out.stderr[-2000:]
    expected = {p.name for p in (ROOT / "skills").iterdir() if (p / "SKILL.md").exists()}
    for agent_dir in (proj / ".claude" / "skills", proj / ".agents" / "skills"):
        assert {p.name for p in agent_dir.iterdir()} >= expected, agent_dir
    qast = proj / ".agents" / "skills" / "using-qa-superteam" / "scripts" / "qast"
    assert os.access(qast, os.X_OK)
    (proj / "tests").mkdir()
    (proj / "tests" / "test_a.py").write_text("def test_ok():\n    assert True\n")
    run = lambda *a: subprocess.run([str(qast), *a], cwd=proj, capture_output=True, text=True, timeout=120)  # noqa: E731
    assert run("run", "start", "--mode", "adhoc", "--scope", "install check").returncode == 0
    res = run("exec", "pytest", "--group", "existing-suite", "--", "tests")
    assert "PASSED (PASSED 1)" in res.stdout, res.stdout + res.stderr
    assert "DECISION: PASS" in run("gate").stdout
    # sibling-relative paths used by workflow skills resolve in the installed layout
    wf = proj / ".agents" / "skills" / "full-audit"
    assert (wf / "../using-qa-superteam/references/orchestration.md").resolve().exists()
