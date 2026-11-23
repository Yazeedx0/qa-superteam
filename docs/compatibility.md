# Compatibility with other coding agents

Claude Code is the first-class target. The table shows which parts are portable and which
depend on Claude Code features. Nothing here claims support that has not been verified.

| Component | Portable? | Notes |
|---|---|---|
| `qast` CLI and core | **Yes** | Python ≥ 3.11, stdlib only. Any agent that can run shell commands can use it. CI runs it without any agent |
| Methodology skills (`skills/qa-*`, `using-qa-superteam`) | **Yes** (Agent Skills format) | Frontmatter uses only the portable `name` and `description` fields. The bodies refer to `qast` commands, not to Claude-only tools |
| Workflow skills (`skills/<workflow>`) | Partly | They use Claude Code features: `disable-model-invocation`, `argument-hint`, `$ARGUMENTS` and `${CLAUDE_PLUGIN_ROOT}` paths. Other hosts typically ignore unknown fields, but `$ARGUMENTS` is not substituted and `${CLAUDE_PLUGIN_ROOT}` paths do not resolve. Pass the arguments in your prompt and read referenced files from the clone |
| Agents (`agents/*.md`) | **No** | Claude Code subagent format |
| Guard hook (`hooks/`) | **No** | Claude Code hook protocol. On other hosts, rely on that host's sandbox and approval settings |
| Plugin packaging (`.claude-plugin/`) | **No** | Claude Code marketplace format |

## Using the skills in other agents (manual, not tested in CI)

1. Put `qast` on PATH: `ln -s <clone>/bin/qast ~/.local/bin/qast`.
2. Expose the skills to the host's skill directory. Many hosts read `~/.agents/skills/`.
   Codex also reads `~/.codex/skills/`. Check your host's documentation, because these
   locations change between releases:
   ```bash
   mkdir -p ~/.agents/skills
   for d in <clone>/skills/*/; do ln -s "$d" ~/.agents/skills/; done
   ```
3. Start with the `using-qa-superteam` skill and name the workflow explicitly ("follow the
   full-audit skill"), passing what `$ARGUMENTS` would have contained.

## What changes without Claude Code

- **Independent verification.** Without subagents, the "independent verifier" is the same
  context unless you start a fresh session. `qast verify` still requires a different
  verifier name and the verifier's own failing execution, but it cannot prove that the
  contexts were isolated. Run `verify-bug` in a separate session for high-stakes findings.
- **Guardrails.** Without the guard hook, only the host's permission system protects
  against risky commands. The adapters' own checks still apply: target allowlists, k6
  profile limits and read-only pytest runs.
- **Progressive disclosure.** This depends on the host loading skill bodies on demand. Some
  hosts inline every skill, which costs context.

## Hosts in CI

Markdown skills do not execute anything by themselves. Unattended CI needs an agent
runtime, for example Claude Code (`claude -p`) or the Claude Code GitHub Action, plus
credentials. Deterministic checks such as `qast exec`, `qast gate --exit-code` and
`qast report` need no agent at all. See [ci.md](ci.md).
