# QA Report — web-checkout (test-e2e)

Run `20261123-142758-test-e2e-0d83` · scope: Checkout SPA: critical journeys and accessibility · generated 2026-11-23T14:28:56Z

## ⛔ Release decision: **BLOCK**

Policy `default` v1.0.0 (sha256 `f6b8fcb3544b`) · evaluated 2026-11-23T14:28:56Z · inputs digest `696f26c3af62`

| Rule | Outcome | Reason |
|---|---|---|
| `R-CONFIRMED-REVIEW` | REVIEW_REQUIRED | F-808e865e [high] Checkout is blocked after correcting an invalid postal code; F-ab1fe8b9 [high] Promo code input has no accessible name |
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
| 3 | 0 | 0 | 0 | 0 | 0 | 39 |

Executions: 13 · Findings: 3 (CONFIRMED 2, REPRODUCED 1)

## Findings

### F-808e865e · Checkout is blocked after correcting an invalid postal code

**CONFIRMED** · severity **high** · functional · reported by qa-superteam:frontend-qa-engineer

_Status basis:_ independently verified by qa-superteam:independent-verification-engineer (independent-rerun) in V-62140143

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
- **Evidence:** [`ev-34afeef02eea`](artifacts/ev-34afeef02eea-pytest-output.log), [`ev-4ded86b1d3e4`](artifacts/ev-4ded86b1d3e4-pytest-report.jsonl), [`ev-47fbc48c1187`](artifacts/ev-47fbc48c1187-junit.xml), [`ev-d18f94779aae`](artifacts/ev-d18f94779aae-tests-qa-test-qa-journeys-py-test-promo-apply-then-remove-re.png), [`ev-8679a631d61a`](artifacts/ev-8679a631d61a-tests-qa-test-qa-journeys-py-test-recover-from-postal-code-e.png)
- **Verification V-62140143:** CONFIRMED by qa-superteam:independent-verification-engineer via independent-rerun — Independent rerun of tests/qa/test_qa_journeys.py::test_recover_from_postal_code_error_and_complete_checkout: consistent failure; screenshots attached.

### F-ab1fe8b9 · Promo code input has no accessible name

**CONFIRMED** · severity **high** · accessibility · reported by qa-superteam:frontend-qa-engineer

_Status basis:_ independently verified by qa-superteam:independent-verification-engineer (independent-rerun) in V-96aad409

- **Expected:** Every form control has an accessible name (WCAG 1.3.1 / 4.1.2)
- **Actual:** axe 'label' violation on #promo-code
- **Location:** `public/app.js`
- **Tests:** `tests/qa/test_qa_a11y.py::test_review_step_has_no_serious_axe_violations`
- **Reproduction steps:**
  1. Reach review step
  2. Run axe-core
  3. Rule 'label' fails for #promo-code
- **Evidence:** [`ev-c57c9c806572`](artifacts/ev-c57c9c806572-pytest-output.log), [`ev-624d1b691f47`](artifacts/ev-624d1b691f47-pytest-report.jsonl), [`ev-3f3c104a1ac7`](artifacts/ev-3f3c104a1ac7-junit.xml), [`ev-cc46d26ef7ce`](artifacts/ev-cc46d26ef7ce-tests-qa-test-qa-a11y-py-test-review-step-has-no-serious-axe.png)
- **Verification V-96aad409:** CONFIRMED by qa-superteam:independent-verification-engineer via independent-rerun — Independent rerun of tests/qa/test_qa_a11y.py::test_review_step_has_no_serious_axe_violations: consistent failure; screenshots attached.

### F-5ce652ae · Removing a promo code keeps the discount in the total

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
- **Evidence:** [`ev-34afeef02eea`](artifacts/ev-34afeef02eea-pytest-output.log), [`ev-4ded86b1d3e4`](artifacts/ev-4ded86b1d3e4-pytest-report.jsonl), [`ev-47fbc48c1187`](artifacts/ev-47fbc48c1187-junit.xml), [`ev-d18f94779aae`](artifacts/ev-d18f94779aae-tests-qa-test-qa-journeys-py-test-promo-apply-then-remove-re.png), [`ev-8679a631d61a`](artifacts/ev-8679a631d61a-tests-qa-test-qa-journeys-py-test-recover-from-postal-code-e.png)

## Test executions

