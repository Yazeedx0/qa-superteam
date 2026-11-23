# QA Report — backend-api (full-audit)

Run `20261123-142737-full-audit-e4dc` · scope: Ledger API: full repository audit · generated 2026-11-23T14:27:51Z

## ⛔ Release decision: **BLOCK**

Policy `default` v1.0.0 (sha256 `f6b8fcb3544b`) · evaluated 2026-11-23T14:27:51Z · inputs digest `8fe9e9538bda`

| Rule | Outcome | Reason |
|---|---|---|
| `R-CONFIRMED-BLOCKING` | BLOCK | F-9718fe18 [critical security] Any logged-in user can read another user's transfer; F-767d20c2 [critical data-integrity] Fee is not included in the funds check, so balances go negative |
| `R-MANDATORY-GROUP:existing-suite` | REVIEW_REQUIRED | 1 skipped/not-run test(s) in mandatory group 'existing-suite' (allowed: 0); skipped tests are not counted as passed |
| `R-PLANNED-MANDATORY-CASES` | BLOCK | planned mandatory test cases failed: TC-AUTHZ, TC-FEE, TC-EMAIL |

<details><summary>Rules satisfied (7)</summary>

- `R-EVIDENCE-EXISTS` — 4 execution(s) recorded
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
| 6 | 0 | 0 | 0 | 0 | 1 | 49 |

Executions: 13 · Findings: 3 (CONFIRMED 2, REPRODUCED 1)

## Findings

### F-767d20c2 · Fee is not included in the funds check, so balances go negative

**CONFIRMED** · severity **critical** · data-integrity · reported by qa-superteam:backend-qa-engineer

_Status basis:_ independently verified by qa-superteam:independent-verification-engineer (independent-rerun) in V-371f24d7

- **Expected:** Transfer rejected when amount + fee exceeds the balance (REQ-BAL, INV-1)
- **Actual:** Transfer of the whole balance succeeds and leaves balance at -fee
- **Location:** `ledger/transfers.py (create_transfer)`
- **Tests:** `tests/qa/test_qa_invariants.py::test_transfer_of_entire_balance_rejected_when_fee_not_covered`, `tests/qa/test_qa_invariants.py::test_balance_never_negative_when_fee_exceeds_remaining_funds`
- **Reproduction steps:**
  1. Deposit 1000 cents
  2. Transfer 1000 cents to another user (fee 10)
  3. GET /wallets/me shows -10
- **Root-cause hypotheses** (not findings unless marked confirmed):
  - Logic in create_transfer does not enforce the stated rule — _hypothesis, medium confidence_
- **Evidence:** [`ev-9e6edd21678d`](artifacts/ev-9e6edd21678d-pytest-output.log), [`ev-e8d2b45a1c39`](artifacts/ev-e8d2b45a1c39-pytest-report.jsonl)
- **Verification V-371f24d7:** CONFIRMED by qa-superteam:independent-verification-engineer via independent-rerun — Re-ran tests/qa/test_qa_invariants.py::test_transfer_of_entire_balance_rejected_when_fee_not_covered in an independent execution; failure is consistent (3/3).

### F-9718fe18 · Any logged-in user can read another user's transfer

**CONFIRMED** · severity **critical** · security · reported by qa-superteam:backend-qa-engineer

_Status basis:_ independently verified by qa-superteam:independent-verification-engineer (independent-rerun) in V-578e93ee

- **Expected:** 404 for a user who neither sent nor received the transfer (REQ-VIS, INV-2)
- **Actual:** 200 with amount, memo and wallet ids of the other users' transfer
- **Location:** `ledger/routers/transfers.py (get_transfer)`
- **Tests:** `tests/qa/test_qa_authz.py::test_outsider_cannot_read_transfer`, `tests/qa/test_qa_authz.py::test_transfer_ids_cannot_be_enumerated`
- **Reproduction steps:**
  1. Register users A, B and C
  2. A deposits and transfers to C
  3. B requests GET /transfers/{id} of A's transfer
