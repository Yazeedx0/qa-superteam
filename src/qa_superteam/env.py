"""Execution environment metadata and capability (tool availability) detection."""

from __future__ import annotations

import hashlib
import os
import platform
import socket
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import models as m
from .procexec import run, tool_version, which


def project_python(root: Path, configured: str = "") -> str:
    """Interpreter used to run the project's Python tests (never the plugin's own)."""
    if configured:
        return configured
    for cand in (".venv/bin/python", "venv/bin/python", ".venv/Scripts/python.exe"):
        p = root / cand
        if p.exists():
            return str(p)
    return "python3" if which("python3") else sys.executable


def git_info(root: Path) -> m.GitInfo:
    def g(*args: str) -> str | None:
        try:
            out = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, timeout=15)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return None
        return out.stdout.strip() if out.returncode == 0 else None

    inside = g("rev-parse", "--is-inside-work-tree")
    if inside != "true":
        return m.GitInfo(is_repo=False)
    status = g("status", "--porcelain", "--", ".", ":(exclude).qa-superteam")
    return m.GitInfo(
        is_repo=True,
        head=g("rev-parse", "HEAD"),
        branch=g("rev-parse", "--abbrev-ref", "HEAD"),
        dirty=bool(status) if status is not None else None,
    )


def environment_info(root: Path, tool_versions: dict[str, str] | None = None) -> m.EnvironmentInfo:
    gi = git_info(root)
    return m.EnvironmentInfo(
        platform=f"{platform.system()}-{platform.release()}-{platform.machine()}",
        python=platform.python_version(),
        hostname_hash=hashlib.sha256(socket.gethostname().encode()).hexdigest()[:12],
        tool_versions=dict(tool_versions or {}),
        ci=bool(os.environ.get("CI")),
        git_head=gi.head,
        git_dirty=gi.dirty,
    )


@dataclass
class Capability:
    name: str
    available: bool
    version: str | None = None
    detail: str | None = None
    used_by: list[str] = field(default_factory=list)
    install_hint: str | None = None


def _py_import(py: str, module: str, root: Path) -> str | None:
    res = run(
        [py, "-c", f"import importlib.metadata as m, {module}; print(m.version('{module}'))"],
        root,
        timeout_s=30,
        max_output_bytes=10_000,
    )
    if res.exit_code == 0 and res.stdout.strip():
        return res.stdout.strip().splitlines()[-1]
    return None


def _node_bin(root: Path, name: str) -> str | None:
    p = root / "node_modules" / ".bin" / name
    return str(p) if p.exists() else None


def detect_capabilities(root: Path, python: str = "") -> list[Capability]:
    py = project_python(root, python)
    caps: list[Capability] = []

    def add(name, version, used_by, hint, detail=None, available=None):
        caps.append(
            Capability(
                name=name,
                available=bool(version) if available is None else available,
                version=version,
                detail=detail,
                used_by=used_by,
                install_hint=None if (version or available) else hint,
            )
        )

    add("git", tool_version(["git", "--version"]), ["qa-discovery", "review-pr", "qa-regression"], "Install git")
    add("project-python", tool_version([py, "--version"], root), ["qa-unit", "qa-backend"], "Create a venv or set [python] interpreter", detail=py)
    add("pytest", _py_import(py, "pytest", root), ["qa-unit", "qa-backend", "qa-frontend"], f"{py} -m pip install pytest")
    add("httpx", _py_import(py, "httpx", root), ["qa-backend", "qa-security"], f"{py} -m pip install httpx")
    add("coverage", _py_import(py, "coverage", root), ["qa-unit"], f"{py} -m pip install coverage")
    add("hypothesis", _py_import(py, "hypothesis", root), ["qa-test-design"], f"{py} -m pip install hypothesis")
    add("testcontainers", _py_import(py, "testcontainers", root), ["qa-backend", "qa-data-integrity"], f"{py} -m pip install testcontainers")
    pw_py = _py_import(py, "playwright", root)
    browsers = Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or Path.home() / ".cache" / "ms-playwright")
    has_browser = browsers.exists() and any(browsers.glob("chromium*"))
    add(
        "playwright-python",
        pw_py,
        ["qa-frontend", "qa-accessibility"],
        f"{py} -m pip install playwright && {py} -m playwright install chromium",
        detail=("chromium installed" if has_browser else "no chromium found in " + str(browsers)) if pw_py else None,
    )
    add("node", tool_version(["node", "--version"]), ["qa-frontend", "qa-contracts"], "Install Node.js >= 18")
    pw_node = _node_bin(root, "playwright")
    add("playwright-node", tool_version([pw_node, "--version"], root) if pw_node else None, ["qa-frontend"], "npm i -D @playwright/test && npx playwright install chromium")
    for runner in ("vitest", "jest"):
        b = _node_bin(root, runner)
        add(runner, tool_version([b, "--version"], root) if b else None, ["qa-unit", "qa-frontend"], f"npm i -D {runner}")
    axe = find_axe(root)
    add("axe-core", "present" if axe else None, ["qa-accessibility"], "npm i -D axe-core  (or set QAST_AXE_PATH to axe.min.js)", detail=str(axe) if axe else None)
    add("k6", tool_version(["k6", "version"]), ["qa-performance"], "https://grafana.com/docs/k6/latest/set-up/install-k6/")
    docker_v = tool_version(["docker", "version", "--format", "{{.Server.Version}}"], timeout_s=10)
    add("docker", docker_v, ["qa-backend", "qa-data-integrity", "qa-reliability"], "Install Docker and start the daemon", detail=None if docker_v else "client missing or daemon not reachable")
    add("bandit", tool_version(["bandit", "--version"]), ["qa-security"], "pipx install bandit  (or uvx bandit)")
    add("pip-audit", tool_version(["pip-audit", "--version"]), ["qa-security"], "pipx install pip-audit  (or uvx pip-audit)")
    add("semgrep", tool_version(["semgrep", "--version"]), ["qa-security"], "pipx install semgrep")
    add("gitleaks", tool_version(["gitleaks", "version"]), ["qa-security"], "https://github.com/gitleaks/gitleaks#installing")
    add("npm", tool_version(["npm", "--version"]), ["qa-security"], "Install Node.js (npm audit)")
    add("uv", tool_version(["uv", "--version"]), ["qa-security"], "https://docs.astral.sh/uv/  (enables uvx-based scanners)")
    key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    add(
        "llm-judge-credentials",
        "ANTHROPIC_API_KEY set" if key else None,
        ["qa-ai-systems"],
        "Optional: export ANTHROPIC_API_KEY to enable model-graded checks",
        available=key,
    )
    add("claude-cli", tool_version(["claude", "--version"]), ["behavioral-evals"], "Optional: required only for live behavioral evals")
    return caps


def find_axe(root: Path) -> Path | None:
    env = os.environ.get("QAST_AXE_PATH")
    candidates = [Path(env)] if env else []
    candidates += [root / "node_modules" / "axe-core" / "axe.min.js"]
    for c in candidates:
        if c.exists():
            return c
    return None


def capabilities_as_dicts(caps: list[Capability]) -> list[dict]:
    return [asdict(c) for c in caps]
