# QA Report — web-checkout (test-e2e)

Run `20261123-134724-test-e2e-9e6d` · scope: Checkout SPA: critical journeys and accessibility · generated 2026-11-23T13:48:23Z

## ⛔ Release decision: **BLOCK**

Policy `default` v1.0.0 (sha256 `f6b8fcb3544b`) · evaluated 2026-11-23T13:48:23Z · inputs digest `04a54e6a7275`

| Rule | Outcome | Reason |
|---|---|---|
| `R-CONFIRMED-REVIEW` | REVIEW_REQUIRED | F-52b23502 [high] Checkout is blocked after correcting an invalid postal code; F-13c12f92 [high] Promo code input has no accessible name |
| `R-PLANNED-MANDATORY-CASES` | BLOCK | planned mandatory test cases failed: TC-RECOVER, TC-PROMO, TC-RTL |

<details><summary>Rules satisfied (8)</summary>

- `R-EVIDENCE-EXISTS` — 4 execution(s) recorded
- `R-EVIDENCE-INTEGRITY` — all evidence hashes verified
- `R-CONFIRMED-BLOCKING` — no confirmed finding at a blocking severity
- `R-UNVERIFIED-HIGH-IMPACT` — no unverified high-impact findings
- `R-MANDATORY-GROUP:existing-suite` — mandatory group 'existing-suite': 6 passed, 0 skipped (within allowance)
- `R-UNTRIAGED-FAILURES` — every failure is linked to a finding
- `R-FLAKY-CRITICAL` — no flaky critical tests observed
- `R-UNTESTED-HIGH-RISK` — every high-priority planned item has an executed outcome

</details>

## Summary

| FAILED | ERROR | INCONCLUSIVE | BLOCKED | NOT_RUN | SKIPPED | PASSED |
|---|---|---|---|---|---|---|
| 3 | 0 | 0 | 0 | 0 | 0 | 38 |

Executions: 13 · Findings: 3 (CONFIRMED 2, REPRODUCED 1)

## Findings

### F-13c12f92 · Promo code input has no accessible name

**CONFIRMED** · severity **high** · accessibility · reported by qa-superteam:frontend-qa-engineer

_Status basis:_ independently verified by qa-superteam:independent-verification-engineer (independent-rerun) in V-3bb946b4

- **Expected:** Every form control has an accessible name (WCAG 1.3.1 / 4.1.2)
- **Actual:** axe 'label' violation on #promo-code
- **Location:** `public/app.js`
- **Tests:** `tests/qa/test_qa_a11y.py::test_review_step_has_no_serious_axe_violations`
- **Reproduction steps:**
  1. Reach review step
  2. Run axe-core
  3. Rule 'label' fails for #promo-code
- **Evidence:** [`ev-80ff8843e4bf`](artifacts/ev-80ff8843e4bf-pytest-output.log), [`ev-4065c731b7fe`](artifacts/ev-4065c731b7fe-pytest-report.jsonl), [`ev-a9655cc7cb80`](artifacts/ev-a9655cc7cb80-junit.xml), [`ev-2c16b29ef450`](artifacts/ev-2c16b29ef450-tests-qa-test-qa-a11y-py-test-review-step-has-no-serious-axe.png)
- **Verification V-3bb946b4:** CONFIRMED by qa-superteam:independent-verification-engineer via independent-rerun — Independent rerun of tests/qa/test_qa_a11y.py::test_review_step_has_no_serious_axe_violations: consistent failure; screenshots attached.

### F-52b23502 · Checkout is blocked after correcting an invalid postal code

**CONFIRMED** · severity **high** · functional · reported by qa-superteam:frontend-qa-engineer

_Status basis:_ independently verified by qa-superteam:independent-verification-engineer (independent-rerun) in V-c0449591

- **Expected:** After fixing the postal code, Continue is enabled (USER_JOURNEYS.md: recovering from a validation error)
- **Actual:** Error clears but Continue stays disabled until reload
- **Location:** `public/app.js`
- **Tests:** `tests/qa/test_qa_journeys.py::test_recover_from_postal_code_error_and_complete_checkout`
- **Reproduction steps:**
  1. Fill contact step
  2. Enter postal code 12 for US
  3. See error
  4. Correct to 12345
  5. Continue stays disabled
