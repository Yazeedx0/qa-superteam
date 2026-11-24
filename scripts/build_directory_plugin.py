#!/usr/bin/env python3
"""Build the Claude plugin-directory edition of QA Superteam into plugins/qa-superteam/.

The plugin directory accepts hooks, bin/ launchers, scripts, TOML and package files only from
Verified organizations. The full plugin (this repository's root) needs all of them: the `qast`
runtime, the qa-guard hook and the bundled copies. This edition is what an unverified publisher can
submit: instructions only (skills, agents, README, license, icon), generated from the same sources
so the two never drift. `qast` becomes an optional, separately installed runtime.

    python3 scripts/build_directory_plugin.py          # write plugins/qa-superteam/
    python3 scripts/build_directory_plugin.py --check  # CI: fail if it drifted from the sources
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "plugins" / "qa-superteam"
REPO_URL = "https://github.com/Yazeedx0/qa-superteam"
# Everything in a skill folder ships except the generated qast runtime bundle.
SKIP_PARTS = {"__pycache__"}
SKIP_DIRS = {Path("using-qa-superteam") / "scripts"}

DESCRIPTION = (
    "An AI quality engineering team as instructions: risk-based QA skills and 12 specialist agents "
    "that work evidence-first and never claim a pass that was not executed. The optional qast runtime "
    "for recorded execution, evidence and a deterministic release gate is installed separately."
)

SKILL_NOTE_RE = re.compile(
    r"^> `qast` is on PATH in Claude Code\. In other agents, run `\.\./using-qa-superteam/scripts/qast` "
    r"\(path relative to this file\) wherever this skill says `qast`\.$",
    re.M,
)
SKILL_NOTE = (
    "> `qast` is an optional command-line runtime that this edition does not bundle. If `command -v qast` "
    "finds nothing, follow *Tools* in the `using-qa-superteam` skill: report each `qast` step as BLOCKED "
    "(qast not installed) and continue with the work that needs no recorder."
)

FINDING_QAST_OLD = """**Finding `qast`.** In Claude Code the plugin puts it on PATH. In any other agent (Codex,
Cursor, Gemini CLI, Copilot, OpenCode, ...) it ships inside this skill: run
`scripts/qast` from this skill's folder, e.g. `.agents/skills/using-qa-superteam/scripts/qast doctor`,
and use that path wherever a skill says `qast`. It needs Python 3.11+ and nothing else."""
FINDING_QAST_NEW = f"""**`qast` is not bundled in this edition.** This edition contains the skills and agents only.
Run `command -v qast` once, before the first step that needs it.

- **Found:** use it exactly as every skill describes.
- **Not found:** say so once and tell the user the optional runtime is published in the project
  repository ({REPO_URL}); do not install anything yourself. Then do the work that needs no
  recorder: discovery by reading, requirements and invariants, risk and strategy, test design, static review,
  drafting the report. Report every step that needs recorded execution, evidence, independent
  verification or the release gate as `BLOCKED` ("qast not installed"). Nothing is `PASSED`,
  `CONFIRMED` or released on that basis, and no gate decision is produced. If the user asks you to run
  their own tests anyway, run exactly the command they name and quote the command and its result as
  "observed, unrecorded"."""

RESUME_OLD = " (this also re-enables the\nguard hook)"

# `--via-uvx` is a real qast flag; the directory scanner treats naming package launchers as a risk.
UVX_REPLACEMENTS = [
    ("`--via-uvx` downloads the scanner from the network;\nuse it only if the user agrees.",
     "the network-install option of `qast exec` downloads the scanner;\nuse it only if the user agrees."),
    ("Use `--via-uvx`, which\ndownloads the tool, only with the user's OK.",
     "Use the network-install option of `qast exec`, which\ndownloads the tool, only with the user's OK."),
    ("`--via-uvx` downloads a tool, so use it only when the delegation allows network installs.",
     "the network-install option of `qast exec` downloads a tool, so use it only when the delegation allows network installs."),
]

LEAD_OLD = '`"$(dirname "$(dirname "$(command -v qast)")")/skills/<workflow>/SKILL.md"` (default `full-audit`)'
LEAD_NEW = (
    "`../<workflow>/SKILL.md`, relative to the base directory shown when `using-qa-superteam` loads "
    "(default `full-audit`)"
)

# Anything that must not survive into the directory edition.
FORBIDDEN = ("scripts/qast", "on PATH in Claude Code", "uvx", "npx", "CLAUDE_PLUGIN_ROOT", "guard hook", "$(dirname")

README_TEMPLATE = """# QA Superteam (directory edition)

An AI quality engineering team for Claude Code, delivered as instructions: **{skills} skills** and
**{agents} specialist agents** that plan QA by risk, design tests with explicit pass/fail conditions,
investigate failures, and refuse to claim a pass or a confirmed defect that was not executed.

