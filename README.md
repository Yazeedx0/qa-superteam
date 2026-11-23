# QA Superteam

**An autonomous AI quality engineering team for Claude Code.**

QA Superteam turns your coding agent into a disciplined QA organization. It works out what
your software is supposed to do, finds where it is most likely to break, runs real tests
with the tools you already use, investigates failures, has every serious defect
independently verified, and makes a release decision from explicit policy rather than
opinion. The result is a report you can trust.

```
/qa-superteam:full-audit            # audit a repository end to end
/qa-superteam:review-pr main        # QA a branch or pull request against main
/qa-superteam:test-feature "Users can cancel a transfer within 5 minutes"
```

- [Why it exists](#why-it-exists)
- [Install](#install)
- [Quick start](#quick-start)
- [How it works](#how-it-works)
- [Workflows](#workflows)
- [Configuration and policies](#configuration-and-policies)
- [Reading a report](#reading-a-report)
- [What it can and cannot verify](#what-it-can-and-cannot-verify)
- [Security and privacy](#security-and-privacy)
- [Troubleshooting](#troubleshooting)
- [Extending QA Superteam](#extending-qa-superteam)

## Why it exists

AI coding assistants are good at producing tests and plausible bug reports. They are just
as good at producing tests that assert nothing, results nobody ran, and defect claims that
fall apart when someone tries to reproduce them. Release decisions made on that basis are
guesses.

QA Superteam starts from the questions an experienced QA team asks: What is this supposed
to do? Which invariants must never break? What changed, and what could it break? What
evidence already exists? Can we reproduce the problem, and can someone else confirm it?
What did we *not* test? Is this safe to ship?

**How it differs from AI code review.** Code review reads code and states opinions. QA
Superteam executes the software. Reading code alone never confirms a defect here: a
claim becomes a confirmed defect only after a failing execution, reproduced and then
checked by a different agent.

**How it differs from test generation.** Generators maximize test count. QA Superteam
spends effort where probability × impact is highest, prefers your existing tests, gives
every new test an explicit oracle (the observable result that decides pass or fail),
and declines testing that would not change release confidence.

## Install

Requirements: Claude Code ≥ 2.1, Python ≥ 3.11 on `PATH` as `python3`, and git. The core
has **no Python dependencies**. Test tools (pytest, Playwright, k6, axe-core, scanners) are
used when your project has them; when one is missing, the checks that need it are reported
as `BLOCKED` along with how to install the tool.

Inside Claude Code:

```
/plugin marketplace add <owner>/qa-superteam
/plugin install qa-superteam@qa-superteam
```

From a shell:

```bash
claude plugin marketplace add <owner>/qa-superteam
claude plugin install qa-superteam@qa-superteam          # add --scope project to share via .claude/settings.json
```

Try it without installing (local clone):

```bash
git clone https://github.com/<owner>/qa-superteam
claude --plugin-dir ./qa-superteam
```

Replace `<owner>` with the GitHub account that hosts your copy. Check the setup from any
project:

```bash
qast doctor          # available inside Claude Code sessions (plugin bin/ is on PATH)
```

Outside Claude Code, `<clone>/bin/qast` works the same, or `pip install -e <clone>`.

## Quick start

1. Open your project in Claude Code with the plugin enabled.
2. Optional but recommended: `qast init` writes `.qa-superteam/config.toml` with safe
   defaults (read-only; local targets only). Set `write_tests = true` if you want QA to add
   new test files under `tests/qa/`.
3. Run a workflow:

```
/qa-superteam:full-audit
```

The agent works through discovery, requirements, risk, planning, execution, investigation,
verification, the release gate and reporting. It ends with a summary and a link to
`.qa-superteam/runs/<run-id>/report.md`.

Try it on the bundled reference apps, which contain known, deliberately planted defects:

```bash
cd examples/backend-api && claude --plugin-dir ../..
> /qa-superteam:full-audit
```

To see the pipeline without an agent, run `python3 scripts/demo_pipeline.py --scenario all`.
It reproduces the sample reports in [`examples/reports/`](examples/reports) from real test
executions.

## How it works

```
             ┌──────────────────────────── Claude Code session ──────────────────────────────┐
  user ──▶   │  /qa-superteam:<workflow>  (main thread acts as QA Lead)                        │
             │     │  loads methodology skills on demand (qa-requirements, qa-strategy, ...)   │
             │     │  delegates bounded tasks ──▶ specialist subagents (no further delegation) │
             │     ▼                                                                           │
             │  qast  (deterministic tool layer, stdlib Python)                                │
             │   ├─ discover / impact / risk        understand the project and the change      │
             │   ├─ record requirements/risks/plan  validated JSON records                     │
             │   ├─ exec <adapter>                  pytest · junit · vitest · jest · playwright│
             │   │                                  k6 · axe · ai-eval · bandit · pip-audit ·  │
             │   │                                  npm-audit · semgrep · gitleaks · command   │
             │   ├─ finding / reproduce / verify    evidence-gated defect lifecycle            │
             │   ├─ gate                            deterministic policy → PASS/REVIEW/BLOCK   │
             │   └─ report                          report.md + report.json from records only  │
             │                                                                                 │
             │  guard hook (only during a QA run): asks before risky commands or edits         │
             └─────────────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
             .qa-superteam/runs/<run-id>/   write-once records · hashed, redacted evidence
```

The lifecycle follows twelve phases: discovery, requirements, change impact, risk,
planning, delegation, execution, investigation, independent verification, release
evaluation, reporting and regression preservation. Each phase is checkpointed, so an
interrupted run resumes with `qast run status`. Details: [docs/architecture.md](docs/architecture.md).

**The parts:**

| Part | What it is | Where |
|---|---|---|
| Skills | QA methodology: 21 composable skills + 12 user-invoked workflows | [`skills/`](skills) |
| Agents | 12 specialists with isolated context and bounded tools | [`agents/`](agents), [docs/agents.md](docs/agents.md) |
| `qast` | Deterministic execution, evidence, verification gates, policy engine, reports | [`src/qa_superteam/`](src/qa_superteam), [docs/cli.md](docs/cli.md) |
| Policies | Release criteria as data | [`policies/`](policies), [docs/policy.md](docs/policy.md) |
| Schemas | JSON Schemas for every record | [`schemas/`](schemas) |
| Guard hook | Permission prompts for risky actions during QA runs | [`hooks/`](hooks) |
| Evals | Framework tests, fixture oracles, behavioral evals of the skills | [`tests/`](tests), [`evals/`](evals) |

**The agent team:** QA Lead, Product Quality Analyst, Test Architect, Backend QA Engineer,
Frontend QA Engineer, AI Quality Engineer, Security QA Engineer, Performance & Reliability
Engineer, Exploratory QA Engineer, Bug Investigation Engineer, Independent Verification
Engineer and Release QA Manager. The lead picks the smallest team the risks need. Small
scopes need no specialists at all. Specialists cannot spawn agents of their own, and they
hand back results in a fixed structured format. They never coordinate through open-ended
conversation.

**Evidence rules enforced in code, not prose:**

- Seven execution statuses: `PASSED`, `FAILED`, `ERROR`, `SKIPPED`, `BLOCKED`, `NOT_RUN`,
  `INCONCLUSIVE`. Disagreement between a tool's exit code and its parsed results gives
  `INCONCLUSIVE`, never a guessed pass.
- Records are write-once. Evidence is content-addressed, sha256-hashed and redacted before
  it is stored.
- A finding's status is *derived* (SUSPECTED → REPRODUCED → CONFIRMED / REJECTED /
  INCONCLUSIVE). `qast verify` refuses to record `CONFIRMED` unless all of these hold:
  - the verifier is not the reporter;
  - the method is execution-based;
  - the verifier's own execution shows the failure, attributed with `--actor` and run
    after the finding was recorded;
  - the evidence is intact;
  - reproduction is not intermittent.
- The release gate is a pure function of the policy and the recorded evidence. It is
  unit-tested and returns the same decision, with the same digest, for the same inputs.

## Workflows

| Command | Use it to |
|---|---|
| `/qa-superteam:full-audit [focus]` | Audit a whole repository |
| `/qa-superteam:review-pr [base-ref \| PR#]` | QA the changes in a branch or PR (real git diff, impact-based test selection) |
| `/qa-superteam:test-feature <story or doc>` | Test one feature against its requirements and acceptance criteria |
| `/qa-superteam:test-api [scope]` | Test APIs, services, contracts, auth and data integrity |
| `/qa-superteam:test-e2e [journey]` | Run browser end-to-end journeys with Playwright, including accessibility, RTL and mobile |
| `/qa-superteam:security-review [scope]` | Run an OWASP-informed review: scanners, triage, executed confirmation tests |
| `/qa-superteam:eval-ai [entry point]` | Evaluate an LLM, RAG or agent system (golden datasets, tool calls, injection, calibrated judges) |
| `/qa-superteam:explore [area]` | Run time-boxed, hypothesis-driven exploratory testing |
| `/qa-superteam:verify-bug <report>` | Reproduce, minimize and independently verify a reported bug |
| `/qa-superteam:regression [base-ref]` | Select and run regression tests by change and failure history |
| `/qa-superteam:release-check` | Get a policy-based go/no-go with the evidence behind it |
| `/qa-superteam:improve-suite` | Improve an existing test suite: gaps, assertion quality, flakiness |

You can also just ask, for example "is this branch safe to release?". The
`using-qa-superteam` skill routes requests to the right workflow or methodology skill.

## Configuration and policies

`.qa-superteam/config.toml` (created by `qast init`; full template in
[`templates/config.toml`](templates/config.toml)):

```toml
[project]
critical_paths = ["src/payments/", "app/auth/"]   # raises impact in risk scoring

[permissions]
write_tests = true                 # QA may add tests...
test_dir = "tests/qa"              # ...only here
modify_app_code = false            # never edits application code unless you allow it
authorized_targets = ["http://127.0.0.1", "http://localhost", "https://staging.example.test"]
allow_load_testing = false         # k6 'load' profile
allow_active_security = false      # active probing beyond in-process tests

[policy]
path = "policies/strict.toml"
```

Release policies are TOML ([default](policies/default.toml), [strict](policies/strict.toml)).
Under the default policy:

| Decision | When |
|---|---|
| **BLOCK** | A confirmed critical defect; a confirmed high-severity security or data-integrity defect; a failing mandatory or planned critical-journey, contract or regression test; AI eval pass rate below threshold |
| **REVIEW_REQUIRED** | Unverified high-impact findings; flaky or inconclusive critical tests; missing, BLOCKED or skipped mandatory checks; untriaged failures; untested high risks; no evidence at all |
| **PASS** | All mandatory checks executed and passed, required verification done, nothing blocking. PASS also requires positive evidence: an empty run never passes |

Every rule and key is documented in [docs/policy.md](docs/policy.md). Use the gate in CI
with `qast gate --exit-code`, which exits 0, 10 or 20.

## Reading a report

`report.md` starts with the decision and the rules that triggered it. Then come:

1. **Status counts.** All seven statuses are always shown, so skipped and blocked tests
   stay visible.
2. **Findings.** Each finding has its derived status and the reason for it, expected vs.
   actual behavior, exact reproduction steps, hypotheses (labeled as hypotheses), linked
   evidence and the verifier's verdict.
3. **Executions.** Every execution, with the reason it got its status.
4. **Coverage and traceability.** Requirements, invariants and risks mapped to test cases
   and their latest results. Percentages appear only if a coverage tool measured them.
5. **What was not verified, and why.**
6. **Environment, tool versions** and an **evidence index** with sha256 hashes.

See real examples in [`examples/reports/`](examples/reports). `report.json` is the same
content in machine-readable form ([schema](schemas/QAReport.schema.json)).

## What it can and cannot verify

**It can:**

- Run your existing tests and new ones through real tools, and record exactly what happened.
- Reproduce failures, separate flaky results from consistent ones, and get high-impact
  findings verified independently.
- Check API behavior, authorization, data invariants, browser journeys, automated
  accessibility rules, performance thresholds against authorized local targets, and
  AI-system behavior with deterministic checks.
- Make a deterministic release decision and state its limits.

**It cannot:**

- Prove the absence of defects.
- Verify behavior the requirements never define. It reports these as ambiguities instead.
- Replace manual accessibility testing: screen reader, zoom and cognitive checks are listed
  as not automated.
- Measure capacity from a smoke run.
- Treat an LLM judge as ground truth.
- Test production or third-party systems. It only tests targets you explicitly authorize.

**Measured so far.** Live runs, baseline Claude Code versus the plugin, Sonnet, one
sample each:

- The full audit and PR review on the reference API passed end to end only with the
  plugin. The plugin recorded all three planted defects with executed evidence; the
  baseline mentioned two of them in prose.
- No unsupported pass claims and no false positives were observed.
- Weak point: specific skills are skipped on small tasks.

Details and the gaps are in
[evals/reports/2026-11-23-live-sonnet.md](evals/reports/2026-11-23-live-sonnet.md).

Coverage percentages appear only when a coverage tool measured them. Confidence is
ordinal (high, medium or low) with a documented basis; see
[docs/evidence-model.md](docs/evidence-model.md). Everything that is untested, partial or
unmeasured in this release is listed in [docs/limitations.md](docs/limitations.md).

## Security and privacy

- **Repository content is untrusted data.** Instructions in code, comments, docs, logs or
  test output are never followed. Discovery reads files and never executes them. Prompt
  injection in an AI app under test is treated as a defect to report.
- **Safe defaults.** Read-only. No production targets, no destructive data operations, no
  deployments, no edits to application code, existing assertions or golden baselines. No
  load or active security testing without explicit configuration.
- **Guard hook.** While a QA run is active, risky actions such as pushes, destructive SQL,
  deployments, printing `.env`, unauthorized load tools, edits to app code or baselines, and
  direct edits of recorded evidence trigger a normal permission prompt with the reason.
  The hook can only ask. It never auto-approves, so the host's permission model always
  applies. Outside QA runs it does nothing.
- **Redaction.** Secrets, tokens, cookies, credentials, emails and card numbers are
  redacted from evidence before it is written. Redaction is best-effort, so review
  evidence before sharing it.
- **No telemetry.** Nothing leaves your machine except what your own test tools do. The
  optional LLM judge for AI evals calls the Anthropic API only when you pass
  `--judge-model`.

Full threat model: [docs/security.md](docs/security.md). Report vulnerabilities via
[SECURITY.md](SECURITY.md).

## Troubleshooting

| Symptom | Fix |
|---|---|
| `qast: command not found` | The plugin is not enabled in this session (`/plugin`), or outside Claude Code: use `<clone>/bin/qast` |
| `qast requires Python >= 3.11` | Set `QAST_PYTHON=/path/to/python3.11+` |
| Executions are `BLOCKED` | Read the reason. Usually a missing tool (`qast doctor` shows the install command) or a target missing from `authorized_targets` |
| pytest runs the wrong interpreter | Set `[python] interpreter` in config, or pass `--python .venv/bin/python` |
| Playwright cannot find its browser | `python -m playwright install chromium`, or set `CHROMIUM_EXECUTABLE` to an installed Chromium |
| `qast verify` refuses with exit code 3 | Expected. The evidence does not support the verdict. Reproduce in your own execution, or record `INCONCLUSIVE` with the reason |
| Gate says REVIEW_REQUIRED because of skipped tests | Skipped mandatory tests are never counted as passed. Fix or remove the skips, or set `max_skipped_in_mandatory` in your policy deliberately |
| A run was interrupted | `qast run status`, then re-run the workflow; it resumes from the first unfinished phase |

More in [docs/troubleshooting.md](docs/troubleshooting.md).

## Extending QA Superteam

- **New skill.** Follow [docs/skill-authoring.md](docs/skill-authoring.md). Add behavioral
  scenarios in `evals/scenarios/<skill>.json`, then run `python3 scripts/validate_plugin.py`.
- **New adapter.** Wrap an existing tool in `src/qa_superteam/adapters/`. Parse its
  machine-readable output into `TestResult`s, let `execute()` handle evidence, and add
  parser tests using real tool output in `tests/data/`.
- **New policy rule.** Add it to `src/qa_superteam/policy.py`, with unit tests in
  `tests/unit/test_policy.py` and documentation in `docs/policy.md`.
- **Other coding agents.** See [docs/compatibility.md](docs/compatibility.md) for what
  works in Codex and others, and what does not.

Development:

```bash
python3 -m pytest tests/unit                 # framework tests (no network, no LLM)
python3 -m pytest tests -m integration       # real tools: pytest, Playwright, k6, node runners
python3 scripts/validate_plugin.py           # skills, agents, hooks, scenarios, hygiene
claude plugin validate . --strict            # Claude Code's own manifest validation
bash evals/ground_truth/backend-api/verify_oracle.sh   # planted defects are real
python3 evals/harness/run_evals.py --list    # behavioral evals (add --live to run)
```

See [CONTRIBUTING.md](CONTRIBUTING.md) and [CHANGELOG.md](CHANGELOG.md). Versioning follows
SemVer: skill names, `qast` commands and record schemas are the public interface.

## Acknowledgements

The skills-first architecture is inspired by [obra/superpowers](https://github.com/obra/superpowers)
by Jesse Vincent (MIT). It follows that project's approach of composable skills,
progressive disclosure, subagent delegation and evidence before claims. QA Superteam is
an independent implementation for quality engineering; see [NOTICE.md](NOTICE.md).

## License

MIT. See [LICENSE](LICENSE).