- **Evidence:** [`ev-00ba9aaef7a4`](artifacts/ev-00ba9aaef7a4-pytest-output.log), [`ev-d02254f24b58`](artifacts/ev-d02254f24b58-pytest-report.jsonl), [`ev-b8a29234f630`](artifacts/ev-b8a29234f630-junit.xml), [`ev-d18f94779aae`](artifacts/ev-d18f94779aae-tests-qa-test-qa-journeys-py-test-promo-apply-then-remove-re.png), [`ev-8679a631d61a`](artifacts/ev-8679a631d61a-tests-qa-test-qa-journeys-py-test-recover-from-postal-code-e.png)
- **Verification V-c0449591:** CONFIRMED by qa-superteam:independent-verification-engineer via independent-rerun — Independent rerun of tests/qa/test_qa_journeys.py::test_recover_from_postal_code_error_and_complete_checkout: consistent failure; screenshots attached.

### F-d164efd1 · Removing a promo code keeps the discount in the total

**REPRODUCED** · severity **medium** · functional · reported by qa-superteam:frontend-qa-engineer

_Status basis:_ reproduction 3/3 failing (consistent); not yet independently verified

- **Expected:** Total returns to undiscounted value after Remove
- **Actual:** Total still includes the 10% discount
- **Location:** `public/app.js`
- **Tests:** `tests/qa/test_qa_journeys.py::test_promo_apply_then_remove_restores_total`
- **Reproduction steps:**
  1. Reach review step
  2. Apply SAVE10
  3. Click Remove
  4. Total still discounted
- **Evidence:** [`ev-00ba9aaef7a4`](artifacts/ev-00ba9aaef7a4-pytest-output.log), [`ev-d02254f24b58`](artifacts/ev-d02254f24b58-pytest-report.jsonl), [`ev-b8a29234f630`](artifacts/ev-b8a29234f630-junit.xml), [`ev-d18f94779aae`](artifacts/ev-d18f94779aae-tests-qa-test-qa-journeys-py-test-promo-apply-then-remove-re.png), [`ev-8679a631d61a`](artifacts/ev-8679a631d61a-tests-qa-test-qa-journeys-py-test-recover-from-postal-code-e.png)

## Test executions

| Execution | Adapter | Label / groups | Status | P/F/E/S/B/NR/I | Duration | Note |
|---|---|---|---|---|---|---|
| `ex-ffb81dfea4fb` | pytest | existing Playwright suite [existing-suite] | **PASSED** | 6/0/0/0/0/0/0 | 2.7s |  |
| `ex-5f12edf9a86a` | pytest | journeys [critical-journeys] | **FAILED** | 5/2/0/0/0/0/0 | 12.0s |  |
| `ex-4cff8ce2a7cc` | pytest | axe on app states [accessibility] | **FAILED** | 3/1/0/0/0/0/0 | 2.5s |  |
| `ex-6a396bb34741` | axe | axe landing page (375px) [accessibility] | **PASSED** | 24/0/0/0/0/0/0 | 1.5s |  |
| `ex-054c3aecacfc` | pytest | reproduce tests/qa/test_qa_journeys.py::test_recover_from_postal_code_error_and… | **FAILED** | 0/1/0/0/0/0/0 | 4.4s |  |
| `ex-a25228a7428f` | pytest | reproduce tests/qa/test_qa_journeys.py::test_recover_from_postal_code_error_and… | **FAILED** | 0/1/0/0/0/0/0 | 4.4s |  |
| `ex-fe2578c4c7fb` | pytest | reproduce tests/qa/test_qa_journeys.py::test_recover_from_postal_code_error_and… | **FAILED** | 0/1/0/0/0/0/0 | 4.4s |  |
| `ex-b64f6017bdad` | pytest | reproduce tests/qa/test_qa_journeys.py::test_promo_apply_then_remove_restores_t… | **FAILED** | 0/1/0/0/0/0/0 | 6.4s |  |
| `ex-60f210e68357` | pytest | reproduce tests/qa/test_qa_journeys.py::test_promo_apply_then_remove_restores_t… | **FAILED** | 0/1/0/0/0/0/0 | 6.4s |  |
| `ex-a65cb31995b2` | pytest | reproduce tests/qa/test_qa_journeys.py::test_promo_apply_then_remove_restores_t… | **FAILED** | 0/1/0/0/0/0/0 | 6.4s |  |
| `ex-5cc1a4c96de3` | pytest | reproduce tests/qa/test_qa_a11y.py::test_review_step_has_no_serious_axe_violati… | **FAILED** | 0/1/0/0/0/0/0 | 1.4s |  |
| `ex-b9bb5e82f55a` | pytest | reproduce tests/qa/test_qa_a11y.py::test_review_step_has_no_serious_axe_violati… | **FAILED** | 0/1/0/0/0/0/0 | 1.4s |  |
| `ex-abddc2daba70` | pytest | reproduce tests/qa/test_qa_a11y.py::test_review_step_has_no_serious_axe_violati… | **FAILED** | 0/1/0/0/0/0/0 | 1.4s |  |

