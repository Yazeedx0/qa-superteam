"""Safe subprocess execution for test tools.

* argv lists only — never ``shell=True``
* hard timeout that kills the whole process group
* bounded output capture (head + tail kept, middle elided)
* missing executables reported as a distinct outcome (-> BLOCKED, not FAILED)
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ProcResult:
    argv: list[str]
    exit_code: int | None
    stdout: str
    stderr: str
    duration_s: float
    timed_out: bool
    not_found: bool = False
    truncated: bool = False


def which(executable: str, cwd: Path | None = None) -> str | None:
    """Resolve an executable, also checking project-local bins (node_modules/.bin, .venv/bin)."""
    if os.sep in executable or (os.altsep and os.altsep in executable):
        p = Path(executable)
        if not p.is_absolute() and cwd is not None:
            p = cwd / p
        return str(p) if p.exists() and os.access(p, os.X_OK) else None
    if cwd is not None:
        for local in ("node_modules/.bin", ".venv/bin", "venv/bin"):
            cand = cwd / local / executable
            if cand.exists() and os.access(cand, os.X_OK):
                return str(cand)
    return shutil.which(executable)


def _cap(data: bytes, limit: int) -> tuple[str, bool]:
    if len(data) <= limit:
        return data.decode("utf-8", errors="replace"), False
    half = max(limit // 2, 1)
    head = data[:half].decode("utf-8", errors="replace")
    tail = data[-half:].decode("utf-8", errors="replace")
    return f"{head}\n... [qast: {len(data) - 2 * half} bytes elided] ...\n{tail}", True


def run(
    argv: list[str],
    cwd: Path,
    timeout_s: float,
    env: dict[str, str] | None = None,
    max_output_bytes: int = 2_000_000,
    stdin_data: str | None = None,
) -> ProcResult:
    if not argv:
        raise ValueError("empty argv")
    resolved = which(argv[0], cwd)
    if resolved is None:
        return ProcResult(argv, None, "", f"executable not found: {argv[0]}", 0.0, False, not_found=True)
    full_env = dict(os.environ)
    if env:
        full_env.update(env)
    start = time.monotonic()
    # Spool to temp files: avoids pipe deadlocks with chatty tools.
    with tempfile.TemporaryFile() as out_f, tempfile.TemporaryFile() as err_f:
        kwargs: dict = {}
        if sys.platform != "win32":
            kwargs["start_new_session"] = True
        else:  # pragma: no cover
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
        try:
            proc = subprocess.Popen(
                [resolved, *argv[1:]],
                cwd=str(cwd),
                env=full_env,
                stdout=out_f,
                stderr=err_f,
                stdin=subprocess.PIPE if stdin_data is not None else subprocess.DEVNULL,
                **kwargs,
            )
        except (FileNotFoundError, PermissionError) as e:
            return ProcResult(argv, None, "", str(e), 0.0, False, not_found=True)
        timed_out = False
        try:
            proc.communicate(input=stdin_data.encode() if stdin_data is not None else None, timeout=timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            _kill_tree(proc)
            proc.wait(timeout=10)
        duration = time.monotonic() - start
        out_f.seek(0)
        err_f.seek(0)
        stdout, t1 = _cap(out_f.read(), max_output_bytes)
        stderr, t2 = _cap(err_f.read(), max_output_bytes)
    return ProcResult(
        argv=argv,
        exit_code=None if timed_out else proc.returncode,
        stdout=stdout,
        stderr=stderr,
        duration_s=round(duration, 3),
        timed_out=timed_out,
        truncated=t1 or t2,
    )


def _kill_tree(proc: subprocess.Popen) -> None:
    if sys.platform == "win32":  # pragma: no cover
        proc.kill()
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def tool_version(argv: list[str], cwd: Path | None = None, timeout_s: float = 15) -> str | None:
    """Return the first line of a ``--version`` style command, or None if unavailable."""
    res = run(argv, cwd or Path.cwd(), timeout_s=timeout_s, max_output_bytes=20_000)
    if res.not_found or res.timed_out or res.exit_code not in (0,):
        return None
    text = (res.stdout or res.stderr).strip()
    return text.splitlines()[0][:200] if text else None
