---
name: qa-test-design
description: Use when designing new test cases - applies equivalence, boundary, decision-table, state-transition, pairwise, property-based, negative and metamorphic techniques, gives every case an observable oracle, and avoids duplicating existing tests.
---

# QA test design

> `qast` is on PATH in Claude Code. In other agents, run `../using-qa-superteam/scripts/qast` (path relative to this file) wherever this skill says `qast`.

## Purpose

Design the smallest set of test cases that would detect the defects the risk register
worries about. Every case names its technique, its oracle (the observable expected
outcome, derived from a source, never from the implementation) and its trace to
requirements, invariants and risks.

## Use when / Do not use when

Use when:
- Phase E, or designing tests for a feature, ticket, invariant or confirmed defect.
- Reviewing existing or proposed tests for oracle quality.

Do not use when:
- No requirements or risks exist yet: run `qa-requirements` / `qa-strategy` first, or design only for what the user stated and record the rest as assumptions.
- The cases are designed and need implementing in a framework: level skills (`qa-unit`, `qa-backend`, `qa-frontend`, `qa-contracts`).
- Behaviour is unknown and needs exploring before it can be specified: `qa-exploratory`.

## Inputs & assumptions

- `requirements.json` (acceptance criteria, invariants), `risks.json` (levels, owners), `profile.json` (suites, frameworks).
- `permissions.write_tests` and `permissions.test_dir` decide `origin` (`new` vs `proposed`).
- `qast doctor` tells whether Hypothesis, fast-check runners, Playwright or axe can run here.

## Tools

| Command | Use |
|---|---|
| `qast schema TestPlan --template`, `qast schema TestCase` | JSON shape; allowed `level` and `technique` values |
| `qast record plan --file <run dir>/drafts/plan.json [--supersede]` | validates; refuses any case without an oracle |
| `qast doctor` | if a property-based library is missing, still design the property; mark the case `proposed` and add the example inputs that can run today |
| Read / Grep over test directories | deduplication against existing tests |

## Method

1. **Pick targets in risk order:** critical/high risks and critical invariants first; medium only for changed behaviour; low stays with the existing suite.
2. **Inventory existing tests** per target: id, what it asserts, inputs, level. An existing test covers a case only if its assertion would fail when the requirement is violated. Executing code without asserting the outcome is not coverage.
3. **Choose techniques by the shape of the behaviour** (worked examples: [references/techniques-worked-examples.md](references/techniques-worked-examples.md)):

   | Shape of the behaviour | `technique` |
   |---|---|
   | input with ranges or classes | `equivalence` + `boundary` |
   | several conditions decide one outcome | `decision-table` |
   | lifecycle, status, multi-step flow | `state-transition` |
   | many independent parameters (country × payment × locale × device) | `pairwise`; all combinations only for critical pairs |
   | a rule that must hold for all inputs (arithmetic, parsing, round-trips) | `property` |
   | invalid, unauthorized, wrong-state, duplicate or malformed input | `negative` |
   | no exact expected output (search, ranking, ML, rendering) | `metamorphic` |
   | business rule across operations | `invariant`, checked after every step of a sequence |
   | confirmed defect | `regression`: exact failing input plus neighbours |
   | is this build usable at all | `smoke` |

4. **Write the oracle before the steps:** exact status, exact value, persisted state, message, and what must not change. Expected values come from the requirement, computed by hand or by an independent model written from the spec; never by calling or copying the code under test. Oracle types and anti-patterns: [references/oracles.md](references/oracles.md).
5. **Boundaries:** for each limit min−1, min, min+1, max−1, max, max+1, plus zero, negative, non-integer, empty, maximum length and unicode where the type allows. For rounding, values on both sides of each rounding step, including an exact half.
6. **Negative partner:** every positive case on a critical/high target has at least one negative case (invalid, unauthorized, another user's resource, wrong state, duplicate).
7. **Deduplicate.** Same requirement + same partition + same oracle as an existing test: reference that test (`origin: "existing"`, node id in `test_ref`) instead of adding one. Several values from one partition are one case with several `inputs`.
8. **Origin, reference, groups:**
   - `existing`: `test_ref` = node id; group `existing-suite`, plus `critical-journeys` or `contract` if it is one.
   - `new`: only when `write_tests = true`; `test_ref` = the planned node id under `permissions.test_dir`.
   - `proposed`: `test_ref` null; steps, inputs and oracle complete enough to implement without guessing.
   - `critical-journeys`, `contract` and `regression` are mandatory-if-planned under the default policy: each such case must execute and pass for PASS. Tag honestly; never drop a group or a priority to avoid `R-PLANNED-MANDATORY-CASES` or `R-UNTESTED-HIGH-RISK`.
9. **Trace and prioritise:** fill `requirement_ids`, `invariant_ids`, `risk_ids`; `priority` = highest linked risk level or invariant criticality. Every critical/high risk gets ≥ 1 case or an `out_of_scope` entry with a reason.
10. **Record** `<run dir>/drafts/plan.json` with `scope`, `strategy_summary` (from `qa-strategy`), `test_cases`, `out_of_scope`, `assumptions`, `entry_criteria`, `exit_criteria`, `specialists`: `qast record plan --file <run dir>/drafts/plan.json` (`--supersede` on revision), then `qast run phase planning done`.

## Stop when

- Every critical/high target has cases with oracles or an out-of-scope reason, medium targets have at most boundary + negative cases, and no case duplicates an existing test; or
- ~30 cases: beyond that delegate to `qa-superteam:test-architect` or split by subsystem.

Do not design beyond the existing suite for low risks.

## Safety

- Design does not execute anything. New test files only when `write_tests = true` and only under `test_dir`; existing tests and assertions are never edited or weakened.
- Test data is synthetic: no real customer data, production credentials or live payment identifiers.
- Cases that need unauthorized activity (load, active attacks, fault injection, non-allowlisted targets) go to `out_of_scope` with the permission that would be needed.

## Output contract

- `plan.json` via `qast record plan`: every case has `id`, `title`, `level`, `technique`, `oracle`, `origin`, `test_ref` (null when proposed), `groups`, `priority`, `inputs`/`steps`, trace ids.
- Summary:

```
PLAN <scope>: <n> cases (<e> existing, <w> new, <p> proposed); techniques: <list>
Critical/high coverage: R-xx → TC-.., TC-..; INV-x → TC-..
Reused existing tests: <node ids>
Out of scope: <item> — <reason>
Proposed, not runnable now: <TC> — <why> — <what would enable it>
```

## Quality checklist

- [ ] Every oracle names an observable value or state, and what must not change where relevant.
- [ ] No expected value came from running or copying the implementation.
- [ ] Every critical/high risk and invariant traces to ≥ 1 case or an out-of-scope reason.
- [ ] Every positive critical/high case has a negative partner.
- [ ] Boundaries cover both sides of every limit and rounding step.
- [ ] No duplicate of an existing test; reused tests carry their node ids.
- [ ] `origin` matches permissions; groups and priorities are honest.
- [ ] For each new or proposed case you can name the concrete defect that would make it fail.

## References

- [references/techniques-worked-examples.md](references/techniques-worked-examples.md): each technique applied to a fee calculation, a checkout flow, a retrieval function, an inventory invariant and a regression.
- [references/oracles.md](references/oracles.md): specified, derived, metamorphic, differential, invariant, implicit and human oracles; anti-patterns and the "would it fail?" check.