- **Root-cause hypotheses** (not findings unless marked confirmed):
  - Logic in get_transfer does not enforce the stated rule — _hypothesis, medium confidence_
- **Evidence:** [`ev-cc1b297e9192`](artifacts/ev-cc1b297e9192-pytest-output.log), [`ev-d4947d2d6374`](artifacts/ev-d4947d2d6374-pytest-report.jsonl)
- **Verification V-578e93ee:** CONFIRMED by qa-superteam:independent-verification-engineer via independent-rerun — Re-ran tests/qa/test_qa_authz.py::test_outsider_cannot_read_transfer in an independent execution; failure is consistent (3/3).

### F-bd4021ab · Email uniqueness is case-sensitive, allowing duplicate accounts

**REPRODUCED** · severity **medium** · data-integrity · reported by qa-superteam:backend-qa-engineer

_Status basis:_ reproduction 3/3 failing (consistent); not yet independently verified

- **Expected:** Registering Alice@example.com after alice@example.com returns 409 (REQ-EMAIL)
- **Actual:** Both registrations succeed and create separate accounts
- **Location:** `ledger/models.py (clean_email)`
- **Tests:** `tests/qa/test_qa_integrity.py::test_email_uniqueness_is_case_insensitive`, `tests/qa/test_qa_integrity.py::test_login_email_is_case_insensitive`
- **Reproduction steps:**
  1. Register alice@example.com
  2. Register Alice@example.com
  3. Observe 201 for both
- **Root-cause hypotheses** (not findings unless marked confirmed):
  - Logic in clean_email does not enforce the stated rule — _hypothesis, medium confidence_
- **Evidence:** [`ev-7f5c5a118120`](artifacts/ev-7f5c5a118120-pytest-output.log), [`ev-73cb1bf90059`](artifacts/ev-73cb1bf90059-pytest-report.jsonl)

## Test executions

| Execution | Adapter | Label / groups | Status | P/F/E/S/B/NR/I | Duration | Note |
|---|---|---|---|---|---|---|
| `ex-8d7b7c8ade45` | pytest | existing suite [existing-suite] | **PASSED** | 13/0/0/1/0/0/0 | 1.0s |  |
| `ex-84360aae24e8` | pytest | authorization [critical-journeys] | **FAILED** | 5/2/0/0/0/0/0 | 0.9s |  |
| `ex-5d57bd816fd2` | pytest | invariants [critical-journeys] | **FAILED** | 21/2/0/0/0/0/0 | 1.5s |  |
| `ex-8d7c5c33da8c` | pytest | data integrity [regression] | **FAILED** | 10/2/0/0/0/0/0 | 1.0s |  |
| `ex-fc9e7cd015ae` | pytest | reproduce tests/qa/test_qa_authz.py::test_outsider_cannot_read_transfer #1 (rep… | **FAILED** | 0/1/0/0/0/0/0 | 0.7s |  |
| `ex-21fee5762e1e` | pytest | reproduce tests/qa/test_qa_authz.py::test_outsider_cannot_read_transfer #2 (rep… | **FAILED** | 0/1/0/0/0/0/0 | 0.7s |  |
| `ex-612fee64b92c` | pytest | reproduce tests/qa/test_qa_authz.py::test_outsider_cannot_read_transfer #3 (rep… | **FAILED** | 0/1/0/0/0/0/0 | 0.7s |  |
| `ex-3cec9eb296c3` | pytest | reproduce tests/qa/test_qa_invariants.py::test_transfer_of_entire_balance_rejec… | **FAILED** | 0/1/0/0/0/0/0 | 0.7s |  |
| `ex-c611774251a2` | pytest | reproduce tests/qa/test_qa_invariants.py::test_transfer_of_entire_balance_rejec… | **FAILED** | 0/1/0/0/0/0/0 | 0.6s |  |
| `ex-df07e8798dc1` | pytest | reproduce tests/qa/test_qa_invariants.py::test_transfer_of_entire_balance_rejec… | **FAILED** | 0/1/0/0/0/0/0 | 0.7s |  |
| `ex-90adcd24f91b` | pytest | reproduce tests/qa/test_qa_integrity.py::test_email_uniqueness_is_case_insensit… | **FAILED** | 0/1/0/0/0/0/0 | 0.6s |  |
| `ex-7eb1a91bf64f` | pytest | reproduce tests/qa/test_qa_integrity.py::test_email_uniqueness_is_case_insensit… | **FAILED** | 0/1/0/0/0/0/0 | 0.6s |  |
| `ex-7efbe729910c` | pytest | reproduce tests/qa/test_qa_integrity.py::test_email_uniqueness_is_case_insensit… | **FAILED** | 0/1/0/0/0/0/0 | 0.6s |  |

