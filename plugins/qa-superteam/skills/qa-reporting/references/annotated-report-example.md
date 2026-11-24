# Annotated report example

A fictional `orders-service` pull-request run, used only to show how summaries are
derived. Ids, paths and numbers are illustrative; in a real run copy them from
`report.md`.

## 1. Excerpt of report.md (as `qast report` renders it)

```markdown
# QA Report — orders-service (review-pr)

Run `20261102-101500-review-pr-4821` · scope: PR 311 checkout retry · generated 2026-11-02T10:52:10Z
Diff: `origin/main` → `working tree`

## ⛔ Release decision: **BLOCK**

Policy `default` v1.0.0 (sha256 `2c9cb446d464`) · evaluated 2026-11-02T10:51:58Z · inputs digest `91e0c2a7d4b3`

| Rule | Outcome | Reason |
|---|---|---|
| `R-CONFIRMED-BLOCKING` | BLOCK | F-1a2b3c [critical data-integrity] Stock reserved twice when an order is retried after a payment timeout |
| `R-UNVERIFIED-HIGH-IMPACT` | REVIEW_REQUIRED | F-4d5e6f [high, SUSPECTED] Order export includes other tenants' orders |
| `R-UNTESTED-HIGH-RISK` | REVIEW_REQUIRED | 1 high-priority item(s) without an executed outcome: test case TC-09 |

## Summary

| FAILED | ERROR | INCONCLUSIVE | BLOCKED | NOT_RUN | SKIPPED | PASSED |
|---|---|---|---|---|---|---|
| 1 | 0 | 0 | 1 | 0 | 0 | 214 |

Executions: 5 · Findings: 2 (CONFIRMED 1, SUSPECTED 1)

## Coverage & traceability

- No coverage percentage reported: no coverage tool output was recorded. (QA Superteam never estimates coverage.)

| Item | Test cases | Latest statuses |
|---|---|---|
| INV-2 | TC-04, TC-05 | FAILED, PASSED |
| R-01 | TC-04, TC-05 | FAILED, PASSED |
| R-03 | TC-09 | NOT_RUN |

**Not verified by this run:**

- [high] R-03 — planned tests did not reach a pass/fail outcome: NOT_RUN
- [medium] playwright (mobile checkout) — BLOCKED: browser executable not installed
```

## 2. Release-manager summary

```
**QA result: BLOCK** — policy default v1.0.0 · run 20261102-101500-review-pr-4821
Why: R-CONFIRMED-BLOCKING — a confirmed critical defect: when a customer retries an order after
a payment timeout, the stock is reserved twice. R-UNVERIFIED-HIGH-IMPACT — a high-severity
report that the order export shows other tenants' orders is not verified yet. R-UNTESTED-HIGH-RISK —
the mobile checkout test (TC-09) did not run.
Confirmed defects (1): F-1a2b3c [critical] stock reserved twice on retry — evidence in report.md
Not yet verified (1): F-4d5e6f [high, suspected] export includes other tenants' orders — next step: independent verification
Executed: 5 executions — 214 passed, 1 failed, 1 blocked
Not verified: mobile checkout (TC-09) — the browser is not installed in this environment — to verify: install the Playwright browsers (see Playwright's documentation), re-run
Decisions needed from you: 1. Hold PR 311 until F-1a2b3c is fixed and re-tested? (BLOCK cannot be waived by QA)
Full report: .qa-superteam/runs/20261102-101500-review-pr-4821/report.md
```

> **Why this shape.** Decision first, with the policy, because the gate decides, not the
> writer. Each rule is translated into one sentence a non-engineer can act on. The
> suspected finding is called "not verified" and is not counted as a defect. The blocked
> mobile test appears as a limitation with the exact unblocking step. No percentages:
> the report states that coverage was not measured.

## 3. Developer summary

```
F-1a2b3c [critical, CONFIRMED by qa-superteam:independent-verification-engineer]
Stock reserved twice when an order is retried after a payment timeout
Expected: one reservation per order id; reserved = 2 for a 2-unit order (REQ-ORD-7, INV-2)
Actual:   reserved = 4 and available = 6 after one timeout and one retry (on_hand 10)
Repro:    1. set SKU-1 on_hand 10  2. place a 2-unit order with the payment stub timing out
          3. retry the same order  4. GET /stock/SKU-1
Test:     tests/qa/test_reservations.py::test_retry_after_timeout_reserves_once (FAILED in ex-7c1e..., 3/3 reproductions)
Evidence: ev-0f3a... (junit), ev-9b21... (log)
Location: src/orders/checkout.py (place_order)
Hypothesis (medium confidence, not confirmed): the reservation is written before the idempotency
check, so the retry reserves again.
Regression test: tests/qa/test_reservations.py::test_retry_after_timeout_reserves_once — fails now, must pass after the fix.

F-4d5e6f [high, SUSPECTED — not reproduced, not verified]
Order export includes other tenants' orders. Next step: reproduce with a two-tenant fixture; do not
treat as a confirmed defect yet.
```

> **Why this shape.** Status words come from the derived status, verbatim in meaning. The
> root-cause idea is labelled a hypothesis with its confidence. Every claim carries an
> execution or evidence id. The regression test is named so the fix can be checked.

## 4. QA-lead summary

```
Evidence gaps: TC-09 (R-03, high) NOT_RUN — Playwright browser missing (BLOCKED execution).
Verification queue: F-4d5e6f (high, SUSPECTED) → independent-verification-engineer.
Traceability: INV-2 has one FAILED and one PASSED case (TC-04 failed: the confirmed defect).
Coverage: not measured; add `coverage` (qast doctor shows it missing) if a measured number is needed.
Next test work: two-tenant export test for R-03/F-4d5e6f; install chromium and run TC-09.
```

> **Why this shape.** A QA lead needs to know where the evidence is thin and what to run
> next, not the narrative. Every gap names its unblocking action.

## 5. A rejected draft

```
Great news overall: the PR looks good and all tests pass except one minor retry bug,
which is probably caused by the payment client. Coverage is around 85%, so confidence is high.
The export issue is a confirmed security bug. Once the retry bug is fixed we're
production-ready.
```

| Problem | Why it is wrong |
|---|---|
| "looks good", "all tests pass except one" | opinion; hides 1 blocked execution and the unrun high-priority case |
| "minor retry bug" | recorded severity is critical |
| "probably caused by the payment client" | an unrecorded hypothesis stated as a likely fact |
| "around 85%", "confidence is high" | no coverage tool ran; both numbers are invented |
| "confirmed security bug" | F-4d5e6f is SUSPECTED |
| "production-ready" once fixed | readiness is the gate's decision on a new run, not a prediction |
