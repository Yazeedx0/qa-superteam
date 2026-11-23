# Running QA Superteam in different coding agents

QA Superteam is an [Agent Skills](https://agentskills.io) package. The skills are plain
`SKILL.md` folders. The deterministic tool `qast` is bundled inside the entry skill
(`skills/using-qa-superteam/scripts/qast`), so it works wherever the skill folders are
installed. Claude Code additionally gets a native plugin with agents and hooks.

## What each install provides

| Capability | Claude Code plugin | Any agent via `npx skills add` |
|---|---|---|
| 33 skills (methodology + workflows) | yes, as `/qa-superteam:<name>` commands | yes, as the agent's native skills |
| `qast` | on `PATH` | `<skills dir>/using-qa-superteam/scripts/qast` (Python 3.11+) |
| Evidence, verification gates, policy engine, reports | yes | yes (same `qast`) |
| 12 specialist agents | yes | no: subagent formats differ between agents; the workflows run single-agent |
| Guard hook (asks before risky actions during QA runs) | yes | no: rely on your agent's own approval settings and sandbox |
| Session pointer ("use the QA skills, never print secrets") | yes | Cursor (`hooks/hooks-cursor.json`) and Gemini CLI (`GEMINI.md`) via their native plugin formats; otherwise no |
| Workflow arguments (`$ARGUMENTS`) | substituted | not substituted; the skills tell the agent to use the user's request instead |
| Workflows start only on explicit request | yes (`disable-model-invocation`) | the field is ignored by most agents, so the agent may start a workflow on its own when the request matches |

## What was tested (0.1.0)

| Path | Status | How |
|---|---|---|
| Claude Code plugin | **Tested** | `claude plugin validate --strict`; live behavioral evals ([report](../evals/reports/2026-11-23-live-sonnet.md)) |
| `npx skills add` into `claude-code`, `codex`, `cursor`, `gemini-cli`, `github-copilot` and `opencode` (project scope) | **Tested** | `tests/integration/test_install_any_agent.py`: all 33 skills land in `.claude/skills/` and `.agents/skills/`; the bundled `qast` runs pytest and the gate from the installed folder; sibling-skill paths resolve |
| Behavior inside Codex, Cursor, Gemini CLI, Copilot, OpenCode and others | **Not tested** | No live sessions in those agents yet. The skills avoid Claude-only tool names and paths (`scripts/validate_plugin.py` rejects `${CLAUDE_PLUGIN_ROOT}` in skills) |
| Native plugin manifests (Codex, Cursor, Gemini CLI; Copilot CLI, Factory Droid and Qwen Code via the Claude marketplace manifest) | **Not tested** | JSON-validated and version-checked against the other manifests; formats follow widely used multi-agent skill repositories |

## How portability is maintained

- **`scripts/sync_skill_runtime.py`** copies `src/qa_superteam`, `policies/` and the config
  template into `skills/using-qa-superteam/scripts/`. It also copies `docs/policy.md` and
  `docs/risk-model.md` into the skills that reference them. CI fails if the copies drift
  (`--check`).
- **Skills reference each other with relative paths.** An example is
  `../using-qa-superteam/references/orchestration.md`. Installers place skills side by side,
  so these paths work in every layout; the validator checks they exist.
- **Every skill states how to find `qast`.** In Claude Code it is on `PATH`; elsewhere it is
  `../using-qa-superteam/scripts/qast`.

## Independent verification without subagents

In agents without subagents, the "independent verifier" runs in the same context unless
you start a fresh session. `qast verify` still requires:

- a verifier name different from the reporter;
- the verifier's own attributed (`--actor`) executions, run after the finding was recorded.

It cannot prove the contexts were separate. For high-stakes findings, run the
`verify-bug` workflow in a new session.

## CI

Markdown skills do not run anything by themselves. Unattended CI needs an agent runtime
plus credentials. The deterministic parts (`qast exec`, `qast gate --exit-code`,
`qast report`) need no agent at all; see [ci.md](ci.md).