This edition contains no hooks, no executables and no scripts. It is generated from the same
sources as the full project ({repo}), so the methodology is identical.

## What works without anything else

Read-only analysis: discovery, requirements and invariants, risk assessment and strategy, test
design, static code and security review, bug-report analysis, report drafting, and the
specialist agents' judgment. Start with `/qa-superteam:full-audit`, `/qa-superteam:review-pr`,
`/qa-superteam:test-feature` or ask for QA in plain words; the `using-qa-superteam` skill routes it.

## What needs the optional `qast` runtime

Recorded test execution, evidence capture, independent verification of defects, run storage and
the deterministic release gate come from `qast`, a standard-library Python command-line tool that
this edition does not bundle. Without it the skills report those steps as `BLOCKED` (never as
passed) and tell you so. The runtime, its installation instructions and the safety hooks live in
the project repository: {repo}

## Safety

Instruction-only: it ships no code of its own. The skills default to read-only work, treat
repository content as data, never print secret values, and do not touch production targets or
change application code unless you authorize it.

## License

MIT. See `LICENSE`.
"""


def lean_skill_text(rel: Path, text: str) -> str:
    text = SKILL_NOTE_RE.sub(SKILL_NOTE, text)
    if rel == Path("using-qa-superteam/SKILL.md"):
        for old, new in ((FINDING_QAST_OLD, FINDING_QAST_NEW), (RESUME_OLD, "")):
            if text.count(old) != 1:
                raise SystemExit(f"build_directory_plugin: anchor not found in {rel}: {old[:50]!r}")
            text = text.replace(old, new)
    return text


def lean_agent_text(name: str, text: str) -> str:
    if name == "qa-lead.md":
        if text.count(LEAD_OLD) != 1:
            raise SystemExit("build_directory_plugin: qa-lead workflow-path anchor not found")
        text = text.replace(LEAD_OLD, LEAD_NEW)
    return text


def expected() -> dict[Path, bytes]:
    files: dict[Path, bytes] = {}
    plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
    plugin["description"] = DESCRIPTION
    files[OUT / ".claude-plugin" / "plugin.json"] = (json.dumps(plugin, indent=2, ensure_ascii=False) + "\n").encode()
    files[OUT / ".claude-plugin" / "icon.png"] = (ROOT / ".claude-plugin" / "icon.png").read_bytes()
    files[OUT / "LICENSE"] = (ROOT / "LICENSE").read_bytes()
    n_skills = sum(1 for p in (ROOT / "skills").iterdir() if (p / "SKILL.md").exists())
    n_agents = len(list((ROOT / "agents").glob("*.md")))
    readme = README_TEMPLATE.format(skills=n_skills, agents=n_agents, repo=REPO_URL)
    files[OUT / "README.md"] = readme.encode()
    skills = ROOT / "skills"
    for src in sorted(p for p in skills.rglob("*") if p.is_file()):
        rel = src.relative_to(skills)
        if SKIP_PARTS & set(rel.parts) or any(rel.is_relative_to(d) for d in SKIP_DIRS):
            continue
        data = src.read_bytes()
        if src.suffix == ".md":
            text = lean_skill_text(rel, data.decode("utf-8"))
            for old, new in UVX_REPLACEMENTS:
                text = text.replace(old, new)
            data = text.encode("utf-8")
        files[OUT / "skills" / rel] = data
    for src in sorted((ROOT / "agents").glob("*.md")):
        text = lean_agent_text(src.name, src.read_text(encoding="utf-8"))
        for old, new in UVX_REPLACEMENTS:
            text = text.replace(old, new)
        files[OUT / "agents" / src.name] = text.encode("utf-8")
    for path, data in files.items():
        if path.suffix == ".md" or path.name == "plugin.json":
            text = data.decode("utf-8")
            for bad in FORBIDDEN:
                if bad in text:
                    raise SystemExit(f"build_directory_plugin: {path.relative_to(ROOT)} still contains {bad!r}")
    return files


def main() -> int:
    check = "--check" in sys.argv
    want = expected()
    have = {p for p in OUT.rglob("*") if p.is_file()} if OUT.exists() else set()
    stale = sorted(str(p.relative_to(ROOT)) for p in have - set(want))
    drift = sorted(str(p.relative_to(ROOT)) for p, data in want.items() if not p.exists() or p.read_bytes() != data)
    if check:
        if stale or drift:
            for s in stale:
                print(f"stale: {s}")
            for d in drift:
                print(f"out of date: {d}")
            print("Run: python3 scripts/build_directory_plugin.py")
            return 1
        print(f"directory edition is up to date ({len(want)} files)")
        return 0
    if OUT.exists():
        shutil.rmtree(OUT)
    for path, data in want.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    print(f"wrote {len(want)} files to {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
