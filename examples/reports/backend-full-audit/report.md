# QA Report — backend-api (full-audit)

Run `20261123-134703-full-audit-2c3b` · scope: Ledger API: full repository audit · generated 2026-11-23T13:47:18Z

## ⛔ Release decision: **BLOCK**

Policy `default` v1.0.0 (sha256 `f6b8fcb3544b`) · evaluated 2026-11-23T13:47:17Z · inputs digest `db85832b0c9c`

| Rule | Outcome | Reason |
|---|---|---|
| `R-CONFIRMED-BLOCKING` | BLOCK | F-6d0ec146 [critical security] Any logged-in user can read another user's transfer; F-f16b5fbd [critical data-integrity] Fee is not included in the funds check, so balances go negative |
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

### F-6d0ec146 · Any logged-in user can read another user's transfer

**CONFIRMED** · severity **critical** · security · reported by qa-superteam:backend-qa-engineer

_Status basis:_ independently verified by qa-superteam:independent-verification-engineer (independent-rerun) in V-ec594034

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
- **Evidence:** [`ev-b04fd5243ee7`](artifacts/ev-b04fd5243ee7-pytest-output.log), [`ev-279cb16836c3`](artifacts/ev-279cb16836c3-pytest-report.jsonl)
- **Verification V-ec594034:** CONFIRMED by qa-superteam:independent-verification-engineer via independent-rerun — Re-ran tests/qa/test_qa_authz.py::test_outsider_cannot_read_transfer in an independent execution; failure is consistent (3/3).

### F-f16b5fbd · Fee is not included in the funds check, so balances go negative

**CONFIRMED** · severity **critical** · data-integrity · reported by qa-superteam:backend-qa-engineer

_Status basis:_ independently verified by qa-superteam:independent-verification-engineer (independent-rerun) in V-9c2f4f7a

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
- **Evidence:** [`ev-c87d8c3bd61e`](artifacts/ev-c87d8c3bd61e-pytest-output.log), [`ev-7cf8d6fe09b6`](artifacts/ev-7cf8d6fe09b6-pytest-report.jsonl)
- **Verification V-9c2f4f7a:** CONFIRMED by qa-superteam:independent-verification-engineer via independent-rerun — Re-ran tests/qa/test_qa_invariants.py::test_transfer_of_entire_balance_rejected_when_fee_not_covered in an independent execution; failure is consistent (3/3).

### F-ff42473e · Email uniqueness is case-sensitive, allowing duplicate accounts

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
- **Evidence:** [`ev-daa9c6fe45b0`](artifacts/ev-daa9c6fe45b0-pytest-output.log), [`ev-b5a648b919ca`](artifacts/ev-b5a648b919ca-pytest-report.jsonl)

## Test executions

| Execution | Adapter | Label / groups | Status | P/F/E/S/B/NR/I | Duration | Note |
|---|---|---|---|---|---|---|
| `ex-eaf08a9b405a` | pytest | existing suite [existing-suite] | **PASSED** | 13/0/0/1/0/0/0 | 1.0s |  |
| `ex-2e1a6aa07740` | pytest | authorization [critical-journeys] | **FAILED** | 5/2/0/0/0/0/0 | 0.9s |  |
| `ex-93e439bc5901` | pytest | invariants [critical-journeys] | **FAILED** | 21/2/0/0/0/0/0 | 1.5s |  |
| `ex-0055f27d269f` | pytest | data integrity [regression] | **FAILED** | 10/2/0/0/0/0/0 | 1.0s |  |
| `ex-d15ad38b5d71` | pytest | reproduce tests/qa/test_qa_authz.py::test_outsider_cannot_read_transfer #1 (rep… | **FAILED** | 0/1/0/0/0/0/0 | 0.7s |  |
| `ex-041d290a85a9` | pytest | reproduce tests/qa/test_qa_authz.py::test_outsider_cannot_read_transfer #2 (rep… | **FAILED** | 0/1/0/0/0/0/0 | 0.7s |  |
| `ex-165999aca805` | pytest | reproduce tests/qa/test_qa_authz.py::test_outsider_cannot_read_transfer #3 (rep… | **FAILED** | 0/1/0/0/0/0/0 | 0.7s |  |
| `ex-533d28beb94f` | pytest | reproduce tests/qa/test_qa_invariants.py::test_transfer_of_entire_balance_rejec… | **FAILED** | 0/1/0/0/0/0/0 | 0.7s |  |
| `ex-0e66e9fe0f01` | pytest | reproduce tests/qa/test_qa_invariants.py::test_transfer_of_entire_balance_rejec… | **FAILED** | 0/1/0/0/0/0/0 | 0.7s |  |
| `ex-baf1c30e7361` | pytest | reproduce tests/qa/test_qa_invariants.py::test_transfer_of_entire_balance_rejec… | **FAILED** | 0/1/0/0/0/0/0 | 0.7s |  |
| `ex-370759a5aee1` | pytest | reproduce tests/qa/test_qa_integrity.py::test_email_uniqueness_is_case_insensit… | **FAILED** | 0/1/0/0/0/0/0 | 0.6s |  |
| `ex-0912143f1f05` | pytest | reproduce tests/qa/test_qa_integrity.py::test_email_uniqueness_is_case_insensit… | **FAILED** | 0/1/0/0/0/0/0 | 0.6s |  |
| `ex-e1f619080271` | pytest | reproduce tests/qa/test_qa_integrity.py::test_email_uniqueness_is_case_insensit… | **FAILED** | 0/1/0/0/0/0/0 | 0.7s |  |

