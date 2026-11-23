# QA Report — backend-api (review-pr)

Run `20261123-142751-review-pr-0389` · scope: PR: refactor transfer funds check · generated 2026-11-23T14:27:57Z
Diff: `main` → `working tree`

## ⛔ Release decision: **BLOCK**

Policy `default` v1.0.0 (sha256 `f6b8fcb3544b`) · evaluated 2026-11-23T14:27:57Z · inputs digest `7525940bbd91`

| Rule | Outcome | Reason |
|---|---|---|
| `R-CONFIRMED-BLOCKING` | BLOCK | F-0a2853f7 [critical data-integrity] PR lets the fee overdraw a wallet (regression) |
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

### F-0a2853f7 · PR lets the fee overdraw a wallet (regression)

**CONFIRMED** · severity **critical** · data-integrity · reported by qa-superteam:backend-qa-engineer

_Status basis:_ independently verified by qa-superteam:independent-verification-engineer (independent-rerun) in V-b82465cc

- **Expected:** 422 when amount + fee > balance; balance unchanged
- **Actual:** Transfer succeeds; balance becomes negative
- **Location:** `ledger/transfers.py (create_transfer)`
- **Tests:** `tests/qa/test_qa_invariants.py::test_transfer_of_entire_balance_rejected_when_fee_not_covered`, `tests/qa/test_qa_invariants.py::test_balance_never_negative_when_fee_exceeds_remaining_funds`
- **Reproduction steps:**
  1. Checkout pr/refactor-funds-check
  2. Deposit 1000
  3. Transfer 1000 (fee 10)
  4. Balance is -10
- **Evidence:** [`ev-6511faaaaa73`](artifacts/ev-6511faaaaa73-pytest-output.log), [`ev-10ba54b75826`](artifacts/ev-10ba54b75826-pytest-report.jsonl)
- **Verification V-b82465cc:** CONFIRMED by qa-superteam:independent-verification-engineer via independent-rerun — Independent rerun on the PR head; consistent 3/3 failure, and the same test passes on main.

## Test executions

| Execution | Adapter | Label / groups | Status | P/F/E/S/B/NR/I | Duration | Note |
|---|---|---|---|---|---|---|
| `ex-82ebc9264c73` | pytest | existing suite [existing-suite] | **PASSED** | 13/0/0/1/0/0/0 | 1.0s |  |
| `ex-e27d18d18c61` | pytest | changed-behaviour tests [regression] | **FAILED** | 21/2/0/0/0/0/0 | 1.4s |  |
| `ex-cd1cf77f6cb9` | pytest | reproduce tests/qa/test_qa_invariants.py::test_transfer_of_entire_balance_rejec… | **FAILED** | 0/1/0/0/0/0/0 | 0.6s |  |
| `ex-6df3253f07b6` | pytest | reproduce tests/qa/test_qa_invariants.py::test_transfer_of_entire_balance_rejec… | **FAILED** | 0/1/0/0/0/0/0 | 0.6s |  |
| `ex-0d62955fc37a` | pytest | reproduce tests/qa/test_qa_invariants.py::test_transfer_of_entire_balance_rejec… | **FAILED** | 0/1/0/0/0/0/0 | 0.7s |  |

<details><summary>Failing, errored and inconclusive results (2)</summary>

