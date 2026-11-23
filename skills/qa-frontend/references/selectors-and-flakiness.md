# Stable selectors and flake-free browser tests

A flaky browser test produces INCONCLUSIVE evidence and wastes the verifier's time.
Most flakiness is designed in; avoid it while writing, not by retrying afterwards.

## Selector priority

| Priority | Python | TypeScript | Why |
|---|---|---|---|
| 1 | `page.get_by_role("button", name="Confirm booking")` | `page.getByRole('button', { name: 'Confirm booking' })` | What users and assistive tech perceive; doubles as an accessibility check |
| 2 | `page.get_by_label("Email")` | `page.getByLabel('Email')` | Fails if the label association breaks (a real defect) |
| 3 | `page.get_by_placeholder(...)`, `get_by_text(...)` | `getByPlaceholder`, `getByText` | Visible text; ambiguous on repeated text |
| 4 | `page.get_by_test_id("booking-ref")` | `page.getByTestId('booking-ref')` | Stable, locale-independent; use for non-semantic output and for RTL/i18n runs |
| Avoid | `.css-1x2y3z`, `div > div:nth-child(3)`, XPath by position | same | Breaks on any layout or styling change |

- Text-based locators break in other locales: in RTL/i18n runs use roles with translated
  names from the app's string table, or test ids.
- Scope before matching: `page.get_by_test_id("summary").get_by_text("$120.00")`.
- A locator that matches several elements fails in strict mode: that is useful
  information (ambiguous UI), not something to silence with `.first` by reflex.
- If the project uses `data-test`/`data-cy` instead of `data-testid`, configure
  `selectors.set_test_id_attribute("data-test")` (Python) / `testIdAttribute` (TS).

## Waiting: let Playwright wait, never sleep

| Instead of | Use |
|---|---|
| `time.sleep(2)`, `page.wait_for_timeout(2000)` | A web-first assertion: `expect(locator).to_be_visible()` / `toBeVisible()` (auto-retries up to the timeout) |
| `assert locator.is_visible()` (checks once) | `expect(locator).to_be_visible()` |
| `assert page.url == ".../review"` | `expect(page).to_have_url(re.compile("/review$"))` |
| Polling a counter in a loop | `with page.expect_response("**/api/bookings") as r:` / `page.waitForResponse(...)` |
| `wait_for_load_state("networkidle")` as a general wait | An assertion on the UI state the next step needs |
| Sleeping for an animation | Assert the end state; disable animations via `reduced_motion="reduce"` in the context if the app honours it |

Actions (`click`, `fill`) already wait for the element to be attached, visible, stable,
enabled and receiving events. `force=True` skips those checks: use it only when the test
is deliberately checking what happens on an "impossible" interaction, and say so.

Proving that something does **not** happen (no second request, no error) needs a
bounded observation window: complete the flow to a later observable state (the
confirmation appears) and then assert the count, rather than sleeping.

## Isolation

- One browser context per test (fresh cookies, storage, cache). Never share a page
  between tests.
- Each test creates its own data through the UI or API; no dependence on test order or
  on data left by another test.
- Server state shared across tests (reference counters, in-memory baskets) must not be part of
  an oracle unless the test created it (`BK-\d+`, not `BK-1001`).
- Clock-dependent UI: `page.clock.set_fixed_time(...)` / `page.clock.install(...)`
  (Playwright ≥ 1.45) instead of waiting for real time.

## Retries and flakiness evidence

- Evidence runs use `retries: 0` (or the project's value, stated in the summary). A test
  that passes only on retry is reported by the Node adapter as `flaky` → INCONCLUSIVE.
- Re-run a suspicious failure with `qast reproduce --test "<id>" --times 3` (Python) or
  `qast reproduce --adapter playwright --test "<file>::<title> [<project>]" --times 3 -- <file> -g "<title>"`
  (Node). `intermittent` ⇒ INCONCLUSIVE: investigate the test (race, shared state,
  timing) before calling it a product defect; product flakiness (e.g. a real race in
  the app) needs a deterministic reproduction (hold the network request, control the
  clock) to become a finding.
- Never add sleeps or raise timeouts to make an intermittent test pass and then report
  the pass.

## Environment failures are not product failures

| Symptom | Classification |
|---|---|
| `Executable doesn't exist at .../chromium...` / browser launch failed | ERROR (environment): install browsers (`python -m playwright install chromium` / `npx playwright install chromium`) or set the project's executable override; no finding |
| App server did not start / port in use | ERROR (environment) |
| `net::ERR_CONNECTION_REFUSED` on `goto` | ERROR unless the test deliberately stopped the server |
| Timeout waiting for an element that the requirement says must appear | FAILED (product), after checking the screenshot/trace shows the app in the expected step |
| Strict-mode violation (locator matched 2 elements) | Usually a test defect; a product defect only if the UI duplicates content it must not |

The Node adapter currently reports browser-launch failures as FAILED results: read the
message before treating any FAILED as a product defect.
