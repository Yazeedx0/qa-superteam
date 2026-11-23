# QA Report — backend-api (review-pr)

Run `20261123-134718-review-pr-f8e8` · scope: PR: refactor transfer funds check · generated 2026-11-23T13:47:24Z
Diff: `main` → `working tree`

## ⛔ Release decision: **BLOCK**

Policy `default` v1.0.0 (sha256 `f6b8fcb3544b`) · evaluated 2026-11-23T13:47:24Z · inputs digest `cb490e2c44f6`

| Rule | Outcome | Reason |
|---|---|---|
| `R-CONFIRMED-BLOCKING` | BLOCK | F-0aff696c [critical data-integrity] PR lets the fee overdraw a wallet (regression) |
| `R-MANDATORY-GROUP:existing-suite` | REVIEW_REQUIRED | 1 skipped/not-run test(s) in mandatory group 'existing-suite' (allowed: 0); skipped tests are not counted as passed |

<details><summary>Rules satisfied (7)</summary>

- `R-EVIDENCE-EXISTS` — 2 execution(s) recorded
- `R-EVIDENCE-INTEGRITY` — all evidence hashes verified
- `R-CONFIRMED-REVIEW` — no confirmed finding at review severity
- `R-UNVERIFIED-HIGH-IMPACT` — no unverified high-impact findings
- `R-UNTRIAGED-FAILURES` — every failure is linked to a finding
- `R-FLAKY-CRITICAL` — no flaky critical tests observed
- `R-UNTESTED-HIGH-RISK` — every high-priority planned item has an executed outcome

</details>

## Summary

| FAILED | ERROR | INCONCLUSIVE | BLOCKED | NOT_RUN | SKIPPED | PASSED |
|---|---|---|---|---|---|---|
| 2 | 0 | 0 | 0 | 0 | 1 | 34 |

Executions: 5 · Findings: 1 (CONFIRMED 1)

## Findings

### F-0aff696c · PR lets the fee overdraw a wallet (regression)

**CONFIRMED** · severity **critical** · data-integrity · reported by qa-superteam:backend-qa-engineer

_Status basis:_ independently verified by qa-superteam:independent-verification-engineer (independent-rerun) in V-e20b32e4

- **Expected:** 422 when amount + fee > balance; balance unchanged
- **Actual:** Transfer succeeds; balance becomes negative
- **Location:** `ledger/transfers.py (create_transfer)`
- **Tests:** `tests/qa/test_qa_invariants.py::test_transfer_of_entire_balance_rejected_when_fee_not_covered`, `tests/qa/test_qa_invariants.py::test_balance_never_negative_when_fee_exceeds_remaining_funds`
- **Reproduction steps:**
  1. Checkout pr/refactor-funds-check
  2. Deposit 1000
  3. Transfer 1000 (fee 10)
  4. Balance is -10
- **Evidence:** [`ev-e0193a269506`](artifacts/ev-e0193a269506-pytest-output.log), [`ev-4251e3b1953c`](artifacts/ev-4251e3b1953c-pytest-report.jsonl)
- **Verification V-e20b32e4:** CONFIRMED by qa-superteam:independent-verification-engineer via independent-rerun — Independent rerun on the PR head; consistent 3/3 failure, and the same test passes on main.

## Test executions

| Execution | Adapter | Label / groups | Status | P/F/E/S/B/NR/I | Duration | Note |
|---|---|---|---|---|---|---|
| `ex-5b9f57eae147` | pytest | existing suite [existing-suite] | **PASSED** | 13/0/0/1/0/0/0 | 1.0s |  |
| `ex-5d6d21b7ed4d` | pytest | changed-behaviour tests [regression] | **FAILED** | 21/2/0/0/0/0/0 | 1.5s |  |
| `ex-c29a777984e6` | pytest | reproduce tests/qa/test_qa_invariants.py::test_transfer_of_entire_balance_rejec… | **FAILED** | 0/1/0/0/0/0/0 | 0.7s |  |
| `ex-fecbd6d285d3` | pytest | reproduce tests/qa/test_qa_invariants.py::test_transfer_of_entire_balance_rejec… | **FAILED** | 0/1/0/0/0/0/0 | 0.6s |  |
| `ex-a718a972a316` | pytest | reproduce tests/qa/test_qa_invariants.py::test_transfer_of_entire_balance_rejec… | **FAILED** | 0/1/0/0/0/0/0 | 0.6s |  |

<details><summary>Failing, errored and inconclusive results (2)</summary>