- **FAILED** `tests/qa/test_qa_invariants.py::test_transfer_of_entire_balance_rejected_when_fee_not_covered` (ex-e27d18d18c61): client = <starlette.testclient.TestClient object at 0x75d1883f5c10> new_user = <function new_user.<locals>._new at 0x75d1883a40e0> balance_of = <function balance_of.<locals>.<lambda> at 0x75d1883a4220>      def test_transfer_of_entire_balance_rejected_when_fee_not_covered(client, new_user, balance_of):         alice = new_user(balance=1_000)         bob = new_user()              r = _transfer(cli…
- **FAILED** `tests/qa/test_qa_invariants.py::test_balance_never_negative_when_fee_exceeds_remaining_funds` (ex-e27d18d18c61): client = <starlette.testclient.TestClient object at 0x75d1883704a0> new_user = <function new_user.<locals>._new at 0x75d1883a7d80> balance_of = <function balance_of.<locals>.<lambda> at 0x75d1883a7ec0>      def test_balance_never_negative_when_fee_exceeds_remaining_funds(client, new_user, balance_of):         alice = new_user(balance=1_000)         bob = new_user()              _transfer(client, …

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
- Platform: Linux-7.0.0-43-generic-x86_64 · Python 3.12.3 · CI: False · git HEAD `8d087222b8ad` dirty=False
- Tools: pytest `pytest 9.0.2`

## Evidence index

| Artifact | Kind | Path | sha256 | Redactions |
|---|---|---|---|---|
| `ev-0c725dafc655` | report | [ev-0c725dafc655-pytest-report.jsonl](artifacts/ev-0c725dafc655-pytest-report.jsonl) | `0c725dafc655cae2` | 0 |
| `ev-10ba54b75826` | report | [ev-10ba54b75826-pytest-report.jsonl](artifacts/ev-10ba54b75826-pytest-report.jsonl) | `10ba54b75826ebbd` | 0 |
| `ev-189224a95a0c` | junit | [ev-189224a95a0c-junit.xml](artifacts/ev-189224a95a0c-junit.xml) | `189224a95a0c8925` | 0 |
| `ev-2e161871160f` | report | [ev-2e161871160f-pytest-report.jsonl](artifacts/ev-2e161871160f-pytest-report.jsonl) | `2e161871160f9d41` | 0 |
| `ev-3e77f50574ae` | junit | [ev-3e77f50574ae-junit.xml](artifacts/ev-3e77f50574ae-junit.xml) | `3e77f50574ae2feb` | 0 |
| `ev-4612dbebb0f5` | junit | [ev-4612dbebb0f5-junit.xml](artifacts/ev-4612dbebb0f5-junit.xml) | `4612dbebb0f5478f` | 0 |
| `ev-516fdce693da` | log | [ev-516fdce693da-pytest-output.log](artifacts/ev-516fdce693da-pytest-output.log) | `516fdce693da6daf` | 0 |
| `ev-5dbc6b8cf73d` | report | [ev-5dbc6b8cf73d-pytest-report.jsonl](artifacts/ev-5dbc6b8cf73d-pytest-report.jsonl) | `5dbc6b8cf73d67bd` | 0 |
| `ev-6511faaaaa73` | log | [ev-6511faaaaa73-pytest-output.log](artifacts/ev-6511faaaaa73-pytest-output.log) | `6511faaaaa733b62` | 0 |
| `ev-97501d318fcc` | log | [ev-97501d318fcc-pytest-output.log](artifacts/ev-97501d318fcc-pytest-output.log) | `97501d318fccd099` | 0 |
| `ev-a4f34cc7f9e8` | junit | [ev-a4f34cc7f9e8-junit.xml](artifacts/ev-a4f34cc7f9e8-junit.xml) | `a4f34cc7f9e8b0e4` | 0 |
| `ev-d08ce036b99b` | log | [ev-d08ce036b99b-pytest-output.log](artifacts/ev-d08ce036b99b-pytest-output.log) | `d08ce036b99b0bc7` | 0 |
| `ev-e85f0689439d` | junit | [ev-e85f0689439d-junit.xml](artifacts/ev-e85f0689439d-junit.xml) | `e85f0689439dc674` | 0 |
| `ev-f34fd7d1c3c1` | log | [ev-f34fd7d1c3c1-pytest-output.log](artifacts/ev-f34fd7d1c3c1-pytest-output.log) | `f34fd7d1c3c11b5b` | 0 |
| `ev-f926b52c812e` | report | [ev-f926b52c812e-pytest-report.jsonl](artifacts/ev-f926b52c812e-pytest-report.jsonl) | `f926b52c812e97a5` | 0 |

_Generated by QA Superteam from recorded evidence. Statuses are normalized tool results; finding statuses are derived from reproduction and verification records; the decision is computed by the deterministic policy engine._