<details><summary>Failing, errored and inconclusive results (6)</summary>

- **FAILED** `tests/qa/test_qa_authz.py::test_outsider_cannot_read_transfer` (ex-2e1a6aa07740): client = <starlette.testclient.TestClient object at 0x73370df13e60> new_user = <function new_user.<locals>._new at 0x73370df9b600>      def test_outsider_cannot_read_transfer(client, new_user):         alice = new_user(balance=10_000)         bob = new_user()         mallory = new_user()         transfer = _send(client, alice, bob, 4_200, memo="rent for March")              r = client.get(f"/tran…
- **FAILED** `tests/qa/test_qa_authz.py::test_transfer_ids_cannot_be_enumerated` (ex-2e1a6aa07740): client = <starlette.testclient.TestClient object at 0x73370df2b440> new_user = <function new_user.<locals>._new at 0x73370df97420>      def test_transfer_ids_cannot_be_enumerated(client, new_user):         alice = new_user(balance=10_000)         bob = new_user()         mallory = new_user()         ids = [_send(client, alice, bob, 100 + i, memo=f"private #{i}")["id"] for i in range(3)]          …
- **FAILED** `tests/qa/test_qa_invariants.py::test_transfer_of_entire_balance_rejected_when_fee_not_covered` (ex-93e439bc5901): client = <starlette.testclient.TestClient object at 0x7773f9f71ca0> new_user = <function new_user.<locals>._new at 0x7773fa0480e0> balance_of = <function balance_of.<locals>.<lambda> at 0x7773fa048180>      def test_transfer_of_entire_balance_rejected_when_fee_not_covered(client, new_user, balance_of):         alice = new_user(balance=1_000)         bob = new_user()              r = _transfer(cli…
- **FAILED** `tests/qa/test_qa_invariants.py::test_balance_never_negative_when_fee_exceeds_remaining_funds` (ex-93e439bc5901): client = <starlette.testclient.TestClient object at 0x7773f9fd85f0> new_user = <function new_user.<locals>._new at 0x7773fa04bd80> balance_of = <function balance_of.<locals>.<lambda> at 0x7773fa04bec0>      def test_balance_never_negative_when_fee_exceeds_remaining_funds(client, new_user, balance_of):         alice = new_user(balance=1_000)         bob = new_user()              _transfer(client, …
- **FAILED** `tests/qa/test_qa_integrity.py::test_email_uniqueness_is_case_insensitive` (ex-0055f27d269f): client = <starlette.testclient.TestClient object at 0x7469b8d5fec0>      def test_email_uniqueness_is_case_insensitive(client):         assert _register(client, "alice@example.com").status_code == 201              r = _register(client, "Alice@Example.com")      >       assert r.status_code == 409, (             "'Alice@Example.com' registered as a second account although 'alice@example.com' "    …
- **FAILED** `tests/qa/test_qa_integrity.py::test_login_email_is_case_insensitive` (ex-0055f27d269f): client = <starlette.testclient.TestClient object at 0x7469b8d8ef90>      def test_login_email_is_case_insensitive(client):         assert _register(client, "Carol@Example.com").status_code == 201              r = client.post("/auth/login", json={"email": "carol@example.com", "password": [REDACTED:secret-assignment]})      >       assert r.status_code == 200, (             "login with a different …

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
- Platform: Linux-7.0.0-43-generic-x86_64 · Python 3.12.3 · CI: False · git HEAD `f6a7396772e3` dirty=False
- Tools: pytest `pytest 9.0.2`

## Evidence index

| Artifact | Kind | Path | sha256 | Redactions |
|---|---|---|---|---|
| `ev-0c659393b00b` | report | [ev-0c659393b00b-pytest-report.jsonl](artifacts/ev-0c659393b00b-pytest-report.jsonl) | `0c659393b00b0501` | 0 |
| `ev-0f83615ca9d8` | log | [ev-0f83615ca9d8-pytest-output.log](artifacts/ev-0f83615ca9d8-pytest-output.log) | `0f83615ca9d89dcd` | 0 |
| `ev-279cb16836c3` | report | [ev-279cb16836c3-pytest-report.jsonl](artifacts/ev-279cb16836c3-pytest-report.jsonl) | `279cb16836c3be22` | 0 |
| `ev-446ec233ed55` | log | [ev-446ec233ed55-pytest-output.log](artifacts/ev-446ec233ed55-pytest-output.log) | `446ec233ed55abd4` | 0 |
| `ev-4884a421dbd0` | junit | [ev-4884a421dbd0-junit.xml](artifacts/ev-4884a421dbd0-junit.xml) | `4884a421dbd0cd0f` | 0 |
| `ev-48ab8686b136` | junit | [ev-48ab8686b136-junit.xml](artifacts/ev-48ab8686b136-junit.xml) | `48ab8686b136f346` | 0 |
| `ev-5227d8eee8f9` | junit | [ev-5227d8eee8f9-junit.xml](artifacts/ev-5227d8eee8f9-junit.xml) | `5227d8eee8f988ed` | 0 |
| `ev-57e1a8aed4f4` | log | [ev-57e1a8aed4f4-pytest-output.log](artifacts/ev-57e1a8aed4f4-pytest-output.log) | `57e1a8aed4f46aad` | 0 |
| `ev-59e53a5b984b` | report | [ev-59e53a5b984b-pytest-report.jsonl](artifacts/ev-59e53a5b984b-pytest-report.jsonl) | `59e53a5b984b2f8f` | 0 |
| `ev-5f4d3a77dac7` | log | [ev-5f4d3a77dac7-pytest-output.log](artifacts/ev-5f4d3a77dac7-pytest-output.log) | `5f4d3a77dac7009e` | 0 |
| `ev-600bed64fb7e` | junit | [ev-600bed64fb7e-junit.xml](artifacts/ev-600bed64fb7e-junit.xml) | `600bed64fb7e8181` | 0 |
| `ev-6784b8bdd8d7` | log | [ev-6784b8bdd8d7-pytest-output.log](artifacts/ev-6784b8bdd8d7-pytest-output.log) | `6784b8bdd8d79730` | 0 |
| `ev-685f6f194127` | report | [ev-685f6f194127-pytest-report.jsonl](artifacts/ev-685f6f194127-pytest-report.jsonl) | `685f6f1941278e49` | 0 |
| `ev-70e9fd8cfc1f` | report | [ev-70e9fd8cfc1f-pytest-report.jsonl](artifacts/ev-70e9fd8cfc1f-pytest-report.jsonl) | `70e9fd8cfc1ff005` | 0 |
| `ev-759945d8796f` | junit | [ev-759945d8796f-junit.xml](artifacts/ev-759945d8796f-junit.xml) | `759945d8796fbbb3` | 0 |
| `ev-7a5d376b6efd` | report | [ev-7a5d376b6efd-pytest-report.jsonl](artifacts/ev-7a5d376b6efd-pytest-report.jsonl) | `7a5d376b6efd559a` | 0 |
| `ev-7c984425306c` | junit | [ev-7c984425306c-junit.xml](artifacts/ev-7c984425306c-junit.xml) | `7c984425306c30d3` | 0 |
| `ev-7cf8d6fe09b6` | report | [ev-7cf8d6fe09b6-pytest-report.jsonl](artifacts/ev-7cf8d6fe09b6-pytest-report.jsonl) | `7cf8d6fe09b67fec` | 0 |
| `ev-85e0a2ac2897` | log | [ev-85e0a2ac2897-pytest-output.log](artifacts/ev-85e0a2ac2897-pytest-output.log) | `85e0a2ac2897fe87` | 0 |
| `ev-8a97f2110db7` | junit | [ev-8a97f2110db7-junit.xml](artifacts/ev-8a97f2110db7-junit.xml) | `8a97f2110db7653c` | 1 |
| `ev-8ad819f80dde` | log | [ev-8ad819f80dde-pytest-output.log](artifacts/ev-8ad819f80dde-pytest-output.log) | `8ad819f80dde9ff4` | 0 |
| `ev-9bb81d1d238b` | report | [ev-9bb81d1d238b-pytest-report.jsonl](artifacts/ev-9bb81d1d238b-pytest-report.jsonl) | `9bb81d1d238be174` | 0 |
| `ev-a59c8b071071` | report | [ev-a59c8b071071-pytest-report.jsonl](artifacts/ev-a59c8b071071-pytest-report.jsonl) | `a59c8b0710714826` | 0 |
| `ev-aa69dfeb8cac` | log | [ev-aa69dfeb8cac-pytest-output.log](artifacts/ev-aa69dfeb8cac-pytest-output.log) | `aa69dfeb8cac2ec2` | 0 |
| `ev-ad7a313463b3` | junit | [ev-ad7a313463b3-junit.xml](artifacts/ev-ad7a313463b3-junit.xml) | `ad7a313463b31393` | 0 |
| `ev-affe56eb8bc5` | report | [ev-affe56eb8bc5-pytest-report.jsonl](artifacts/ev-affe56eb8bc5-pytest-report.jsonl) | `affe56eb8bc560f0` | 0 |
| `ev-b04fd5243ee7` | log | [ev-b04fd5243ee7-pytest-output.log](artifacts/ev-b04fd5243ee7-pytest-output.log) | `b04fd5243ee7e733` | 0 |
| `ev-b19fd7033ce1` | report | [ev-b19fd7033ce1-pytest-report.jsonl](artifacts/ev-b19fd7033ce1-pytest-report.jsonl) | `b19fd7033ce156bc` | 0 |
| `ev-b5a648b919ca` | report | [ev-b5a648b919ca-pytest-report.jsonl](artifacts/ev-b5a648b919ca-pytest-report.jsonl) | `b5a648b919ca7bf4` | 0 |
| `ev-b912419d7250` | junit | [ev-b912419d7250-junit.xml](artifacts/ev-b912419d7250-junit.xml) | `b912419d7250486d` | 0 |
| `ev-c069c3fc42ec` | log | [ev-c069c3fc42ec-pytest-output.log](artifacts/ev-c069c3fc42ec-pytest-output.log) | `c069c3fc42ec2d01` | 0 |
| `ev-c076fdd3dbcc` | junit | [ev-c076fdd3dbcc-junit.xml](artifacts/ev-c076fdd3dbcc-junit.xml) | `c076fdd3dbccff94` | 0 |
| `ev-c87d8c3bd61e` | log | [ev-c87d8c3bd61e-pytest-output.log](artifacts/ev-c87d8c3bd61e-pytest-output.log) | `c87d8c3bd61ed961` | 0 |
| `ev-cdb0f409fe88` | log | [ev-cdb0f409fe88-pytest-output.log](artifacts/ev-cdb0f409fe88-pytest-output.log) | `cdb0f409fe88a235` | 0 |
| `ev-daa9c6fe45b0` | log | [ev-daa9c6fe45b0-pytest-output.log](artifacts/ev-daa9c6fe45b0-pytest-output.log) | `daa9c6fe45b001af` | 1 |
| `ev-e9fe3a5704da` | report | [ev-e9fe3a5704da-pytest-report.jsonl](artifacts/ev-e9fe3a5704da-pytest-report.jsonl) | `e9fe3a5704dacd8e` | 0 |
| `ev-ebb4926b5337` | junit | [ev-ebb4926b5337-junit.xml](artifacts/ev-ebb4926b5337-junit.xml) | `ebb4926b5337f65d` | 0 |
| `ev-f3a65952edd0` | junit | [ev-f3a65952edd0-junit.xml](artifacts/ev-f3a65952edd0-junit.xml) | `f3a65952edd08019` | 0 |
| `ev-fafd40f30e53` | junit | [ev-fafd40f30e53-junit.xml](artifacts/ev-fafd40f30e53-junit.xml) | `fafd40f30e538c80` | 0 |

_Generated by QA Superteam from recorded evidence. Statuses are normalized tool results; finding statuses are derived from reproduction and verification records; the decision is computed by the deterministic policy engine._
