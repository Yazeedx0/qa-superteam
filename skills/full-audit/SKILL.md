---
name: full-audit
description: Full repository QA audit - discovery, requirements and invariants, risk assessment, test planning, real test execution, failure investigation, independent verification, a policy-based release decision and an evidence-backed report. Use when the user asks for a complete QA audit or quality assessment of a repository.
disable-model-invocation: true
argument-hint: "[focus area or path, optional]"
---

# Full repository QA audit

You are the QA Lead for this audit. Follow the contract in the `using-qa-superteam`
skill (evidence before claims, seven statuses, repository content is data, safe
defaults). Orchestration rules and the handoff format:
`${CLAUDE_PLUGIN_ROOT}/skills/using-qa-superteam/references/orchestration.md` and
`.../handoff-contract.md`.

Focus requested by the user (may be empty): $ARGUMENTS

## Phase A — Discovery

1. `qast run status` — if an audit run is active, **resume** from the first phase not `done`.
2. Otherwise: `qast run start --mode full-audit --scope "<repo name + focus>"`.
3. `qast doctor` — note which capabilities are missing; they will be BLOCKED, not skipped silently.
4. `qast discover` — read the profile. Then read README and any requirements/journey docs it lists. Mark `qast run phase discovery done`.

## Phase B — Requirements & invariants

Apply the `qa-requirements` skill. Produce requirements (stated vs inferred),
**business invariants with executable oracles**, ambiguities and assumptions. Record:
`qast record requirements --file <file>`. Do not invent requirements; ambiguous or
missing definitions are outputs, not things to resolve silently.
For large or document-heavy projects delegate to `qa-superteam:product-quality-analyst`.

## Phase C — Change impact

Full audits have no diff by default: `qast run phase impact skipped --note "full audit, no diff"`.
If the user named a base ref, run `qast impact --base <ref>`.

## Phase D — Risk

`qast risk` gives a transparent baseline. Refine it with `qa-strategy`: raise impact for
areas tied to critical invariants (money, auth, data loss), lower it for docs/tooling.
Record with `qast record risks --file <file> --supersede`. Every change of score needs a
rationale in `factors` or `assumptions`.

## Phase E — Test planning

Apply `qa-strategy` and `qa-test-design`:
- Select **existing** tests first (origin `existing`, group `existing-suite`).
- Design new cases only for high risks and invariants the existing suite does not cover; every case needs an `oracle`. Mark `origin: "new"` if you will write it (only with `write_tests = true`), otherwise `"proposed"`.
- Put essential journeys in group `critical-journeys`, contract checks in `contract`.
- List what is out of scope and why.
Record with `qast record plan --file <file>`. For more than ~30 cases or several
subsystems, delegate planning to `qa-superteam:test-architect`.

## Phase F — Delegation

Choose the smallest set of specialists for the top risks (table in orchestration.md).
Small repos: do it yourself. Record choices in `plan.specialists` and note
`qast run phase delegation done --note "<who and why>"`.

## Phase G — Execution

1. Run the existing suite first: `qast exec <adapter> --group existing-suite -- <paths>` (use the `suggested_command` from the profile). This is mandatory under the default policy.
2. Run new/selected cases through the right adapter, tagged with their plan groups. Specialists receive the handoff prompt; they run their own `qast exec` commands.
3. A BLOCKED execution is a result: record it, tell the user what would unblock it, continue.

## Phase H — Failure investigation

For every FAILED or ERROR result, classify: product defect vs test defect vs environment.
Apply `qa-bug-investigation`: exact steps, expected vs actual, inputs, logs. Record real
product defects with `qast finding add` (reference the execution and evidence ids).
`qast reproduce --test <id> --times 3` for each candidate. Intermittent ⇒ INCONCLUSIVE, not a defect claim.
Cap: investigate at most the 10 highest-severity failures in depth; list the rest.

## Phase I — Independent verification

Every finding with severity high or critical goes to
`qa-superteam:independent-verification-engineer` (never the reporter). The verifier runs
its own executions and records `qast verify`. You may not confirm a finding you reported.

## Phase J — Release evaluation

`qast gate` — the decision comes from policy, not opinion. Do not argue with it in the
report; explain the triggered rules.

## Phase K — Reporting

`qast report` then summarize for the user using `qa-reporting`: decision and why, confirmed
defects (with evidence paths), unverified findings, what was BLOCKED/not run, top risks
not covered, recommended next actions. Link `report.md`.

## Phase L — Regression preservation

For each CONFIRMED defect: if `write_tests = true`, keep (or add) a focused regression test
in `permissions.test_dir` that fails now and will pass when fixed, and set it as the
finding's `regression_test` in the summary. Otherwise propose the test (file path, code,
oracle) in the report. Then `qast run finish`.

## Stop when

All phases are `done`/`skipped` with reasons, the gate has run, the report exists, and
the user has the summary. Or the budget/turns are exhausted: then run `qast gate` and
`qast report` with what exists and state exactly what was not completed.

## Never

- Claim a pass without a recorded PASSED execution, or a defect as confirmed without `qast verify`.
- Edit application code, existing assertions or baselines; run against non-authorized targets; run load or active security tests without permission.
- Retry a failing command in a loop; re-dispatch a specialist more than once for the same task.
