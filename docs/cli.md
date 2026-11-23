# `qast` CLI reference

`qast` is the deterministic tool layer behind every QA Superteam skill. When the
plugin is enabled, Claude Code puts the plugin's `bin/` on the Bash `PATH`, so skills
call `qast` directly. Outside Claude Code: `python3 -m pip install -e .` or call
`<repo>/bin/qast`. It needs Python ≥ 3.11 and nothing else.

Run `qast <command> --help` for every flag. Global option: `--project DIR` (default `.`).
Most commands accept `--run ID` (default: the active run) and `--json`.

## Run lifecycle (checkpoints & resumption)

| Command | Purpose |
|---|---|
| `qast run start --mode <mode> --scope "<words>" [--base REF] [--head REF]` | Create `.qa-superteam/runs/<id>/`, mark it active. Modes: `full-audit review-pr test-feature test-api test-e2e security-review eval-ai explore verify-bug regression release-check improve-suite adhoc` |
| `qast run status [--json]` | Phases, records present, executions, findings with derived status. **Use this to resume an interrupted run.** |
| `qast run phase <phase> <started\|done\|skipped\|blocked> [--note "..."]` | Checkpoint a phase: `discovery requirements impact risk planning delegation execution investigation verification release reporting regression` |
| `qast run note "<text>" [--kind limitation\|assumption\|decision]` | Record a disclosure; limitations appear in the report |
| `qast run finish` | Clear the active-run marker (turns the guard hook off) |
| `qast run list` | All runs |

## Understanding the project

| Command | Output |
|---|---|
| `qast doctor [--json]` | Which tools are available (pytest, Playwright, k6, axe-core, scanners, Docker, judge credentials) and how to install missing ones |
| `qast discover [--supersede]` | `profile.json`: languages, components, test suites (with suggested `qast exec` commands), confidence-tagged facts, unknowns |
| `qast impact --base <ref> [--head <ref>] [--no-worktree]` | `impact.json`: changed files with risk signals, selected tests with reasons, changed source without related tests |
| `qast risk [--supersede]` | `risks.json`: baseline probability × impact register with documented factors |

## Recording analysis (validated JSON)

Write JSON to a file, then submit it. The CLI validates strictly and explains errors.
Print a fill-in example with `qast schema <Model> --template`.

| Command | Model |
|---|---|
| `qast record requirements --file req.json` | `RequirementSet` (requirements, invariants with oracles, ambiguities, assumptions) |
| `qast record risks --file risks.json --supersede` | `RiskRegister` (refines the baseline) |
| `qast record plan --file plan.json` | `TestPlan` (every test case needs an `oracle`) |
| `qast finding add --file finding.json` | `DefectFinding` — refused if referenced evidence/executions do not exist |
| `qast finding list [--json]` / `qast finding show <id>` | Findings with **derived** status |

## Executing real tests

```
qast exec <adapter> [--group G]... [--label L] [--timeout S] [--cwd DIR] [--python PY] [adapter flags] -- <tool args>
```

Everything after `--` is passed to the tool. Every execution records normalized results
(`PASSED FAILED ERROR SKIPPED BLOCKED NOT_RUN INCONCLUSIVE`), redacted logs and reports
as hashed evidence, and environment metadata. A missing tool yields a **BLOCKED**
execution with an install hint — never a pass and never a failure.

| Adapter | Tool | Example |
|---|---|---|
| `pytest` | pytest (project interpreter) | `qast exec pytest --group existing-suite -- tests` |
| `junit` | any command writing JUnit XML | `qast exec junit --report out/junit.xml -- go test ./... ` |
| `vitest` / `jest` | JS unit runners (JSON reporter) | `qast exec vitest --group existing-suite` |
| `playwright` | Playwright Test (Node) | `qast exec playwright --group critical-journeys -- tests/e2e` |
| `command` | exit-code only (coarse) | `qast exec command --label lint -- npm run lint` |
| `k6` | k6 | `qast exec k6 --target http://127.0.0.1:8000 [--profile smoke\|load] -- perf/script.js` |
| `axe` | axe-core via Playwright | `qast exec axe --target http://127.0.0.1:8000/ [--viewport 375x812]` |
| `ai-eval` | golden-dataset AI eval runner | `qast exec ai-eval --dataset evals/golden.jsonl --entry pkg.bot:answer [--samples 3] [--judge-model M --calibration cal.json]` |
| `bandit` `pip-audit` `npm-audit` `semgrep` `gitleaks` | security scanners | `qast exec bandit -- src` (`--via-uvx` to fetch a missing scanner; `semgrep` needs `--config`) |

Policy groups used by the default policy: `existing-suite` (mandatory), `critical-journeys`,
`contract`, `regression` (mandatory if planned), plus `security`, `accessibility`,
`performance`, `ai-eval`, `exploratory`.

Safety enforced by adapters: `k6`/`axe` targets must be in `permissions.authorized_targets`;
k6 `load` profile needs `permissions.allow_load_testing`; k6 scripts must read
`__ENV.TARGET` and contain no unauthorized hard-coded URLs; pytest runs with
`-p no:cacheprovider` so the project tree is not written.

Test code can drop screenshots, traces or HAR files into `$QAST_ARTIFACT_DIR`; they are
collected, hashed and linked to the matching result.

## Reproduction and verification

| Command | Purpose |
|---|---|
| `qast reproduce --test <id> [--times 3] [--adapter pytest] [-- <args that run only this test>]` | Re-runs one test N times (capped by `budgets.max_reproduce_attempts`), classifies `consistent` / `intermittent` / `not-reproduced` / `blocked` |
| `qast verify <finding> --verdict CONFIRMED\|REJECTED\|INCONCLUSIVE --method independent-rerun\|alternate-oracle\|code-inspection\|manual --verifier <name> --rationale "..." [--execution ID]... [--evidence ID]... [--test ID]...` | Records a verdict **only if machine checks pass**. CONFIRMED requires: verifier ≠ reporter, execution-based method, a FAILED result in an execution the verifier ran, intact evidence, and no intermittent reproduction. Otherwise exit code 3 with the failed checks |

Finding status is derived, never edited: `SUSPECTED → REPRODUCED → CONFIRMED`, or
`NOT_REPRODUCED`, `INCONCLUSIVE`, `REJECTED`.

## Release decision and reporting

| Command | Purpose |
|---|---|
| `qast gate [--policy FILE] [--exit-code]` | Deterministic `PASS` / `REVIEW_REQUIRED` / `BLOCK` with per-rule reasons (`--exit-code`: 0 / 10 / 20 for CI) |
| `qast report [--print]` | `report.md` + `report.json` generated only from records |
| `qast validate` | Re-validate every record against its schema and every artifact against its sha256 |

## Utilities

| Command | Purpose |
|---|---|
| `qast init [--force]` | Write `.qa-superteam/config.toml` with read-only defaults |
| `qast schema [Model] [--template]` | JSON Schema or fill-in example |
| `qast redact [FILE]` | Redact secrets/PII from text (stdin by default) |
| `qast ai-eval validate <dataset.jsonl>` | Check an eval dataset |
| `qast ai-eval calibrate --judgments j.jsonl --labels human.jsonl [--out cal.json]` | Judge vs human agreement and Cohen's kappa |

## Exit codes

`0` success · `1` error/invalid input · `3` refused by an evidence gate (`finding add`,
`verify`) · `gate --exit-code`: `0` PASS, `10` REVIEW_REQUIRED, `20` BLOCK.
`qast exec` exits 0 whenever the execution was recorded — read the printed status.
