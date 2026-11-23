# Architecture

QA Superteam is **skills-first and agent-orchestrated**, with a small deterministic core.
There is no server, database or dashboard: the plugin, the CLI and the files of a run are
everything.

```
┌───────────────────────────────────────────────────────────────────────────────┐
│ Methodology (Markdown, loaded on demand)                                      │
│   skills/using-qa-superteam      contract + router (always the entry point)  │
│   skills/<workflow>              12 user-invoked workflows (/qa-superteam:*)   │
│   skills/qa-<discipline>         21 composable methodology skills             │
│   agents/<specialist>.md         12 bounded specialists                        │
├───────────────────────────────────────────────────────────────────────────────┤
│ Deterministic core (stdlib Python ≥ 3.11)  — bin/qast → src/qa_superteam       │
│   discovery.py   impact.py (diff, test selection, baseline risk)               │
│   adapters/      real tools → normalized TestResults + evidence               │
│   store.py       write-once run records, content-addressed evidence           │
│   findings.py    derived finding status, reproduction, verification gates     │
│   policy.py      release gate (pure function)                                  │
│   report.py      report.md / report.json from records only                    │
│   redact.py      secret/PII redaction on everything persisted                  │
│   aieval.py      AI-eval checks, sampling, judge calibration                   │
├───────────────────────────────────────────────────────────────────────────────┤
│ Execution tools (yours, not ours): pytest, Playwright, Vitest/Jest, k6,       │
│ axe-core, Bandit, pip-audit, npm audit, Semgrep, gitleaks, project commands    │
└───────────────────────────────────────────────────────────────────────────────┘
```

## Why this split

- **Skills** carry judgment: what to test, how to design oracles, how to triage. They are
  plain Markdown with `references/` for depth, loaded only when relevant (progressive
  disclosure), and portable to other agents that read Agent Skills.
- **Agents** exist only where an isolated context helps: a large investigation, parallel
  work on independent areas, and above all *independent verification* (a different
  context from the one that reported the defect).
- **`qast`** does everything that must be reliable: running tools, normalizing results,
  hashing evidence, enforcing verification gates, computing the decision. An agent cannot
  "decide" a test passed; it can only read what `qast` recorded.
- **Policies** are data, so release criteria are reviewed like code and the gate is
  reproducible.

## Lifecycle of a run

| Phase | Output record | Command |
|---|---|---|
| A Discovery | `profile.json` | `qast doctor`, `qast discover` |
| B Requirements & behaviour | `requirements.json` | `qast record requirements` |
| C Change impact | `impact.json` | `qast impact --base <ref>` |
| D Risk | `risks.json` | `qast risk`, refined via `qast record risks --supersede` |
| E Planning | `plan.json` | `qast record plan` |
| F Delegation | `plan.specialists`, journal | `qast run phase delegation done --note` |
| G Execution | `executions/*.json`, `evidence/*`, `artifacts/*` | `qast exec <adapter>` |
| H Investigation | `findings/*.json`, reproduction executions | `qast finding add`, `qast reproduce` |
| I Verification | `verifications/*.json` | `qast verify` |
| J Release | `decision.json` | `qast gate` |
| K Reporting | `report.md`, `report.json` | `qast report` |
| L Regression | regression tests (if allowed) or proposals | `qast exec` (red now) |

Every phase is checkpointed in `journal.jsonl` (`qast run phase ...`). `qast run status`
reconstructs progress after an interruption, so workflows resume instead of restarting.

## Run directory

```
.qa-superteam/
  config.toml                  project configuration (commit this)
  active-run                   marker: enables the guard hook while a run is in progress
  runs/<run-id>/               (git-ignored)
    run.json                   mode, scope, refs, environment
    journal.jsonl              append-only: phases, notes, commands, file mutations
    profile.json impact.json requirements.json risks.json plan.json
    executions/ex-*.json       write-once TestExecution records
    evidence/ev-*.json         EvidenceArtifact (sha256, size, redactions)
    artifacts/ev-*-<name>      redacted logs, reports, screenshots, traces
    findings/F-*.json          write-once DefectFinding
    verifications/V-*.json     write-once VerificationResult (with machine checks)
    decision.json              ReleaseDecision (rules, policy sha256, inputs digest)
    report.md report.json      QAReport
    history/                   superseded singletons (plan.v1.json, ...)
```

## Identifiers

- Result ids `tr-<sha256(adapter, identifier)[:12]>` are deterministic across runs, so
  the same test can be compared between runs.
- Evidence ids `ev-<sha256(content)[:12]>` are content-addressed: identical evidence is
  stored once, and tampering is detectable.
- Execution ids are derived from run, sequence, adapter, label and process, so they stay
  unique under parallel specialists.
- Finding ids derive from title, affected paths and tests, so recording the same finding
  twice is rejected as a duplicate.

## Concurrency

Specialists may run in parallel. The run store is safe for that: records are created with
`O_EXCL`, evidence is content-addressed with race-tolerant writes, and nothing is updated
in place (finding status is derived). Parallelism rules for *what* may run concurrently
(ports, shared test files) are in `skills/using-qa-superteam/references/orchestration.md`.

## Repository layout and rationale

| Path | Why it exists |
|---|---|
| `.claude-plugin/` | Plugin manifest and a single-plugin marketplace so `/plugin install` works from the repo |
| `skills/`, `agents/`, `hooks/`, `bin/` | Claude Code plugin components (auto-discovered); `bin/qast` lands on the Bash `PATH` |
| `src/qa_superteam/` | The core; adapters live inside the package (`adapters/`) because they share its types and evidence pipeline — a top-level `adapters/` would need import-path hacks |
| `schemas/` | Generated JSON Schemas (CI checks they match the models) |
| `policies/`, `templates/` | Release policies and the config template, as data |
| `scripts/` | Schema generation, plugin validation, the demo pipeline |
| `tests/` | Framework tests: `unit/` (no tools needed) and `integration/` (real tools) |
| `evals/` | Ground-truth oracles for the fixtures and the behavioral eval harness |
| `examples/` | Reference fixtures with planted defects, and sample reports from real runs |
| `docs/` | Everything a user or contributor needs beyond the README |
