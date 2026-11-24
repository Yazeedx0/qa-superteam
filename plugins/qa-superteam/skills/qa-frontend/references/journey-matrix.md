# Journey coverage matrix

For each critical journey (from the requirements/journey docs, else inferred from the
UI and labelled `inferred`), decide which rows apply. Each applicable row is a test case
with an oracle; rows that do not apply are listed with a reason. Business-essential
journeys go in policy group `critical-journeys`.

| Row | Question the test answers | Typical oracle |
|---|---|---|
| Happy path | Can a user with valid input finish the journey? | Final state visible (confirmation, saved record) with the data entered |
| Validation per field | Is each invalid input rejected at the right moment with a message? | Message text/role, `aria-invalid`, `aria-describedby` link, step does not advance |
| **Recovery** | After an error, can the user fix it and finish **in the same page session**? | Error clears (on input or on submit, per requirement), entered data kept, journey completes without reload |
| Dependent-field recovery | Does changing one field re-validate fields that depend on it? | E.g. country change re-checks postal code format; stale error not left behind, stale "valid" not accepted |
| Navigation | Back/forward/step links keep data; deep links to later steps handled | Fields refilled; incomplete steps cannot be skipped |
| Persistence | Reload/new tab resumes correctly; data cleared when it should be | Same step and values after reload; fresh start after completion |
| Corrupted state | Malformed/outdated stored state does not break the app | App loads, falls back to a clean state, no `pageerror` |
| Network failure | Connection loss, 4xx/5xx, timeouts during submit | Error message, data kept, retry possible, no duplicate submission |
| Loading/double submit | Rapid repeated actions while a request is pending | Exactly one request/side effect |
| Totals and money | Displayed amounts equal the amounts sent/charged | Request body matches what the UI showed (intercept with `page.route`) |
| Responsive 375 px | Every step and error state fits; actions reachable | `scrollWidth <= clientWidth`, primary action inside viewport, long text wraps |
| RTL / locales | `dir`/`lang`, mirrored layout, all strings translated, bidi content intact | Attribute values, computed `direction`, label/field edges, no leftover source-language strings |
| Keyboard | Journey completes with keyboard only; focus moves sensibly | Hand-off to `qa-accessibility` (it owns focus/a11y oracles) |
| Accessibility states | Each step and error state scanned | Hand-off to `qa-accessibility` with the steps to reach each state |
| Visual | Only with existing valid baselines | See `playwright-ts-patterns.md` (never create/update baselines) |
| Console health | No uncaught exceptions during the journey | `pageerror` list empty |

## Prioritising

1. Rows that touch money, data loss or the ability to complete the essential journey.
2. Rows the requirements state explicitly (they have the strongest oracles).
3. Rows where the existing suite has nothing (check `tests/` first; do not duplicate).
4. Variants (locales × viewports) last: run the essential journey in each supported
   locale and the narrowest viewport, not every row in every combination.

## Writing the oracle from the requirement

Copy the requirement's wording into the test name or a comment, and assert exactly what
it says. When it is silent (e.g. "does the error clear on input or on submit?"), assert
only what every reasonable reading agrees on (the error is gone before the user can
continue) and record the ambiguity with the plan, rather than encoding today's
behaviour.