- **FAILED** `tests/qa/test_qa_invariants.py::test_transfer_of_entire_balance_rejected_when_fee_not_covered` (ex-5d6d21b7ed4d): client = <starlette.testclient.TestClient object at 0x7baa72709b20> new_user = <function new_user.<locals>._new at 0x7baa727140e0> balance_of = <function balance_of.<locals>.<lambda> at 0x7baa72714180>      def test_transfer_of_entire_balance_rejected_when_fee_not_covered(client, new_user, balance_of):         alice = new_user(balance=1_000)         bob = new_user()              r = _transfer(cli…
- **FAILED** `tests/qa/test_qa_invariants.py::test_balance_never_negative_when_fee_exceeds_remaining_funds` (ex-5d6d21b7ed4d): client = <starlette.testclient.TestClient object at 0x7baa72703fb0> new_user = <function new_user.<locals>._new at 0x7baa72717d80> balance_of = <function balance_of.<locals>.<lambda> at 0x7baa72717ec0>      def test_balance_never_negative_when_fee_exceeds_remaining_funds(client, new_user, balance_of):         alice = new_user(balance=1_000)         bob = new_user()              _transfer(client, …

</details>

## Coverage & traceability

- No coverage percentage reported: no coverage tool output was recorded. (QA Superteam never estimates coverage.)

## Risk register

| Risk | Area | P×I | Level | Key factors |
|---|---|---|---|---|
| R-01 | ledger | 1×5=5 | low | change size: 4 lines changed across 1 file(s); related tests: related tests selected; impact signals: money movement / business-critical |

## Workflow phases

discovery: done, requirements: done, impact: done, risk: done, planning: pending, delegation: pending, execution: done, investigation: pending, verification: done, release: pending, reporting: pending, regression: pending

## Limitations & what was not verified

- Demonstration run: analysis records (requirements, plan, finding text) and the QA tests were scripted (reference tests stand in for agent-authored tests). All executions, evidence, verifications and the decision are real.
- Discovery: No CI configuration detected.
- Evidence redaction is pattern-based and best-effort; review artifacts before sharing externally.

## Scope & environment

- Project: backend-api · languages: Python (16)
- Test suites: pytest: tests (3 files)
- Platform: Linux-7.0.0-43-generic-x86_64 · Python 3.12.3 · CI: False · git HEAD `916b64eadacc` dirty=False
- Tools: pytest `pytest 9.0.2`

## Evidence index

| Artifact | Kind | Path | sha256 | Redactions |
|---|---|---|---|---|
| `ev-282ac5213a01` | report | [ev-282ac5213a01-pytest-report.jsonl](artifacts/ev-282ac5213a01-pytest-report.jsonl) | `282ac5213a01bf20` | 0 |
| `ev-336326f2245b` | junit | [ev-336326f2245b-junit.xml](artifacts/ev-336326f2245b-junit.xml) | `336326f2245b69a6` | 0 |
| `ev-4251e3b1953c` | report | [ev-4251e3b1953c-pytest-report.jsonl](artifacts/ev-4251e3b1953c-pytest-report.jsonl) | `4251e3b1953cb574` | 0 |
| `ev-42ccfd72059e` | report | [ev-42ccfd72059e-pytest-report.jsonl](artifacts/ev-42ccfd72059e-pytest-report.jsonl) | `42ccfd72059e170d` | 0 |
| `ev-57dfdad201a5` | junit | [ev-57dfdad201a5-junit.xml](artifacts/ev-57dfdad201a5-junit.xml) | `57dfdad201a5b138` | 0 |
| `ev-77e95655ce93` | log | [ev-77e95655ce93-pytest-output.log](artifacts/ev-77e95655ce93-pytest-output.log) | `77e95655ce931912` | 0 |
| `ev-7d914ea16613` | report | [ev-7d914ea16613-pytest-report.jsonl](artifacts/ev-7d914ea16613-pytest-report.jsonl) | `7d914ea166139bb2` | 0 |
| `ev-7e82f1b19b5f` | junit | [ev-7e82f1b19b5f-junit.xml](artifacts/ev-7e82f1b19b5f-junit.xml) | `7e82f1b19b5f1915` | 0 |
| `ev-85a151174c7f` | log | [ev-85a151174c7f-pytest-output.log](artifacts/ev-85a151174c7f-pytest-output.log) | `85a151174c7f1e71` | 0 |
| `ev-9fd8c41f593a` | junit | [ev-9fd8c41f593a-junit.xml](artifacts/ev-9fd8c41f593a-junit.xml) | `9fd8c41f593a7431` | 0 |
| `ev-bfd851ce0571` | log | [ev-bfd851ce0571-pytest-output.log](artifacts/ev-bfd851ce0571-pytest-output.log) | `bfd851ce0571dcb5` | 0 |
| `ev-d1c538b207bb` | junit | [ev-d1c538b207bb-junit.xml](artifacts/ev-d1c538b207bb-junit.xml) | `d1c538b207bbf73f` | 0 |
| `ev-da323691d645` | report | [ev-da323691d645-pytest-report.jsonl](artifacts/ev-da323691d645-pytest-report.jsonl) | `da323691d6459028` | 0 |
| `ev-e0193a269506` | log | [ev-e0193a269506-pytest-output.log](artifacts/ev-e0193a269506-pytest-output.log) | `e0193a2695064865` | 0 |
| `ev-fbce58e71906` | log | [ev-fbce58e71906-pytest-output.log](artifacts/ev-fbce58e71906-pytest-output.log) | `fbce58e719062b3e` | 0 |

_Generated by QA Superteam from recorded evidence. Statuses are normalized tool results; finding statuses are derived from reproduction and verification records; the decision is computed by the deterministic policy engine._
