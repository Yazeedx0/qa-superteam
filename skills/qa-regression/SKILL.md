---
name: qa-regression
description: Use when selecting or running regression tests - chooses tests from the git diff and failure history, runs the mandatory suite, compares with earlier runs, and preserves regression tests for confirmed defects.
---

# Regression testing

## Purpose

Show, with executions, that a change did not break behaviour that used to work and that
fixed defects stay fixed. Selection decides what runs *first* and what deserves extra
attention; it never replaces the mandatory existing suite. Confirmed defects leave
behind a focused regression test that fails while the defect exists and passes once it
is fixed.

## Use when / Do not use when

Use when:
- a diff, branch or PR needs a regression check (`regression` workflow, `review-pr`, Phase C/G);
- a fix for a recorded finding needs to be checked and locked in;
- results of this run must be compared with an earlier run;
- Phase L of a workflow preserves regression tests for CONFIRMED findings.

Do not use when:
- new behaviour needs test design - use `qa-test-design`;
- the goal is finding new problems - use `qa-exploratory`;
- a failure needs its cause established - use `qa-bug-investigation`; a finding needs a verdict - use `qa-verification`.

## Inputs & assumptions

- A git repository and a base ref (branch, tag or commit) for diff-based selection. No base ref -> ask, or run history- and defect-based selection only and say so.
- An active run: `qast run start --mode regression --scope "<change>" --base <ref>` (or the calling workflow's run).
- The profile (`qast discover`) for the suite's run command (`suggested_command`).
- Earlier runs in `.qa-superteam/runs/` (optional) for history and confirmed findings.
- Permissions: `write_tests`, `test_dir`. Budgets: `command_timeout_s`, `max_reproduce_attempts`.

## Tools

| Need | Command |
|---|---|
| Change-based selection | `qast impact --base <ref> [--head <ref>]` (selected tests with reasons, changed source with no related tests) |
| Earlier runs and their findings | `qast run list` · `qast finding list --run <id> --json` · `qast run status --run <id>` |
| Selected / defect regression tests | `qast exec <adapter> --group regression --label "regression/<source>" -- <test ids>` |
| Mandatory suite | `qast exec <adapter> --group existing-suite -- <suite paths>` |
| Check a "now passing" or flaky test | `qast reproduce --test <id> --times 3` |
| Plan the regression cases | `qast record plan --file <plan.json>` (cases in group `regression` with `test_ref`) |
| Disclose gaps | `qast run note "<...>" --kind limitation` |

`qast impact` needs git; without it, record the limitation and fall back to history-
and defect-based selection plus the full suite. A missing runner yields BLOCKED
executions - report them; never substitute a lighter check and call it equivalent.

## Method

1. **Select by change.** `qast impact --base <ref>`. Read every selected test's reason (changed test, name match, import reference) and the list of changed source with no related tests. Widen per [references/selection-algorithm.md](references/selection-algorithm.md): callers of changed functions, whole component for money/auth/data-model signals, full suite for dependency or configuration changes.
2. **Select by history.** List earlier runs (`qast run list`), scan their executions for FAILED/ERROR/INCONCLUSIVE results and their findings for test identifiers and regression tests (scripts in selection-algorithm.md). Keep tests that still exist; skip probes under `.qa-superteam/`.
3. **Select confirmed-defect regression tests**: the `regression_test` or `test_identifiers` of CONFIRMED findings in earlier runs, plus any test named after a finding id (`test_f_<id>_...`).
4. **Record the plan** when this run feeds a release decision: one case per selected test in group `regression` (`origin: "existing"`, `test_ref`, `oracle`, the selection reason). If the run already has a plan, add the cases to it and record with `--supersede`. Only plan tests expected to pass; a red test for a still-open defect belongs to its finding, not the plan (a failing planned `regression` case blocks the gate).
5. **Run in order of information per minute**: changed tests and defect regression tests -> impact-selected tests -> historical failures (all with `--group regression`), then the **full existing suite** with `--group existing-suite` - mandatory every time, even when everything selected passed. Tests QA added in this run (untracked files) do not belong to the existing suite: exclude them from that execution (pytest `--ignore=<file>`) and run them under `regression`.
6. **Compare with the previous comparable run** per test identifier ([references/comparing-runs.md](references/comparing-runs.md)): NEW FAILURE -> `qa-bug-investigation`; NOW PASSING -> `qast reproduce --times 3` before calling it fixed; STILL FAILING -> link the existing finding; NOT RUN NOW -> coverage lost, never a pass; UNSTABLE -> flaky handling below.
7. **Flaky tests**: show intermittency with `qast reproduce`, report counts and executions, and propose quarantine options (owner, ticket, expiry). Quarantining is a human decision: never add skip/xfail markers, deselect the test, retry until green, or drop it from the suite. A flaky failure in a mandatory group stays a failure for the gate.
8. **Preserve regression tests for CONFIRMED findings** ([references/regression-test-template.md](references/regression-test-template.md)): with `write_tests = true`, add one focused test per finding under `permissions.test_dir`, named after the finding id, asserting the *required* behaviour; run it - it must FAIL now for the defect's reason (not ERROR), and will pass after the fix. Without `write_tests`, put the full test (path, code, oracle) in the summary as a proposal.

## Stop when

- The existing suite and all selected regression tests have executed (or are BLOCKED with a reason), comparisons are done and every new failure has been handed to investigation.
- Budget: when the full suite alone exceeds the remaining budget, run it anyway and record what was not reached; never trade the mandatory suite for a subset.
- Reproduction of "now passing" or flaky tests stops at `budgets.max_reproduce_attempts`.

## Safety

- Never edit, weaken, skip, delete or deselect existing tests or assertions; never update snapshots or golden files to the current output.
- New test files only with `write_tests = true`, only under `permissions.test_dir`, never asserting the current buggy output.
- `git` is read-only here: no checkout, reset, stash, commit or push; `qast impact` reads the diff without changing the tree.
- Quarantine, test deletion and baseline updates are proposals for a human, with evidence.

## Output contract

- `impact.json` (from `qast impact`), optional plan cases in group `regression`.
- Executions: `regression` group (selected and defect tests, labelled by source), `existing-suite` group (full suite), reproductions for flaky / now-passing tests.
- Summary: selection table (test, reason: change / history / defect), result per group, comparison with the previous run (new failures, now passing - verified or not, still failing with finding ids, not run), flaky tests with counts and the quarantine proposal, regression tests added or proposed per CONFIRMED finding, changed source with no related tests. HANDOFF block when delegated.

## Quality checklist

- [ ] `qast impact` ran against the stated base ref, or its absence is recorded as a limitation
- [ ] History and confirmed-defect tests were considered, with the runs they came from
- [ ] The full existing suite ran with `--group existing-suite` (or is BLOCKED with a reason)
- [ ] Every NEW FAILURE went to investigation; every NOW PASSING was re-run before being called fixed
- [ ] No test was skipped, deselected, weakened or quarantined by QA
- [ ] Each CONFIRMED finding has a regression test that fails now for the right reason, or a concrete proposal
- [ ] Changed source with no related tests is listed as a gap

## References

- [references/selection-algorithm.md](references/selection-algorithm.md) - change, history and defect selection, widening rules, scripts
- [references/regression-test-template.md](references/regression-test-template.md) - finding-named regression test, red-now/green-after checks
- [references/comparing-runs.md](references/comparing-runs.md) - per-test status comparison between two runs
