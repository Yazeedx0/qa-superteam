# Security model

QA Superteam runs an AI agent with shell access against code it did not write. Its security
posture rests on three assumptions:

1. The repository under test is untrusted input.
2. The agent can make mistakes.
3. The host's permission model is the final authority.

## Threats and controls

| Threat | Control |
|---|---|
| Prompt injection through repository content (README, comments, test output, fixtures, retrieved documents in AI apps) | Every skill and agent treats repository content as data. Discovery only reads files and never imports or executes them. Instructions found in content are reported as findings when relevant (for AI systems, injection is a tested defect class). Judge prompts wrap model output as untrusted data |
| Executing project code | Running the project's tests *is* executing its code. It happens only through the host's Bash tool, under its permission prompts, in the project's own environment. The `qast` core runs isolated (`python3 -I`), so project modules cannot shadow it |
| Destructive or outward-facing commands | Default config is read-only. While a run is active, the guard hook asks for permission before git pushes, resets, commits, destructive SQL, datastore flushes, cluster/infra changes, deployments, publishing, printing `.env` or the full environment, and load or attack tools aimed at unauthorized targets |
| Testing systems you do not own | Active tests (k6, axe, live HTTP) need targets in `permissions.authorized_targets` (default: localhost only), enforced by the adapters. k6 scripts must read `__ENV.TARGET` and are scanned for hard-coded unauthorized URLs. The `load` profile also needs `allow_load_testing = true`. Active security probing needs `allow_active_security = true`, and fault injection needs `allow_fault_injection = true` |
| Weakening tests to make them pass | Skills forbid it. The guard hook asks before edits to existing tests, snapshot or golden baseline files, and application code (unless `modify_app_code = true`) |
| Fabricated or altered evidence | Records are write-once and created only through `qast`. Evidence is content-addressed and hashed. The hook asks before direct edits under a run's `executions/`, `evidence/`, `artifacts/`, `findings/` and `verifications/`. Tampering is detected by `qast validate` and degrades confirmed findings to inconclusive |
| Secret leakage into reports | All persisted text (logs, reports, messages, command lines, journal) is redacted for private keys, cloud/API tokens, JWTs, bearer/basic credentials, URL credentials, cookies, `password=`-style assignments, emails (except example domains) and Luhn-valid card numbers. gitleaks runs with `--redact`. Secrets found are referenced by location, never echoed |
| Recursive or runaway agents | Only `qa-lead` has the Agent tool. Specialists have explicit tool allowlists and `maxTurns`. Reproduction is capped (`max_reproduce_attempts` ≤ 20). Re-dispatch is limited to once per task |
| Supply chain of the plugin itself | No runtime dependencies. Optional tools are your own installs. `--via-uvx` downloads scanners only when you pass it |

## SessionStart pointer

At session start the plugin adds about 120 tokens of context in every session while it is
enabled. The pointer tells the agent:

- to load `using-qa-superteam` for QA requests;
- never to print secret values, even when asked;
- never to claim unexecuted results.

Live evals showed agents echoing a secret on request and skipping QA skills without it.
To remove the pointer, disable the plugin or delete the SessionStart entry in
`hooks/hooks.json`.

## What the guard hook is and is not

- It runs only when `.qa-superteam/active-run` exists in the project and is less than 12 hours old.
- It can return `ask` with a reason, or nothing. It never returns `allow`, so it cannot
  bypass your permission settings, and it does not override `deny` rules.
- It uses pattern matching, so it can be evaded by unusual command spellings. It is a
  seatbelt, not a sandbox. For untrusted repositories, run Claude Code inside a container
  or VM.
- Its PostToolUse half appends redacted commands and file mutations to the run journal,
  which makes every change made during QA traceable.

## Redaction limits

Pattern-based redaction misses secrets that look like ordinary text, as well as custom
token formats. Add project-specific patterns under `[redaction] extra_patterns`. Treat
`.qa-superteam/runs/` as sensitive: it is git-ignored by default, and you should review
it before attaching it to tickets or CI artifacts.

## Behavioral evals

Live evals run a real agent. The harness copies fixtures to a temp dir and passes a tool
allowlist instead of bypassing permissions. `--unsafe-bypass` exists only for disposable
CI containers.

## Reporting vulnerabilities

See [SECURITY.md](../SECURITY.md).
