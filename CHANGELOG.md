# Changelog

All notable changes are documented here. The project follows [Semantic Versioning](https://semver.org/):
the public interface is the set of skill names and their invocation, `qast` commands and flags,
record schemas (`schemas/`), policy keys and exit codes.

## [0.1.0] - 2026-11-23

### Added
- Claude Code plugin with marketplace manifest; `bin/qast` on the Bash PATH.
- 21 methodology skills and 12 user-invoked workflows (`/qa-superteam:*`), each with behavioral eval scenarios.
- 12 specialist agents with tool allowlists, turn limits and a structured HANDOFF contract.
- `qast` stdlib-only core: run lifecycle with phase checkpoints, discovery, git-diff impact analysis,
  baseline risk scoring, validated records, write-once store, content-addressed redacted evidence.
- Adapters: pytest (own reporter plugin), JUnit, Vitest, Jest, Playwright Test, generic command, k6
  (target allowlist, smoke/load profiles), axe-core via Playwright, AI eval runner, Bandit, pip-audit,
  npm audit, Semgrep, gitleaks.
- Evidence-gated finding lifecycle (`qast reproduce`, `qast verify`) and deterministic release policy
  engine with default and strict policies.
- AI eval runner: deterministic checks, strict tool-call argument matching, sampling for
  nondeterminism, optional calibrated LLM judge (Cohen's kappa gating).
- Guard hook (PreToolUse/PostToolUse) active only during QA runs.
- Reference fixtures with planted defects and oracle scripts; scripted demo pipeline; behavioral
  eval harness with baseline-vs-plugin conditions.
- CI: schemas, plugin contracts, unit tests (3.11-3.13), real-tool integration tests, fixture oracles,
  sample reports; optional live behavioral evals.
- SessionStart pointer hook (about 120 tokens), added after live evals showed skipped skills and a
  secret echoed on request.
- Live behavioral eval report: `evals/reports/2026-11-23-live-sonnet.md`.

### Multi-agent support
- Installable in any Agent Skills-compatible agent with `npx skills add Yazeedx0/qa-superteam` (tested for
  claude-code, codex, cursor, gemini-cli, github-copilot and opencode project installs).
- `qast` runtime, policies and config template bundled inside the `using-qa-superteam` skill
  (`scripts/sync_skill_runtime.py`, drift-checked in CI); skills use relative paths only.
- Native manifests for Codex, Cursor (with session-start hook) and Gemini CLI; the session-start hook
  emits each host's format.

### Changed after independent review
- Every `qast verify` verdict requires independence. CONFIRMED needs the verifier's own `--actor`
  executions; conflicting verdicts degrade to INCONCLUSIVE.
- Run lifecycle: `qast run resume`, run states, and no evidence written into inactive runs.
- The guard hook protects config and policies and catches shell writes.