| Execution | Adapter | Label / groups | Status | P/F/E/S/B/NR/I | Duration | Note |
|---|---|---|---|---|---|---|
| `ex-d474b03df9d6` | pytest | existing Playwright suite [existing-suite] | **PASSED** | 6/0/0/0/0/0/0 | 2.6s |  |
| `ex-75b5494fe2e1` | pytest | journeys [critical-journeys] | **FAILED** | 5/2/0/0/0/0/0 | 12.0s |  |
| `ex-ab82a6a9e35a` | pytest | axe on app states [accessibility] | **FAILED** | 3/1/0/0/0/0/0 | 2.5s |  |
| `ex-cce3c25530e3` | axe | axe landing page (375px) [accessibility] | **PASSED** | 25/0/0/0/0/0/0 | 1.5s |  |
| `ex-68ddd90b5fd0` | pytest | reproduce tests/qa/test_qa_journeys.py::test_recover_from_postal_code_error_and… | **FAILED** | 0/1/0/0/0/0/0 | 4.4s |  |
| `ex-5436e6d13420` | pytest | reproduce tests/qa/test_qa_journeys.py::test_recover_from_postal_code_error_and… | **FAILED** | 0/1/0/0/0/0/0 | 4.4s |  |
| `ex-331bce68cca7` | pytest | reproduce tests/qa/test_qa_journeys.py::test_recover_from_postal_code_error_and… | **FAILED** | 0/1/0/0/0/0/0 | 4.4s |  |
| `ex-dcdc0413d1cf` | pytest | reproduce tests/qa/test_qa_journeys.py::test_promo_apply_then_remove_restores_t… | **FAILED** | 0/1/0/0/0/0/0 | 6.4s |  |
| `ex-0630dc520de7` | pytest | reproduce tests/qa/test_qa_journeys.py::test_promo_apply_then_remove_restores_t… | **FAILED** | 0/1/0/0/0/0/0 | 6.4s |  |
| `ex-bbd9f0888023` | pytest | reproduce tests/qa/test_qa_journeys.py::test_promo_apply_then_remove_restores_t… | **FAILED** | 0/1/0/0/0/0/0 | 6.4s |  |
| `ex-4f34e3091dc0` | pytest | reproduce tests/qa/test_qa_a11y.py::test_review_step_has_no_serious_axe_violati… | **FAILED** | 0/1/0/0/0/0/0 | 1.4s |  |
| `ex-128127676bb5` | pytest | reproduce tests/qa/test_qa_a11y.py::test_review_step_has_no_serious_axe_violati… | **FAILED** | 0/1/0/0/0/0/0 | 1.4s |  |
| `ex-1e5d97b51965` | pytest | reproduce tests/qa/test_qa_a11y.py::test_review_step_has_no_serious_axe_violati… | **FAILED** | 0/1/0/0/0/0/0 | 1.4s |  |

<details><summary>Failing, errored and inconclusive results (3)</summary>

