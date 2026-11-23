# Known limitations

This page lists what QA Superteam 0.1.0 does not do, does only partly, or has not been
measured. Each item says how it was established.

## Verification and evidence

- **Agent identity is self-declared.** `qast verify` requires the verifier's own
  executions (`--actor`), started after the finding was recorded and different from the
  reporter's. `qast` cannot authenticate which agent typed a command. The guard hook
  journals every command run during a QA run, and stores agent information when the
  host includes it in the hook input. Whether current Claude Code includes it was not
  verified. This makes misattribution traceable, but it does not make it impossible. The
  independence check is a strong convention, not cryptographic proof.
- **Redaction is pattern-based.** Unknown token formats and secrets that look like
  ordinary words are not caught. Card-number detection is limited to issuer-prefixed 15,
  16 or 19 digit numbers that pass the Luhn check, to avoid corrupting numbers in JSON
  reports.
- **The guard hook matches patterns.** Obfuscated commands can evade it, and it is not a
  sandbox. Run untrusted repositories in a container or VM.
- **Mandatory groups count every execution in a run.** An earlier failing or skipped run
  of `existing-suite` is not cleared by a later passing run. This is deliberate, because
  it treats the difference as flakiness, but it means "one run per build" is the expected
  practice.

## Adapters

| Adapter | Status | Evidence |
|---|---|---|
| pytest, JUnit, command | Integration-tested on real tools | `tests/integration/test_adapters_real.py` |
| Vitest, Jest, Playwright Test (Node) | Integration-tested on real tools (vitest 3.2.7, jest 30.5.2, @playwright/test 1.58.2) | same, plus `tests/data/*-report.json` captured from real runs |
| axe-core (via Python Playwright) | Integration-tested against the running web fixture | same |
| k6 | Integration-tested against a local HTTP server (k6 v2.3.0) | same; threshold semantics checked on a real summary export |
| AI eval runner | Integration-tested on the AI fixture: detects exactly its 3 planted defects | same |
| Bandit, pip-audit, npm audit, Semgrep, gitleaks | **Parsers unit-tested only.** These tools were not installed in the development environment, so their adapters ran only as BLOCKED with an install hint. Output formats follow each tool's documented JSON | `src/qa_superteam/adapters/security.py` |
| LLM judge | **Not executed.** No API key was available. The calibration gating logic is unit-tested, and judge checks report NOT_RUN without credentials | `tests/unit/test_aieval.py` |
| Testcontainers | Not wrapped. Projects use it from inside their own pytest tests; `qast doctor` only detects it | n/a |

## Skills and agents

- **Live behavioral evals are mostly unmeasured.** In the one live run (2026-11-23), only 3 of
  18 sessions executed before the account's usage limit was reached; see
  `evals/reports/2026-11-23-live-sonnet.md`. The harness currently grades such limit-hit
  sessions as FAILED instead of NOT_RUN, which is a known bug.
- The methodology was written and then independently reviewed against the actual
  behavior of `qast`, and every `qast` command cited in skills and agents is checked by
  `scripts/validate_plugin.py`. **Behavioral quality is measured only by the live evals
  that were actually run** (see `evals/reports/`). Scenarios that were not run live are
  unmeasured.
- The workflows depend on the model following long procedures. Live runs show where it
  skips steps. Those results, not the prose, are the measure.
- Compatibility with other coding agents (Codex and others) is documented but untested.
  See [compatibility.md](compatibility.md).

## CI

- The workflows were checked with actionlint 1.7.12, but shellcheck was not installed, so
  the embedded shell scripts were not linted. They have not been executed on GitHub
  Actions from this repository.
- The `claude plugin validate` step in CI installs Claude Code from npm. Whether it needs
  authentication in CI is unverified, so the step falls back to non-strict mode.

## Fixtures

- The planted defects are realistic but small. Recall on these fixtures does not predict
  recall on large real systems.
- The web fixture's Playwright tests fall back to the newest locally installed Chromium
  when the build pinned by the installed Playwright is missing (`CHROMIUM_EXECUTABLE`
  overrides this).