<details><summary>Failing, errored and inconclusive results (6)</summary>

- **FAILED** `tests/qa/test_qa_authz.py::test_outsider_cannot_read_transfer` (ex-84360aae24e8): client = <starlette.testclient.TestClient object at 0x735dfa7b7fe0> new_user = <function new_user.<locals>._new at 0x735dfa843600>      def test_outsider_cannot_read_transfer(client, new_user):         alice = new_user(balance=10_000)         bob = new_user()         mallory = new_user()         transfer = _send(client, alice, bob, 4_200, memo="rent for March")              r = client.get(f"/tran…
- **FAILED** `tests/qa/test_qa_authz.py::test_transfer_ids_cannot_be_enumerated` (ex-84360aae24e8): client = <starlette.testclient.TestClient object at 0x735dfa7d34d0> new_user = <function new_user.<locals>._new at 0x735dfa83f600>      def test_transfer_ids_cannot_be_enumerated(client, new_user):         alice = new_user(balance=10_000)         bob = new_user()         mallory = new_user()         ids = [_send(client, alice, bob, 100 + i, memo=f"private #{i}")["id"] for i in range(3)]          …
- **FAILED** `tests/qa/test_qa_invariants.py::test_transfer_of_entire_balance_rejected_when_fee_not_covered` (ex-5d57bd816fd2): client = <starlette.testclient.TestClient object at 0x7cda678e5d00> new_user = <function new_user.<locals>._new at 0x7cda678b00e0> balance_of = <function balance_of.<locals>.<lambda> at 0x7cda678b0180>      def test_transfer_of_entire_balance_rejected_when_fee_not_covered(client, new_user, balance_of):         alice = new_user(balance=1_000)         bob = new_user()              r = _transfer(cli…
- **FAILED** `tests/qa/test_qa_invariants.py::test_balance_never_negative_when_fee_exceeds_remaining_funds` (ex-5d57bd816fd2): client = <starlette.testclient.TestClient object at 0x7cda67874500> new_user = <function new_user.<locals>._new at 0x7cda678b3d80> balance_of = <function balance_of.<locals>.<lambda> at 0x7cda678b3ec0>      def test_balance_never_negative_when_fee_exceeds_remaining_funds(client, new_user, balance_of):         alice = new_user(balance=1_000)         bob = new_user()              _transfer(client, …
- **FAILED** `tests/qa/test_qa_integrity.py::test_email_uniqueness_is_case_insensitive` (ex-8d7c5c33da8c): client = <starlette.testclient.TestClient object at 0x7c953856be60>      def test_email_uniqueness_is_case_insensitive(client):         assert _register(client, "alice@example.com").status_code == 201              r = _register(client, "Alice@Example.com")      >       assert r.status_code == 409, (             "'Alice@Example.com' registered as a second account although 'alice@example.com' "    …
- **FAILED** `tests/qa/test_qa_integrity.py::test_login_email_is_case_insensitive` (ex-8d7c5c33da8c): client = <starlette.testclient.TestClient object at 0x7c953851ae40>      def test_login_email_is_case_insensitive(client):         assert _register(client, "Carol@Example.com").status_code == 201              r = client.post("/auth/login", json={"email": "carol@example.com", "password": [REDACTED:secret-assignment]})      >       assert r.status_code == 200, (             "login with a different …

</details>

## Coverage & traceability

- No coverage percentage reported: no coverage tool output was recorded. (QA Superteam never estimates coverage.)

| Item | Test cases | Latest statuses |
|---|---|---|
| REQ-BAL | TC-FEE | FAILED |
| REQ-VIS | TC-AUTHZ | FAILED |
| REQ-EMAIL | TC-EMAIL | FAILED |
| REQ-LARGE | — | — |
| INV-1 | TC-FEE | FAILED |
| INV-2 | TC-AUTHZ | FAILED |
| R-01 | TC-EXIST, TC-AUTHZ, TC-FEE | FAILED, FAILED, FAILED |

**Not verified by this run:**

- [medium] REQ-LARGE — no planned test case traces to this item
- [info] REQ-LARGE — out of scope: ambiguous requirement; needs product definition
- [info] load testing — out of scope: no authorized performance environment

## Risk register

| Risk | Area | P×I | Level | Key factors |
|---|---|---|---|---|
| R-01 | ledger | 3×5=15 | high | test presence: project has automated tests; criticality: money movement / business-critical |

## Test plan

Risk-based. Existing suite is mandatory. New API tests target the two critical invariants (INV-1, INV-2) and the email uniqueness rule with boundary and negative techniques. REQ-LARGE is ambiguous and out of scope.

| Case | Title | Level / technique | Groups | Priority | Origin | Ref |
|---|---|---|---|---|---|---|
| TC-EXIST | Existing suite | api / regression | existing-suite | high | existing | `tests` |
| TC-AUTHZ | Third party cannot read a transfer | api / negative | critical-journeys | critical | new | `tests/qa/test_qa_authz.py` |
| TC-FEE | Fee cannot overdraw a wallet | api / boundary | critical-journeys | critical | new | `tests/qa/test_qa_invariants.py` |
| TC-EMAIL | Case-insensitive email uniqueness | api / equivalence | regression | high | new | `tests/qa/test_qa_integrity.py` |

## Workflow phases

discovery: done, requirements: done, impact: skipped, risk: done, planning: done, delegation: done, execution: done, investigation: done, verification: done, release: done, reporting: done, regression: skipped

## Limitations & what was not verified

- Demonstration run: analysis records (requirements, plan, finding text) and the QA tests were scripted (reference tests stand in for agent-authored tests). All executions, evidence, verifications and the decision are real.
- Discovery: No CI configuration detected.
- Phases skipped in this run: impact, regression
- Evidence redaction is pattern-based and best-effort; review artifacts before sharing externally.

## Scope & environment

- Project: backend-api · languages: Python (16)
- Test suites: pytest: tests (3 files)
- Platform: Linux-7.0.0-43-generic-x86_64 · Python 3.12.3 · CI: False · git HEAD `75e11d474461` dirty=False
- Tools: pytest `pytest 9.0.2`

## Evidence index

| Artifact | Kind | Path | sha256 | Redactions |
|---|---|---|---|---|
| `ev-0f4bff781f66` | junit | [ev-0f4bff781f66-junit.xml](artifacts/ev-0f4bff781f66-junit.xml) | `0f4bff781f660140` | 0 |
| `ev-0f5d29891409` | junit | [ev-0f5d29891409-junit.xml](artifacts/ev-0f5d29891409-junit.xml) | `0f5d298914097f87` | 0 |
| `ev-173a9f8518ad` | report | [ev-173a9f8518ad-pytest-report.jsonl](artifacts/ev-173a9f8518ad-pytest-report.jsonl) | `173a9f8518ad8776` | 0 |
| `ev-1a523e7b172d` | report | [ev-1a523e7b172d-pytest-report.jsonl](artifacts/ev-1a523e7b172d-pytest-report.jsonl) | `1a523e7b172dd1c0` | 0 |
| `ev-1b325a4c03e9` | junit | [ev-1b325a4c03e9-junit.xml](artifacts/ev-1b325a4c03e9-junit.xml) | `1b325a4c03e93fed` | 0 |
| `ev-2082d67f5909` | log | [ev-2082d67f5909-pytest-output.log](artifacts/ev-2082d67f5909-pytest-output.log) | `2082d67f59093cb6` | 0 |
| `ev-2de188ab1f85` | report | [ev-2de188ab1f85-pytest-report.jsonl](artifacts/ev-2de188ab1f85-pytest-report.jsonl) | `2de188ab1f8571bd` | 0 |
| `ev-3b3ee856460b` | report | [ev-3b3ee856460b-pytest-report.jsonl](artifacts/ev-3b3ee856460b-pytest-report.jsonl) | `3b3ee856460b4a28` | 0 |
| `ev-3db4db618794` | log | [ev-3db4db618794-pytest-output.log](artifacts/ev-3db4db618794-pytest-output.log) | `3db4db6187940cfd` | 0 |
| `ev-416dbab46908` | report | [ev-416dbab46908-pytest-report.jsonl](artifacts/ev-416dbab46908-pytest-report.jsonl) | `416dbab4690839d5` | 0 |
| `ev-45f9d2d06a02` | log | [ev-45f9d2d06a02-pytest-output.log](artifacts/ev-45f9d2d06a02-pytest-output.log) | `45f9d2d06a023ca9` | 0 |
| `ev-481f06d2cc42` | junit | [ev-481f06d2cc42-junit.xml](artifacts/ev-481f06d2cc42-junit.xml) | `481f06d2cc425ec4` | 0 |
| `ev-495ffc1b98bc` | report | [ev-495ffc1b98bc-pytest-report.jsonl](artifacts/ev-495ffc1b98bc-pytest-report.jsonl) | `495ffc1b98bccc04` | 0 |
| `ev-52901e72fd33` | report | [ev-52901e72fd33-pytest-report.jsonl](artifacts/ev-52901e72fd33-pytest-report.jsonl) | `52901e72fd330ac1` | 0 |
| `ev-581fa4cd615d` | log | [ev-581fa4cd615d-pytest-output.log](artifacts/ev-581fa4cd615d-pytest-output.log) | `581fa4cd615df05c` | 0 |
| `ev-5d7786e9e1aa` | report | [ev-5d7786e9e1aa-pytest-report.jsonl](artifacts/ev-5d7786e9e1aa-pytest-report.jsonl) | `5d7786e9e1aab8b8` | 0 |
| `ev-64c19d35a4cb` | log | [ev-64c19d35a4cb-pytest-output.log](artifacts/ev-64c19d35a4cb-pytest-output.log) | `64c19d35a4cb1b21` | 0 |
| `ev-6550c1a75486` | log | [ev-6550c1a75486-pytest-output.log](artifacts/ev-6550c1a75486-pytest-output.log) | `6550c1a754865f92` | 0 |
| `ev-6c59778fd642` | junit | [ev-6c59778fd642-junit.xml](artifacts/ev-6c59778fd642-junit.xml) | `6c59778fd642f7d8` | 0 |
| `ev-73cb1bf90059` | report | [ev-73cb1bf90059-pytest-report.jsonl](artifacts/ev-73cb1bf90059-pytest-report.jsonl) | `73cb1bf90059d78a` | 0 |
| `ev-758411f8d40d` | log | [ev-758411f8d40d-pytest-output.log](artifacts/ev-758411f8d40d-pytest-output.log) | `758411f8d40d6b79` | 0 |
| `ev-7e30366b034b` | junit | [ev-7e30366b034b-junit.xml](artifacts/ev-7e30366b034b-junit.xml) | `7e30366b034b08b3` | 0 |
| `ev-7f5c5a118120` | log | [ev-7f5c5a118120-pytest-output.log](artifacts/ev-7f5c5a118120-pytest-output.log) | `7f5c5a118120f572` | 1 |
| `ev-8d32c6d8a717` | log | [ev-8d32c6d8a717-pytest-output.log](artifacts/ev-8d32c6d8a717-pytest-output.log) | `8d32c6d8a7171500` | 0 |
| `ev-915f1d7c270c` | junit | [ev-915f1d7c270c-junit.xml](artifacts/ev-915f1d7c270c-junit.xml) | `915f1d7c270cecb3` | 0 |
| `ev-9d699b74efb2` | log | [ev-9d699b74efb2-pytest-output.log](artifacts/ev-9d699b74efb2-pytest-output.log) | `9d699b74efb24efd` | 0 |
| `ev-9e6edd21678d` | log | [ev-9e6edd21678d-pytest-output.log](artifacts/ev-9e6edd21678d-pytest-output.log) | `9e6edd21678dc318` | 0 |
| `ev-a10acc36f031` | report | [ev-a10acc36f031-pytest-report.jsonl](artifacts/ev-a10acc36f031-pytest-report.jsonl) | `a10acc36f0316526` | 0 |
| `ev-a1f383d87553` | log | [ev-a1f383d87553-pytest-output.log](artifacts/ev-a1f383d87553-pytest-output.log) | `a1f383d875531903` | 0 |
| `ev-c04975fa8fdf` | junit | [ev-c04975fa8fdf-junit.xml](artifacts/ev-c04975fa8fdf-junit.xml) | `c04975fa8fdf03d0` | 0 |
| `ev-c410382a4001` | junit | [ev-c410382a4001-junit.xml](artifacts/ev-c410382a4001-junit.xml) | `c410382a400189db` | 1 |
| `ev-cc1b297e9192` | log | [ev-cc1b297e9192-pytest-output.log](artifacts/ev-cc1b297e9192-pytest-output.log) | `cc1b297e919249e9` | 0 |
| `ev-d4947d2d6374` | report | [ev-d4947d2d6374-pytest-report.jsonl](artifacts/ev-d4947d2d6374-pytest-report.jsonl) | `d4947d2d6374f4cc` | 0 |
| `ev-d7adb1cd5623` | junit | [ev-d7adb1cd5623-junit.xml](artifacts/ev-d7adb1cd5623-junit.xml) | `d7adb1cd5623999f` | 0 |
| `ev-e1ebe62c9a9f` | junit | [ev-e1ebe62c9a9f-junit.xml](artifacts/ev-e1ebe62c9a9f-junit.xml) | `e1ebe62c9a9f9772` | 0 |
| `ev-e5b5c0eb5c99` | junit | [ev-e5b5c0eb5c99-junit.xml](artifacts/ev-e5b5c0eb5c99-junit.xml) | `e5b5c0eb5c99cfb8` | 0 |
| `ev-e8d2b45a1c39` | report | [ev-e8d2b45a1c39-pytest-report.jsonl](artifacts/ev-e8d2b45a1c39-pytest-report.jsonl) | `e8d2b45a1c398b54` | 0 |
| `ev-fc32cdd4a317` | junit | [ev-fc32cdd4a317-junit.xml](artifacts/ev-fc32cdd4a317-junit.xml) | `fc32cdd4a3177ed3` | 0 |
| `ev-fed7ca5ea1e5` | report | [ev-fed7ca5ea1e5-pytest-report.jsonl](artifacts/ev-fed7ca5ea1e5-pytest-report.jsonl) | `fed7ca5ea1e5fda3` | 0 |

_Generated by QA Superteam from recorded evidence. Statuses are normalized tool results; finding statuses are derived from reproduction and verification records; the decision is computed by the deterministic policy engine._
