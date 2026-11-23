"""QA Superteam guard hook (PreToolUse / PostToolUse), active only during a QA run.

PreToolUse: for risky operations it returns ``permissionDecision: "ask"`` with a
reason, which forces the host's normal permission prompt.  It never returns
"allow", so it can only add friction, never bypass the host's permission model.

PostToolUse: appends a redacted record of commands and file mutations to the active
run's journal so every change made during QA is traceable.

Stdlib only; run with ``python3 -I``.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

STALE_AFTER_S = 12 * 3600

BASH_RULES: list[tuple[str, str]] = [
    (r"\bgit\s+push\b", "pushes to a remote"),
    (r"\bgit\s+(reset\s+--hard|clean\s+-[a-z]*f|checkout\s+--\s|restore\s+\.|stash\s+(drop|clear))", "discards local changes"),
    (r"\bgit\s+commit\b", "creates a commit (QA runs do not commit unless asked)"),
    (r"\brm\s+-[a-z]*r[a-z]*f?\s+(/|~|\.\s*$|\*|\.\.)", "recursively deletes broad paths"),
    (r"(?i)\b(drop|truncate)\s+(table|database|schema)\b", "destructive database statement"),
    (r"(?i)\bdelete\s+from\s+\w+\s*(;|$|\")", "DELETE without WHERE"),
    (r"(?i)\b(dropdb|flushall|flushdb|dropDatabase)\b", "destructive datastore command"),
    (r"\b(kubectl\s+(apply|delete|scale|rollout|edit|patch)|helm\s+(install|upgrade|uninstall|delete))\b", "changes a Kubernetes cluster"),
    (r"\bterraform\s+(apply|destroy|import)\b", "changes infrastructure"),
    (r"\b(fly|flyctl)\s+deploy\b|\bvercel\b.*--prod|\bheroku\s+(releases|deploy|ps:scale)|\bgcloud\b.*\bdeploy\b|\baws\s+\S+\s+(delete|terminate|put|update)", "deploys or mutates cloud resources"),
    (r"\b(npm|pnpm|yarn)\s+publish\b|\btwine\s+upload\b|\bdocker\s+push\b|\bgh\s+(release\s+create|pr\s+merge)\b", "publishes or merges"),
    (r"(^|[\s;&|])(cat|less|head|tail|more)\s+[^|;&]*\.env(\.|\s|$)", "prints an environment file that may contain secrets"),
    (r"(^|[\s;&|])(printenv|env)\s*($|[;&|])", "prints all environment variables (may contain secrets)"),
]
LOAD_TOOLS = re.compile(r"(^|[\s;&|/])(k6\s+run|ab\s|wrk\s|hey\s|vegeta\s|locust\b|artillery\s|siege\s|sqlmap\b|nikto\b|zap-|nuclei\b|ffuf\b|hydra\b)")
URL_RE = re.compile(r"https?://[^\s'\"`)]+")
BASELINE_RE = re.compile(r"(__snapshots__/|-snapshots/|\.snap$|(^|/)golden(s)?/|(^|/)baselines?/|ground_truth/|expected[-_]?output)", re.I)


def _marker(project: Path) -> tuple[str, Path] | None:
    m = project / ".qa-superteam" / "active-run"
    try:
        lines = m.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    if not lines:
        return None
    if time.time() - m.stat().st_mtime > STALE_AFTER_S:
        return None
    run_dir = Path(lines[2]) if len(lines) > 2 else project / ".qa-superteam" / "runs" / lines[0]
    return lines[0], run_dir


def _ask(reason: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "ask",
                    "permissionDecisionReason": f"QA Superteam guard (active QA run): {reason}. Approve only if this was explicitly requested.",
                }
            }
        )
    )


def _config(project: Path):
    try:
        from qa_superteam.config import load_config

        return load_config(project)
    except Exception:  # noqa: BLE001 - a broken config must not disable the guard
        return None


SHELL_WRITE_RES = [
    re.compile(r"\bsed\s+(?:-[a-zA-Z]*i[a-zA-Z]*|--in-place)\S*\s+(?:'[^']*'|\"[^\"]*\"|\S+)\s+(?P<path>[^\s;&|<>]+)"),
    re.compile(r"\bperl\s+-[a-zA-Z]*p[a-zA-Z]*i\S*\s+(?:-e\s+)?(?:'[^']*'|\"[^\"]*\")\s+(?P<path>[^\s;&|<>]+)"),
    re.compile(r"\btee\s+(?:-a\s+)?(?P<path>[^\s;&|<>-][^\s;&|<>]*)"),
    re.compile(r"(?<![0-9&<>])>{1,2}\s*(?P<path>[^\s;&|<>()]+)"),
    re.compile(r"\b(?:cp|mv|install)\s+(?:-\S+\s+)*\S+\s+(?P<path>[^\s;&|<>]+)\s*(?:$|[;&|])"),
]


def shell_write_targets(cmd: str) -> list[str]:
    out = []
    for rx in SHELL_WRITE_RES:
        for m in rx.finditer(cmd):
            p = m.group("path").strip("'\"")
            if p and not p.startswith(("/dev/", "&")) and p not in ("/dev/null",):
                out.append(p)
    return out


def check_bash(cmd: str, project: Path) -> str | None:
    for rx, why in BASH_RULES:
        if re.search(rx, cmd):
            return why
    for target in shell_write_targets(cmd):
        if target.startswith(("/tmp/", "$TMPDIR", "${TMPDIR")) or "$QAST_" in target or "${QAST_" in target:
            continue
        why = check_write(target, project, "Bash")
        if why and not why.startswith("writes outside the project"):
            return f"shell command writes a file: {why}"
    if LOAD_TOOLS.search(cmd) and "qast" not in cmd.split()[0:1]:
        cfg = _config(project)
        allow = cfg.permissions.authorized_targets if cfg else ["http://127.0.0.1", "http://localhost"]
        from qa_superteam.config import is_authorized

        bad = [u for u in URL_RE.findall(cmd) if not is_authorized(u, allow)]
        if bad:
            return f"load/security tool aimed at unauthorized target(s) {bad}"
        return "runs a load or active security tool directly; prefer `qast exec k6` which enforces target and profile limits"
    return None


def check_write(path_str: str, project: Path, tool: str) -> str | None:
    p = Path(path_str)
    if not p.is_absolute():
        p = project / p
    try:
        rel = p.resolve().relative_to(project.resolve()).as_posix()
    except ValueError:
        return f"writes outside the project ({path_str})"
    if rel.startswith(".qa-superteam/"):
        if rel.startswith(".qa-superteam/runs/") and ("/executions/" in rel or "/evidence/" in rel or "/artifacts/" in rel or "/verifications/" in rel or "/findings/" in rel):
            return "edits recorded QA evidence directly; records are write-once and must only be created through qast"
        if rel in (".qa-superteam/config.toml", ".qa-superteam/active-run"):
            return f"changes QA permissions/run state ({rel}); only the user should loosen QA permissions"
        return None
    if rel.endswith(".toml") and ("polic" in rel.lower()):
        return f"changes a release policy file ({rel}); policies must not be edited to change a decision"
    if BASELINE_RE.search(rel):
        return f"modifies a golden baseline/snapshot ({rel}); baselines must not be changed to make tests pass"
    cfg = _config(project)
    from qa_superteam.impact import classify_path

    kind, _, _ = classify_path(rel)
    exists = p.exists()
    if kind == "test":
        if cfg is None or not cfg.permissions.write_tests:
            return f"adds or edits a test ({rel}) but permissions.write_tests = false"
        if exists:
            return f"edits an EXISTING test ({rel}); confirm this does not weaken or delete assertions"
        test_dir = cfg.permissions.test_dir.rstrip("/") + "/"
        if not rel.startswith(test_dir):
            return f"creates a test outside permissions.test_dir ({test_dir})"
        return None
    if cfg is None or not cfg.permissions.modify_app_code:
        return f"modifies a non-test project file ({rel}) during a read-only QA run (permissions.modify_app_code = false)"
    return None


def main() -> int:
    phase = sys.argv[1] if len(sys.argv) > 1 else "pre"
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    project = Path(os.environ.get("CLAUDE_PROJECT_DIR") or event.get("cwd") or ".")
    active = _marker(project)
    if not active:
        return 0
    run_id, run_dir = active
    tool = event.get("tool_name", "")
    tin = event.get("tool_input") or {}
    if phase == "pre":
        reason = None
        if tool == "Bash":
            reason = check_bash(str(tin.get("command", "")), project)
        elif tool in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
            reason = check_write(str(tin.get("file_path") or tin.get("notebook_path") or ""), project, tool)
        if reason:
            _ask(reason)
        return 0
    # post: traceability journal
    try:
        from qa_superteam.redact import Redactor

        r = Redactor()
        if tool == "Bash":
            rec = {"event": "tool.bash", "command": r.redact(str(tin.get("command", ""))[:2000])}
        else:
            rec = {"event": "tool.file_mutation", "tool": tool, "path": str(tin.get("file_path") or tin.get("notebook_path") or "")}
        rec["ts"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        rec["agent"] = event.get("agent_type") or event.get("subagent_type") or "main"
        if run_dir.exists():
            with open(run_dir / "journal.jsonl", "a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001 - journaling must never break the session
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