<details><summary>Failing, errored and inconclusive results (3)</summary>

- **FAILED** `tests/qa/test_qa_journeys.py::test_recover_from_postal_code_error_and_complete_checkout` (ex-5f12edf9a86a): checkout = <conftest.Checkout object at 0x7c25d9866c30>      def test_recover_from_postal_code_error_and_complete_checkout(checkout):         page = checkout.page         checkout.open().fill_contact()              postal = page.get_by_test_id("postal-code")         continue_button = page.get_by_test_id("shipping-continue")         postal_error = page.locator("#postal-code-error")              po…
- **FAILED** `tests/qa/test_qa_journeys.py::test_promo_apply_then_remove_restores_total` (ex-5f12edf9a86a): checkout = <conftest.Checkout object at 0x7c25d95db050>      def test_promo_apply_then_remove_restores_total(checkout):         page = checkout.page         checkout.to_review(country="US", postal="94107")              total = page.get_by_test_id("total")         expect(page.get_by_test_id("subtotal")).to_have_text("$80.00")         expect(page.get_by_test_id("shipping-cost")).to_have_text("$5.00…
- **FAILED** `tests/qa/test_qa_a11y.py::test_review_step_has_no_serious_axe_violations` (ex-4cff8ce2a7cc): checkout = <conftest.Checkout object at 0x7a8b4786a7b0> axe_path = PosixPath('<project>/node_modules/axe-core/axe.min.js')      def test_review_step_has_no_serious_axe_violations(checkout, axe_path: Path):         checkout.to_review()         expect(checkout.page.get_by_test_id("promo-input")).to_be_visible()              violations = blocking(run_axe(checkout.p…

</details>

## Coverage & traceability

- No coverage percentage reported: no coverage tool output was recorded. (QA Superteam never estimates coverage.)

**Not verified by this run:**

- [info] screen-reader and 200% zoom checks — out of scope: manual validation required; not automatable here

## Test plan

Journeys from docs/USER_JOURNEYS.md are mandatory (critical-journeys). Existing Playwright suite is the regression baseline. Accessibility via axe-core on each app state plus a page-level adapter scan; manual screen-reader checks are out of scope.

| Case | Title | Level / technique | Groups | Priority | Origin | Ref |
|---|---|---|---|---|---|---|
| TC-RECOVER | Recover from a postal-code validation error and complete ch… | e2e / state-transition | critical-journeys | critical | new | `tests/qa/test_qa_journeys.py::test_recover_from_postal_code_error_and…` |
| TC-PROMO | Promo apply then remove restores the total | e2e / state-transition | regression | high | new | `tests/qa/test_qa_journeys.py::test_promo_apply_then_remove_restores_t…` |
| TC-RTL | Arabic locale renders right-to-left | e2e / equivalence | critical-journeys | medium | new | `tests/qa/test_qa_journeys.py` |
| TC-A11Y | No serious/critical axe violations on the review step | accessibility / smoke | accessibility | high | new | `tests/qa/test_qa_a11y.py` |

## Workflow phases

discovery: done, requirements: pending, impact: pending, risk: pending, planning: done, delegation: pending, execution: done, investigation: pending, verification: done, release: pending, reporting: pending, regression: pending

## Limitations & what was not verified

- Demonstration run: analysis records (requirements, plan, finding text) and the QA tests were scripted (reference tests stand in for agent-authored tests). All executions, evidence, verifications and the decision are real.
- Discovery: No CI configuration detected.
- Discovery: No authentication mechanism detected; confirm whether the system is meant to be public.
- Evidence redaction is pattern-based and best-effort; review artifacts before sharing externally.

## Scope & environment

- Project: web-checkout · languages: Python (5), JavaScript (2), HTML (1), CSS (1)
- Test suites: pytest: tests (3 files)
- Platform: Linux-7.0.0-43-generic-x86_64 · Python 3.12.3 · CI: False · git HEAD `bd743a5ff3d6` dirty=False
- Tools: pytest `pytest 9.0.2`

## Evidence index

| Artifact | Kind | Path | sha256 | Redactions |
|---|---|---|---|---|
| `ev-00ba9aaef7a4` | log | [ev-00ba9aaef7a4-pytest-output.log](artifacts/ev-00ba9aaef7a4-pytest-output.log) | `00ba9aaef7a4161a` | 0 |
| `ev-04d77f18f409` | report | [ev-04d77f18f409-pytest-report.jsonl](artifacts/ev-04d77f18f409-pytest-report.jsonl) | `04d77f18f4090b1c` | 0 |
| `ev-0966a69f29d0` | screenshot | [ev-0966a69f29d0-http-127-0-0-1-36765.png](artifacts/ev-0966a69f29d0-http-127-0-0-1-36765.png) | `0966a69f29d025c6` | 0 |
| `ev-0b25ae41120e` | log | [ev-0b25ae41120e-pytest-output.log](artifacts/ev-0b25ae41120e-pytest-output.log) | `0b25ae41120e40b9` | 0 |
| `ev-0eb500a3ae05` | report | [ev-0eb500a3ae05-pytest-report.jsonl](artifacts/ev-0eb500a3ae05-pytest-report.jsonl) | `0eb500a3ae059eb4` | 0 |
| `ev-107ba709aadb` | report | [ev-107ba709aadb-pytest-report.jsonl](artifacts/ev-107ba709aadb-pytest-report.jsonl) | `107ba709aadbb2b3` | 0 |
| `ev-2c16b29ef450` | screenshot | [ev-2c16b29ef450-tests-qa-test-qa-a11y-py-test-review-step-has-no-serious-axe.png](artifacts/ev-2c16b29ef450-tests-qa-test-qa-a11y-py-test-review-step-has-no-serious-axe.png) | `2c16b29ef4504aa5` | 0 |
| `ev-33071bd82af4` | report | [ev-33071bd82af4-pytest-report.jsonl](artifacts/ev-33071bd82af4-pytest-report.jsonl) | `33071bd82af46b83` | 0 |
| `ev-35154dc25841` | report | [ev-35154dc25841-pytest-report.jsonl](artifacts/ev-35154dc25841-pytest-report.jsonl) | `35154dc258412c0c` | 0 |
| `ev-3fc6935fd51b` | report | [ev-3fc6935fd51b-pytest-report.jsonl](artifacts/ev-3fc6935fd51b-pytest-report.jsonl) | `3fc6935fd51b349c` | 0 |
| `ev-4065c731b7fe` | report | [ev-4065c731b7fe-pytest-report.jsonl](artifacts/ev-4065c731b7fe-pytest-report.jsonl) | `4065c731b7fe8272` | 0 |
| `ev-54be768ddeff` | junit | [ev-54be768ddeff-junit.xml](artifacts/ev-54be768ddeff-junit.xml) | `54be768ddeff3655` | 0 |
| `ev-55b056853a90` | report | [ev-55b056853a90-pytest-report.jsonl](artifacts/ev-55b056853a90-pytest-report.jsonl) | `55b056853a90ad2e` | 0 |
| `ev-57bf35ddf4a1` | log | [ev-57bf35ddf4a1-pytest-output.log](artifacts/ev-57bf35ddf4a1-pytest-output.log) | `57bf35ddf4a13c0a` | 0 |
| `ev-5f367d5ca1f7` | log | [ev-5f367d5ca1f7-pytest-output.log](artifacts/ev-5f367d5ca1f7-pytest-output.log) | `5f367d5ca1f74eba` | 0 |
| `ev-668d890c8df4` | junit | [ev-668d890c8df4-junit.xml](artifacts/ev-668d890c8df4-junit.xml) | `668d890c8df467b2` | 0 |
| `ev-671f202f7608` | log | [ev-671f202f7608-pytest-output.log](artifacts/ev-671f202f7608-pytest-output.log) | `671f202f7608324c` | 0 |
| `ev-6c5de29ac8b9` | junit | [ev-6c5de29ac8b9-junit.xml](artifacts/ev-6c5de29ac8b9-junit.xml) | `6c5de29ac8b9b1a7` | 0 |
| `ev-6e9e064d811c` | log | [ev-6e9e064d811c-axe-output.log](artifacts/ev-6e9e064d811c-axe-output.log) | `6e9e064d811c61da` | 0 |
| `ev-73f96087608a` | log | [ev-73f96087608a-pytest-output.log](artifacts/ev-73f96087608a-pytest-output.log) | `73f96087608add30` | 0 |
| `ev-76127979b563` | report | [ev-76127979b563-axe-result.json](artifacts/ev-76127979b563-axe-result.json) | `76127979b563c86b` | 0 |
| `ev-7989f26f0095` | junit | [ev-7989f26f0095-junit.xml](artifacts/ev-7989f26f0095-junit.xml) | `7989f26f009552b0` | 0 |
| `ev-7c1769b14cc2` | junit | [ev-7c1769b14cc2-junit.xml](artifacts/ev-7c1769b14cc2-junit.xml) | `7c1769b14cc2b5e5` | 0 |
| `ev-7fae74298a08` | log | [ev-7fae74298a08-pytest-output.log](artifacts/ev-7fae74298a08-pytest-output.log) | `7fae74298a08de49` | 0 |
| `ev-80ff8843e4bf` | log | [ev-80ff8843e4bf-pytest-output.log](artifacts/ev-80ff8843e4bf-pytest-output.log) | `80ff8843e4bf3619` | 0 |
| `ev-8512a628cfd2` | report | [ev-8512a628cfd2-pytest-report.jsonl](artifacts/ev-8512a628cfd2-pytest-report.jsonl) | `8512a628cfd273f0` | 0 |
| `ev-85ee711c5098` | junit | [ev-85ee711c5098-junit.xml](artifacts/ev-85ee711c5098-junit.xml) | `85ee711c5098b767` | 0 |
| `ev-8679a631d61a` | screenshot | [ev-8679a631d61a-tests-qa-test-qa-journeys-py-test-recover-from-postal-code-e.png](artifacts/ev-8679a631d61a-tests-qa-test-qa-journeys-py-test-recover-from-postal-code-e.png) | `8679a631d61a36cc` | 0 |
| `ev-924942cc2ffd` | junit | [ev-924942cc2ffd-junit.xml](artifacts/ev-924942cc2ffd-junit.xml) | `924942cc2ffdb26b` | 0 |
| `ev-a9655cc7cb80` | junit | [ev-a9655cc7cb80-junit.xml](artifacts/ev-a9655cc7cb80-junit.xml) | `a9655cc7cb8091d5` | 0 |
| `ev-ad9de0de881e` | log | [ev-ad9de0de881e-pytest-output.log](artifacts/ev-ad9de0de881e-pytest-output.log) | `ad9de0de881ee0bb` | 0 |
| `ev-b31fb1a3cdbe` | report | [ev-b31fb1a3cdbe-pytest-report.jsonl](artifacts/ev-b31fb1a3cdbe-pytest-report.jsonl) | `b31fb1a3cdbef192` | 0 |
| `ev-b7c83382bd65` | log | [ev-b7c83382bd65-pytest-output.log](artifacts/ev-b7c83382bd65-pytest-output.log) | `b7c83382bd65b134` | 0 |
| `ev-b8a29234f630` | junit | [ev-b8a29234f630-junit.xml](artifacts/ev-b8a29234f630-junit.xml) | `b8a29234f630dd56` | 0 |
| `ev-bda98dc10bc1` | junit | [ev-bda98dc10bc1-junit.xml](artifacts/ev-bda98dc10bc1-junit.xml) | `bda98dc10bc127ab` | 0 |
| `ev-d02254f24b58` | report | [ev-d02254f24b58-pytest-report.jsonl](artifacts/ev-d02254f24b58-pytest-report.jsonl) | `d02254f24b58169f` | 0 |
| `ev-d18f94779aae` | screenshot | [ev-d18f94779aae-tests-qa-test-qa-journeys-py-test-promo-apply-then-remove-re.png](artifacts/ev-d18f94779aae-tests-qa-test-qa-journeys-py-test-promo-apply-then-remove-re.png) | `d18f94779aae9e8e` | 0 |
| `ev-d30983f5dc76` | log | [ev-d30983f5dc76-pytest-output.log](artifacts/ev-d30983f5dc76-pytest-output.log) | `d30983f5dc763748` | 0 |
| `ev-e15136746132` | junit | [ev-e15136746132-junit.xml](artifacts/ev-e15136746132-junit.xml) | `e151367461320fb3` | 0 |
| `ev-ef60adc1cf1d` | junit | [ev-ef60adc1cf1d-junit.xml](artifacts/ev-ef60adc1cf1d-junit.xml) | `ef60adc1cf1d264e` | 0 |
| `ev-f29ba7dcf39f` | report | [ev-f29ba7dcf39f-pytest-report.jsonl](artifacts/ev-f29ba7dcf39f-pytest-report.jsonl) | `f29ba7dcf39f118c` | 0 |
| `ev-f662b84160a1` | log | [ev-f662b84160a1-pytest-output.log](artifacts/ev-f662b84160a1-pytest-output.log) | `f662b84160a1360e` | 0 |

_Generated by QA Superteam from recorded evidence. Statuses are normalized tool results; finding statuses are derived from reproduction and verification records; the decision is computed by the deterministic policy engine._
