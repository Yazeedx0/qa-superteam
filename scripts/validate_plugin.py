#!/usr/bin/env python3
"""Structural validation of the QA Superteam plugin (stdlib only; runs in CI).

Complements `claude plugin validate` (manifest/schema checks by Claude Code) with
QA-Superteam-specific contracts:

* manifests: names, versions consistent across plugin.json / marketplace.json / pyproject / package
* skills: frontmatter fields, name == directory, description length, size budget,
  required sections, workflow skills user-invoked only, links resolve,
  every `qast ...` command cited exists in the real CLI parser
* agents: frontmatter, no plugin-ignored fields, only qa-lead may delegate, HANDOFF contract
* hooks: JSON valid and referenced scripts exist and are executable
* directory edition (plugins/qa-superteam): in sync with skills/ + agents/, and only file types the plugin
  directory accepts from unverified organizations (no hooks, bin/, scripts, TOML, package files)
* evals: every skill has >= 1 behavioral scenario with known check types and fixtures
* hygiene: no developer-machine paths, no empty directories
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

SKILL_FIELDS = {
    "name", "description", "when_to_use", "argument-hint", "arguments", "disable-model-invocation", "user-invocable",
    "allowed-tools", "disallowed-tools", "model", "effort", "context", "agent", "hooks", "paths", "shell",
    "license", "compatibility", "metadata",
}
AGENT_FIELDS = {
    "name", "description", "tools", "disallowedTools", "model", "maxTurns", "skills", "memory", "background",
    "effort", "isolation", "color", "autoCompactWindow", "omitClaudeMd",
}
AGENT_IGNORED_IN_PLUGINS = {"hooks", "mcpServers", "permissionMode", "initialPrompt"}
KNOWN_TOOLS = {"Read", "Grep", "Glob", "Bash", "Write", "Edit", "MultiEdit", "NotebookEdit", "Skill", "Agent", "WebFetch", "WebSearch", "TodoWrite"}
WORKFLOWS = {"full-audit", "review-pr", "test-feature", "test-api", "test-e2e", "security-review", "eval-ai", "explore", "verify-bug", "regression", "release-check", "improve-suite"}
REQUIRED_SECTIONS = ["purpose", "use when", "input", "tool", "method", "stop", "safety", "output", "checklist"]
CHECK_TYPES = {
    "skill_invoked", "skill_not_invoked", "agent_invoked", "command_ran", "command_not_ran", "final_text_matches",
    "final_text_not_matches", "no_unsupported_pass_claim", "findings_vs_ground_truth", "no_writes_outside", "record_exists",
}
FIXTURES = {None, "backend-api", "web-checkout", "ai-support-bot"}
DEV_PATH_RE = re.compile(r"(/home/[a-z][\w.-]*/|/Users/[A-Za-z][\w.-]*/|C:\\\\Users\\\\)")


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.checked = 0

    def err(self, where: str, msg: str) -> None:
        self.errors.append(f"{where}: {msg}")

    def warn(self, where: str, msg: str) -> None:
        self.warnings.append(f"{where}: {msg}")


def parse_frontmatter(text: str) -> tuple[dict, str] | None:
    """Minimal YAML-frontmatter reader for flat `key: value` maps (what skills/agents use)."""
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---", 4)
    if end < 0:
        return None
    block, body = text[4:end], text[end + 4 :]
    data: dict[str, object] = {}
    key = None
    for raw in block.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if raw.startswith((" ", "\t", "-")) and key:
            data[key] = (str(data[key]) + " " + raw.strip()).strip()
            continue
        if ":" not in raw:
            return None
        key, _, val = raw.partition(":")
        key, val = key.strip(), val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        if val.lower() in ("true", "false"):
            data[key] = val.lower() == "true"
        elif re.fullmatch(r"-?\d+", val):
            data[key] = int(val)
        else:
            data[key] = val
    return data, body


def qast_command_tree() -> dict[str, set[str]]:
    from qa_superteam.cli import build_parser

    parser = build_parser()
    tree: dict[str, set[str]] = {}
    for action in parser._subparsers._group_actions:  # noqa: SLF001
        for name, sub in action.choices.items():
            nested: set[str] = set()
            if sub._subparsers is not None:  # noqa: SLF001
                for a in sub._subparsers._group_actions:  # noqa: SLF001
                    if hasattr(a, "choices") and isinstance(a.choices, dict):
                        nested |= set(a.choices)
            tree[name] = nested
    return tree


QAST_RE = re.compile(r"\bqast\s+([a-z][a-z-]*)(?:\s+([a-z][a-z-]*))?")


CODE_RE = re.compile(r"```[^\n]*\n(.*?)```|`([^`\n]+)`", re.S)
CMD_POS_RE = re.compile(r"(?:^|&&|\|\||[|;(]|\$\s|\$\()\s*(qast\s+[a-z][a-z-]*(?:\s+[a-z][a-z-]*)?)", re.M)


def code_segments(text: str) -> str:
    """Commands cited in command position: inline spans starting with `qast`, or fenced-block lines/pipelines."""
    out = []
    for m in CODE_RE.finditer(text):
        block, span = m.group(1), m.group(2)
        if span is not None:
            if span.lstrip().startswith("qast "):
                out.append(span.strip())
            continue
        code = "\n".join(ln for ln in (block or "").splitlines() if not ln.lstrip().startswith(("#", "//", "--", "*")))
        out += [c for c in CMD_POS_RE.findall(code)]
    return " ;\n".join(out)


def check_qast_refs(where: str, text: str, tree: dict[str, set[str]], rep: Report) -> None:
    for m in QAST_RE.finditer(code_segments(text)):
        cmd, sub = m.group(1), m.group(2)
        if cmd in ("command", "commands"):  # prose such as "every qast command"
            continue
        if cmd not in tree:
            rep.err(where, f"cites unknown command `qast {cmd}`")
            continue
        nested = tree[cmd]
        if nested and sub and sub not in nested and cmd in ("run", "finding", "ai-eval"):
            rep.err(where, f"cites unknown command `qast {cmd} {sub}`")


def check_links(where: Path, body: str, rep: Report) -> None:
    for target in re.findall(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", body):
        if re.match(r"[a-z]+://", target) or target.startswith("mailto:"):
            continue
        p = (where.parent / target).resolve()
        if not p.exists():
            rep.err(str(where.relative_to(ROOT)), f"broken link {target}")
    for target in re.findall(r"`(\.\./[a-z0-9-]+/[^\s`]+)`", body):  # sibling-skill paths used in any agent
        if "<" in target or "..." in target[3:]:
            continue
        if not (where.parent / target).exists():
            rep.err(str(where.relative_to(ROOT)), f"relative path {target} does not exist")
    if "${CLAUDE_PLUGIN_ROOT}" in body and where.parts[-3:-2] != ("hooks",):
        rep.err(str(where.relative_to(ROOT)), "uses ${CLAUDE_PLUGIN_ROOT}; skills must use relative paths so they work in every agent")
    for target in re.findall(r"\$\{CLAUDE_PLUGIN_ROOT\}/([^\s`'\")]+)", body):
        target = target.rstrip(".,;:")
        if "..." in target or "<" in target:
            continue
        if not (ROOT / target).exists():
            rep.err(str(where.relative_to(ROOT)), f"${{CLAUDE_PLUGIN_ROOT}}/{target} does not exist")


def validate_manifests(rep: Report) -> None:
    pj = ROOT / ".claude-plugin" / "plugin.json"
    mj = ROOT / ".claude-plugin" / "marketplace.json"
    try:
        plugin = json.loads(pj.read_text())
        market = json.loads(mj.read_text())
    except (OSError, json.JSONDecodeError) as e:
        rep.err("manifest", str(e))
        return
    rep.checked += 2
    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", plugin.get("name", "")):
        rep.err("plugin.json", "name must be kebab-case")
    for k in ("version", "description", "license"):
        if not plugin.get(k):
            rep.err("plugin.json", f"missing {k}")
    entries = [p for p in market.get("plugins", []) if p.get("name") == plugin.get("name")]
    if not entries:
        rep.err("marketplace.json", "does not list the plugin")
    elif entries[0].get("source") != "./":
        rep.err("marketplace.json", "plugin source should be './' for this single-repo marketplace")
    if not market.get("owner", {}).get("name"):
        rep.err("marketplace.json", "owner.name required")
    versions = {"plugin.json": plugin.get("version")}
    if entries:
        versions["marketplace.json"] = entries[0].get("version")
    versions["pyproject.toml"] = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    from qa_superteam import __version__

    versions["qa_superteam.__version__"] = __version__
    for other in (".codex-plugin/plugin.json", ".cursor-plugin/plugin.json", "gemini-extension.json"):
        path = ROOT / other
        if path.exists():
            try:
                versions[other] = json.loads(path.read_text()).get("version")
            except json.JSONDecodeError as e:
                rep.err(other, f"invalid JSON: {e}")
    if len(set(versions.values())) != 1:
        rep.err("versions", f"inconsistent: {versions}")
    import subprocess

    out = subprocess.run([sys.executable, str(ROOT / "scripts" / "sync_skill_runtime.py"), "--check"], capture_output=True, text=True)
    if out.returncode != 0:
        rep.err("skills/using-qa-superteam/scripts", "bundled qast runtime is out of date: run python3 scripts/sync_skill_runtime.py")


DIRECTORY_EXT = {".md", ".txt", ".json", ".yaml", ".yml", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico"}
DIRECTORY_BARE = {"LICENSE"}
DIRECTORY_REFUSED_NAMES = {"claude.md", "claude.local.md", "agents.md"}
DIRECTORY_REFUSED_DIRS = {"bin", "hooks", "node_modules", ".claude", "egress"}
DIRECTORY_SAFE_PATH = re.compile(r"[A-Za-z0-9._/-]+")


def validate_directory_edition(rep: Report) -> None:
    """plugins/qa-superteam must stay what an unverified publisher can submit to the plugin directory."""
    import subprocess

    base = ROOT / "plugins" / "qa-superteam"
    if not base.is_dir():
        rep.err("plugins/qa-superteam", "directory edition missing: run python3 scripts/build_directory_plugin.py")
        return
    out = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_directory_plugin.py"), "--check"], capture_output=True, text=True)
    if out.returncode != 0:
        rep.err("plugins/qa-superteam", "out of date with skills/ and agents/: run python3 scripts/build_directory_plugin.py")
    rep.checked += 1
    for p in sorted(base.rglob("*")):
        rel = p.relative_to(ROOT)
        if p.is_dir():
            if p.name in DIRECTORY_REFUSED_DIRS:
                rep.err(str(rel), "folder refused by the plugin directory for unverified organizations")
            continue
        if not DIRECTORY_SAFE_PATH.fullmatch(str(p.relative_to(base))):
            rep.err(str(rel), "path has a character or name not every computer keeps")
        if p.name.lower() in DIRECTORY_REFUSED_NAMES:
            rep.err(str(rel), "CLAUDE.md / AGENTS.md style files are refused")
        if p.suffix.lower() not in DIRECTORY_EXT and p.name not in DIRECTORY_BARE:
            rep.err(str(rel), "file type refused (only Markdown, text, JSON, YAML and PNG/JPEG/GIF/WebP/ICO images are accepted)")
            continue
        data = p.read_bytes()
        if data.startswith(b"#!"):
            rep.err(str(rel), "starts with #! (script)")
        if p.suffix.lower() in (".md", ".txt", ".json", ".yaml", ".yml") or p.name in DIRECTORY_BARE:
            try:
                data.decode("utf-8")
            except UnicodeDecodeError:
                rep.err(str(rel), "not UTF-8")
            if b"\x00" in data:
                rep.err(str(rel), "contains a NUL byte")
    icon = base / ".claude-plugin" / "icon.png"
    if not icon.exists():
        rep.err("plugins/qa-superteam/.claude-plugin/icon.png", "missing icon (square PNG, 512-2048 px, under 2 MB)")
    else:
        import struct

        raw = icon.read_bytes()
        w, h = struct.unpack(">II", raw[16:24]) if raw[:8] == b"\x89PNG\r\n\x1a\n" else (0, 0)
        if w != h or not 512 <= w <= 2048 or len(raw) >= 2 * 1024 * 1024:
            rep.err("plugins/qa-superteam/.claude-plugin/icon.png", f"icon must be a square PNG of 512-2048 px under 2 MB (got {w}x{h}, {len(raw)} bytes)")
    manifest = base / ".claude-plugin" / "plugin.json"
    try:
        edition = json.loads(manifest.read_text())
        full = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
    except (OSError, json.JSONDecodeError) as e:
        rep.err("plugins/qa-superteam/.claude-plugin/plugin.json", str(e))
        return
    for key in ("name", "version"):
        if edition.get(key) != full.get(key):
            rep.err("plugins/qa-superteam/.claude-plugin/plugin.json", f"{key} differs from the full plugin ({edition.get(key)!r} vs {full.get(key)!r})")


def validate_skills(rep: Report, tree) -> list[str]:
    names = []
    for d in sorted((ROOT / "skills").iterdir()):
        if not d.is_dir():
            continue
        where = f"skills/{d.name}"
        sk = d / "SKILL.md"
        if not sk.exists():
            rep.err(where, "missing SKILL.md")
            continue
        rep.checked += 1
        text = sk.read_text(encoding="utf-8")
        if len(text.encode()) >= 20_000:
            rep.err(where, f"SKILL.md is {len(text.encode())} bytes (limit 20000); move detail to references/")
        elif text.count("\n") > 200:
            rep.warn(where, f"SKILL.md has {text.count(chr(10))} lines; aim for < 150")
        fm = parse_frontmatter(text)
        if fm is None:
            rep.err(where, "invalid or missing frontmatter")
            continue
        meta, body = fm
        unknown = set(meta) - SKILL_FIELDS
        if unknown:
            rep.err(where, f"unknown frontmatter fields {sorted(unknown)}")
        if meta.get("name") != d.name:
            rep.err(where, f"name {meta.get('name')!r} must equal directory name")
        desc = str(meta.get("description", ""))
        if not desc:
            rep.err(where, "description required")
        elif len(desc) > 1024:
            rep.err(where, f"description is {len(desc)} chars (max 1024)")
        if d.name in WORKFLOWS:
            if meta.get("disable-model-invocation") is not True:
                rep.err(where, "workflow skills must set disable-model-invocation: true")
        else:
            if meta.get("disable-model-invocation") is True:
                rep.err(where, "methodology skills must stay model-invocable")
            if d.name != "using-qa-superteam":
                if not desc.lower().startswith("use when"):
                    rep.warn(where, "description should start with 'Use when'")
                heads = " ".join(h.lower() for h in re.findall(r"^#{2,3}\s+(.+)$", body, re.M))
                missing = [s for s in REQUIRED_SECTIONS if s not in heads]
                if missing:
                    rep.err(where, f"missing required sections: {missing}")
        if re.search(r"\b(TODO|TBD|FIXME)\b", CODE_RE.sub("", text)):
            rep.err(where, "contains TODO/TBD/FIXME placeholder")
        check_links(sk, body, rep)
        check_qast_refs(where, text, tree, rep)
        for ref in sorted((d / "references").glob("*.md")) if (d / "references").exists() else []:
            rep.checked += 1
            rtext = ref.read_text(encoding="utf-8")
            check_links(ref, rtext, rep)
            check_qast_refs(f"{where}/references/{ref.name}", rtext, tree, rep)
            if re.search(r"\b(TODO|TBD|FIXME)\b", CODE_RE.sub("", rtext)):
                rep.err(f"{where}/references/{ref.name}", "contains TODO/TBD/FIXME placeholder")
        names.append(d.name)
    missing_wf = WORKFLOWS - set(names)
    if missing_wf:
        rep.err("skills", f"missing workflow skills {sorted(missing_wf)}")
    return names


def validate_agents(rep: Report, tree) -> None:
    files = sorted((ROOT / "agents").glob("*.md"))
    if not files:
        rep.err("agents", "no agent definitions")
    for f in files:
        where = f"agents/{f.name}"
        rep.checked += 1
        fm = parse_frontmatter(f.read_text(encoding="utf-8"))
        if fm is None:
            rep.err(where, "invalid frontmatter")
            continue
        meta, body = fm
        if meta.get("name") != f.stem:
            rep.err(where, "name must equal file name")
        if ":" in str(meta.get("name", "")):
            rep.err(where, "name must not contain ':'")
        if not meta.get("description"):
            rep.err(where, "description required")
        ignored = set(meta) & AGENT_IGNORED_IN_PLUGINS
        if ignored:
            rep.err(where, f"fields ignored for plugin agents: {sorted(ignored)}")
        unknown = set(meta) - AGENT_FIELDS - AGENT_IGNORED_IN_PLUGINS
        if unknown:
            rep.err(where, f"unknown fields {sorted(unknown)}")
        tools = [t.strip() for t in str(meta.get("tools", "")).split(",") if t.strip()]
        if not tools:
            rep.err(where, "explicit tools allowlist required (bounds what a specialist can do)")
        bad = [t for t in tools if t not in KNOWN_TOOLS]
        if bad:
            rep.err(where, f"unknown tools {bad}")
        if "Agent" in tools and f.stem != "qa-lead":
            rep.err(where, "only qa-lead may delegate (Agent tool); specialists must not spawn agents")
        if f.stem != "qa-lead" and "HANDOFF" not in body:
            rep.err(where, "must end with the HANDOFF block from the handoff contract")
        if not isinstance(meta.get("maxTurns"), int):
            rep.err(where, "maxTurns (int) required to bound the agent loop")
        check_qast_refs(where, body, tree, rep)


def validate_hooks(rep: Report) -> None:
    hj = ROOT / "hooks" / "hooks.json"
    if not hj.exists():
        return
    rep.checked += 1
    try:
        data = json.loads(hj.read_text())
    except json.JSONDecodeError as e:
        rep.err("hooks.json", str(e))
        return
    for event, groups in data.get("hooks", {}).items():
        for g in groups:
            for h in g.get("hooks", []):
                cmd = h.get("command", "")
                for script in re.findall(r"\$\{CLAUDE_PLUGIN_ROOT\}/([^\s\"']+)", cmd):
                    p = ROOT / script
                    if not p.exists():
                        rep.err("hooks.json", f"{event}: missing {script}")
                    elif not os.access(p, os.X_OK):
                        rep.err("hooks.json", f"{event}: {script} is not executable")


def validate_scenarios(rep: Report, skills: list[str]) -> None:
    sdir = ROOT / "evals" / "scenarios"
    ids = set()
    for skill in skills:
        f = sdir / f"{skill}.json"
        where = f"evals/scenarios/{skill}.json"
        if not f.exists():
            rep.err(where, "missing behavioral scenarios for skill")
            continue
        rep.checked += 1
        try:
            items = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            rep.err(where, f"invalid JSON: {e}")
            continue
        if not isinstance(items, list) or not items:
            rep.err(where, "must be a non-empty JSON array")
            continue
        for sc in items:
            sid = sc.get("id", "?")
            if sid in ids:
                rep.err(where, f"duplicate scenario id {sid}")
            ids.add(sid)
            for k in ("id", "skill", "prompt", "checks"):
                if k not in sc:
                    rep.err(where, f"{sid}: missing {k}")
            if sc.get("fixture") not in FIXTURES:
                rep.err(where, f"{sid}: unknown fixture {sc.get('fixture')!r}")
            for c in sc.get("checks", []):
                if c.get("type") not in CHECK_TYPES:
                    rep.err(where, f"{sid}: unknown check type {c.get('type')!r}")
                for key in ("pattern",):
                    if key in c:
                        try:
                            re.compile(c[key])
                        except re.error as e:
                            rep.err(where, f"{sid}: bad regex {c[key]!r}: {e}")
            for cond in sc.get("conditions", ["plugin"]):
                if cond not in ("plugin", "baseline"):
                    rep.err(where, f"{sid}: unknown condition {cond}")
    for f in sdir.glob("*.json"):
        if f.stem not in skills:
            rep.err(f"evals/scenarios/{f.name}", "scenario file for a skill that does not exist")


def validate_hygiene(rep: Report) -> None:
    scan = ["skills", "agents", "hooks", "src", "docs", "policies", "templates", "scripts", "evals/harness", "evals/scenarios", ".claude-plugin", "README.md", ".github"]
    for item in scan:
        base = ROOT / item
        paths = [base] if base.is_file() else (list(base.rglob("*")) if base.exists() else [])
        for p in paths:
            if p.is_file() and p.suffix in (".md", ".py", ".json", ".toml", ".sh", ".yml", ".yaml", "") and "__pycache__" not in p.parts:
                try:
                    text = p.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    continue
                if DEV_PATH_RE.search(text):
                    rep.err(str(p.relative_to(ROOT)), "contains a developer-machine absolute path")
    skip = {".git", "node_modules", "__pycache__", ".qa-superteam", ".pytest_cache"}
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in skip]
        if not dirnames and not filenames:
            rep.err(str(Path(dirpath).relative_to(ROOT)), "empty directory")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    rep = Report()
    tree = qast_command_tree()
    validate_manifests(rep)
    skills = validate_skills(rep, tree)
    validate_agents(rep, tree)
    validate_hooks(rep)
    validate_directory_edition(rep)
    validate_scenarios(rep, skills)
    validate_hygiene(rep)
    if args.json:
        print(json.dumps({"checked": rep.checked, "errors": rep.errors, "warnings": rep.warnings}, indent=2))
    else:
        for w in rep.warnings:
            print(f"warning: {w}")
        for e in rep.errors:
            print(f"ERROR: {e}")
        print(f"validate_plugin: {rep.checked} items checked, {len(rep.errors)} error(s), {len(rep.warnings)} warning(s)")
    return 1 if rep.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