- **FAILED** `tests/qa/test_qa_journeys.py::test_recover_from_postal_code_error_and_complete_checkout` (ex-75b5494fe2e1): checkout = <conftest.Checkout object at 0x7a45a095ac90>      def test_recover_from_postal_code_error_and_complete_checkout(checkout):         page = checkout.page         checkout.open().fill_contact()              postal = page.get_by_test_id("postal-code")         continue_button = page.get_by_test_id("shipping-continue")         postal_error = page.locator("#postal-code-error")              po…
- **FAILED** `tests/qa/test_qa_journeys.py::test_promo_apply_then_remove_restores_total` (ex-75b5494fe2e1): checkout = <conftest.Checkout object at 0x7a459fece480>      def test_promo_apply_then_remove_restores_total(checkout):         page = checkout.page         checkout.to_review(country="US", postal="94107")              total = page.get_by_test_id("total")         expect(page.get_by_test_id("subtotal")).to_have_text("$80.00")         expect(page.get_by_test_id("shipping-cost")).to_have_text("$5.00…
- **FAILED** `tests/qa/test_qa_a11y.py::test_review_step_has_no_serious_axe_violations` (ex-ab82a6a9e35a): checkout = <conftest.Checkout object at 0x7eb7a9866930> axe_path = PosixPath('<project>/node_modules/axe-core/axe.min.js')      def test_review_step_has_no_serious_axe_violations(checkout, axe_path: Path):         checkout.to_review()         expect(checkout.page.get_by_test_id("promo-input")).to_be_visible()              violations = blocking(run_axe(checkout.p…

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
- Platform: Linux-7.0.0-43-generic-x86_64 · Python 3.12.3 · CI: False · git HEAD `4fb3dc41f2ff` dirty=False
- Tools: pytest `pytest 9.0.2`

## Evidence index

| Artifact | Kind | Path | sha256 | Redactions |
|---|---|---|---|---|
| `ev-010f9dea074c` | log | [ev-010f9dea074c-pytest-output.log](artifacts/ev-010f9dea074c-pytest-output.log) | `010f9dea074c29f7` | 0 |
| `ev-0966a69f29d0` | screenshot | [ev-0966a69f29d0-http-127-0-0-1-45691.png](artifacts/ev-0966a69f29d0-http-127-0-0-1-45691.png) | `0966a69f29d025c6` | 0 |
| `ev-0a83fe714214` | log | [ev-0a83fe714214-pytest-output.log](artifacts/ev-0a83fe714214-pytest-output.log) | `0a83fe71421486ce` | 0 |
| `ev-10e8143b58b9` | junit | [ev-10e8143b58b9-junit.xml](artifacts/ev-10e8143b58b9-junit.xml) | `10e8143b58b94626` | 0 |
| `ev-130d647e6abb` | junit | [ev-130d647e6abb-junit.xml](artifacts/ev-130d647e6abb-junit.xml) | `130d647e6abb69d8` | 0 |
| `ev-1f0428711779` | report | [ev-1f0428711779-pytest-report.jsonl](artifacts/ev-1f0428711779-pytest-report.jsonl) | `1f0428711779d24a` | 0 |
| `ev-217ca6e4728f` | screenshot | [ev-217ca6e4728f-tests-qa-test-qa-journeys-py-test-promo-apply-then-remove-re.png](artifacts/ev-217ca6e4728f-tests-qa-test-qa-journeys-py-test-promo-apply-then-remove-re.png) | `217ca6e4728f5353` | 0 |
| `ev-2984fcc37dc4` | report | [ev-2984fcc37dc4-axe-result.json](artifacts/ev-2984fcc37dc4-axe-result.json) | `2984fcc37dc49d85` | 0 |
| `ev-2bc959b25f8e` | report | [ev-2bc959b25f8e-pytest-report.jsonl](artifacts/ev-2bc959b25f8e-pytest-report.jsonl) | `2bc959b25f8ee8a6` | 0 |
| `ev-2c16b29ef450` | screenshot | [ev-2c16b29ef450-tests-qa-test-qa-a11y-py-test-review-step-has-no-serious-axe.png](artifacts/ev-2c16b29ef450-tests-qa-test-qa-a11y-py-test-review-step-has-no-serious-axe.png) | `2c16b29ef4504aa5` | 0 |
| `ev-34afeef02eea` | log | [ev-34afeef02eea-pytest-output.log](artifacts/ev-34afeef02eea-pytest-output.log) | `34afeef02eea1f47` | 0 |
| `ev-3c688c55735e` | report | [ev-3c688c55735e-pytest-report.jsonl](artifacts/ev-3c688c55735e-pytest-report.jsonl) | `3c688c55735eda61` | 0 |
| `ev-3f3c104a1ac7` | junit | [ev-3f3c104a1ac7-junit.xml](artifacts/ev-3f3c104a1ac7-junit.xml) | `3f3c104a1ac73f98` | 0 |
| `ev-416bc97d33ec` | log | [ev-416bc97d33ec-pytest-output.log](artifacts/ev-416bc97d33ec-pytest-output.log) | `416bc97d33ec7477` | 0 |
| `ev-42dee9287c41` | junit | [ev-42dee9287c41-junit.xml](artifacts/ev-42dee9287c41-junit.xml) | `42dee9287c41132f` | 0 |
| `ev-4368e01e61ca` | log | [ev-4368e01e61ca-pytest-output.log](artifacts/ev-4368e01e61ca-pytest-output.log) | `4368e01e61cadd75` | 0 |
| `ev-47fbc48c1187` | junit | [ev-47fbc48c1187-junit.xml](artifacts/ev-47fbc48c1187-junit.xml) | `47fbc48c1187aca2` | 0 |
| `ev-4ded86b1d3e4` | report | [ev-4ded86b1d3e4-pytest-report.jsonl](artifacts/ev-4ded86b1d3e4-pytest-report.jsonl) | `4ded86b1d3e44e7d` | 0 |
| `ev-5007c6fb4db2` | report | [ev-5007c6fb4db2-pytest-report.jsonl](artifacts/ev-5007c6fb4db2-pytest-report.jsonl) | `5007c6fb4db28de8` | 0 |
| `ev-5255ea626a0f` | junit | [ev-5255ea626a0f-junit.xml](artifacts/ev-5255ea626a0f-junit.xml) | `5255ea626a0fd50d` | 0 |
| `ev-5ec3925f7d9b` | junit | [ev-5ec3925f7d9b-junit.xml](artifacts/ev-5ec3925f7d9b-junit.xml) | `5ec3925f7d9b630a` | 0 |
| `ev-624d1b691f47` | report | [ev-624d1b691f47-pytest-report.jsonl](artifacts/ev-624d1b691f47-pytest-report.jsonl) | `624d1b691f47d0a4` | 0 |
| `ev-645bec591d95` | log | [ev-645bec591d95-pytest-output.log](artifacts/ev-645bec591d95-pytest-output.log) | `645bec591d953eff` | 0 |
| `ev-6476b914b3ac` | report | [ev-6476b914b3ac-pytest-report.jsonl](artifacts/ev-6476b914b3ac-pytest-report.jsonl) | `6476b914b3ac1f1c` | 0 |
| `ev-72d67b16111f` | log | [ev-72d67b16111f-pytest-output.log](artifacts/ev-72d67b16111f-pytest-output.log) | `72d67b16111f07a9` | 0 |
| `ev-72fa857f5db9` | log | [ev-72fa857f5db9-pytest-output.log](artifacts/ev-72fa857f5db9-pytest-output.log) | `72fa857f5db9a7d7` | 0 |
| `ev-7a5a5825577c` | report | [ev-7a5a5825577c-pytest-report.jsonl](artifacts/ev-7a5a5825577c-pytest-report.jsonl) | `7a5a5825577cf2d2` | 0 |
| `ev-7db945a62325` | junit | [ev-7db945a62325-junit.xml](artifacts/ev-7db945a62325-junit.xml) | `7db945a623253a8b` | 0 |
| `ev-8679a631d61a` | screenshot | [ev-8679a631d61a-tests-qa-test-qa-journeys-py-test-recover-from-postal-code-e.png](artifacts/ev-8679a631d61a-tests-qa-test-qa-journeys-py-test-recover-from-postal-code-e.png) | `8679a631d61a36cc` | 0 |
| `ev-8751660e89aa` | report | [ev-8751660e89aa-pytest-report.jsonl](artifacts/ev-8751660e89aa-pytest-report.jsonl) | `8751660e89aa6bd5` | 0 |
| `ev-8cd182346c7e` | report | [ev-8cd182346c7e-pytest-report.jsonl](artifacts/ev-8cd182346c7e-pytest-report.jsonl) | `8cd182346c7e82e2` | 0 |
| `ev-9823c2151ec7` | log | [ev-9823c2151ec7-pytest-output.log](artifacts/ev-9823c2151ec7-pytest-output.log) | `9823c2151ec7594e` | 0 |
| `ev-a6b0b57251ef` | junit | [ev-a6b0b57251ef-junit.xml](artifacts/ev-a6b0b57251ef-junit.xml) | `a6b0b57251ef79ec` | 0 |
| `ev-afe64e85169a` | report | [ev-afe64e85169a-pytest-report.jsonl](artifacts/ev-afe64e85169a-pytest-report.jsonl) | `afe64e85169a7e67` | 0 |
| `ev-bc873b8a8f97` | log | [ev-bc873b8a8f97-axe-output.log](artifacts/ev-bc873b8a8f97-axe-output.log) | `bc873b8a8f978846` | 0 |
| `ev-c4406964033d` | junit | [ev-c4406964033d-junit.xml](artifacts/ev-c4406964033d-junit.xml) | `c4406964033da1fd` | 0 |
| `ev-c57c9c806572` | log | [ev-c57c9c806572-pytest-output.log](artifacts/ev-c57c9c806572-pytest-output.log) | `c57c9c8065728e7c` | 0 |
| `ev-cac0a1fe0186` | report | [ev-cac0a1fe0186-pytest-report.jsonl](artifacts/ev-cac0a1fe0186-pytest-report.jsonl) | `cac0a1fe01863bef` | 0 |
| `ev-cc46d26ef7ce` | screenshot | [ev-cc46d26ef7ce-tests-qa-test-qa-a11y-py-test-review-step-has-no-serious-axe.png](artifacts/ev-cc46d26ef7ce-tests-qa-test-qa-a11y-py-test-review-step-has-no-serious-axe.png) | `cc46d26ef7ce2703` | 0 |
| `ev-cc7ee25222f2` | junit | [ev-cc7ee25222f2-junit.xml](artifacts/ev-cc7ee25222f2-junit.xml) | `cc7ee25222f2188f` | 0 |
| `ev-d18f94779aae` | screenshot | [ev-d18f94779aae-tests-qa-test-qa-journeys-py-test-promo-apply-then-remove-re.png](artifacts/ev-d18f94779aae-tests-qa-test-qa-journeys-py-test-promo-apply-then-remove-re.png) | `d18f94779aae9e8e` | 0 |
| `ev-e4f92950d29f` | log | [ev-e4f92950d29f-pytest-output.log](artifacts/ev-e4f92950d29f-pytest-output.log) | `e4f92950d29f1dfc` | 0 |
| `ev-fa62f86e0d31` | junit | [ev-fa62f86e0d31-junit.xml](artifacts/ev-fa62f86e0d31-junit.xml) | `fa62f86e0d31152f` | 0 |
| `ev-fd335953b385` | log | [ev-fd335953b385-pytest-output.log](artifacts/ev-fd335953b385-pytest-output.log) | `fd335953b3859502` | 0 |

_Generated by QA Superteam from recorded evidence. Statuses are normalized tool results; finding statuses are derived from reproduction and verification records; the decision is computed by the deterministic policy engine._
