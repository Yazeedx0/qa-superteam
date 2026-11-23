from __future__ import annotations

import io
import json
import shutil
import subprocess
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(__file__).parent / "data"
sys.path.insert(0, str(ROOT / "src"))


@pytest.fixture
def project(tmp_path, monkeypatch):
    """An empty project directory with a pinned clock."""
    monkeypatch.setenv("QAST_FIXED_TIME", "2026-01-01T00:00:00Z")
    p = tmp_path / "proj"
    p.mkdir()
    return p


@pytest.fixture
def qast(project):
    """Call the CLI in-process: qast("run", "start", ...) -> (exit_code, stdout)."""
    from qa_superteam.cli import main

    def call(*args: str, cwd: Path | None = None):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(["--project", str(cwd or project), *args])
        return code, buf.getvalue()

    return call


@pytest.fixture
def store(project):
    from qa_superteam.config import load_config
    from qa_superteam.store import RunStore

    return RunStore.create(load_config(project), "adhoc", "unit test")


def copy_fixture(name: str, dest: Path) -> Path:
    src = ROOT / "examples" / name
    out = dest / name
    shutil.copytree(src, out, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", ".qa-superteam", "node_modules"))
    nm = src / "node_modules"
    if nm.exists():
        (out / "node_modules").symlink_to(nm)
    return out


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
                          env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com", "GIT_COMMITTER_NAME": "t",
                               "GIT_COMMITTER_EMAIL": "t@example.com", "PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": str(cwd)}).stdout


def load_json(name: str):
    return json.loads((DATA / name).read_text())
