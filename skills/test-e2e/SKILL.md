---
name: test-e2e
description: Browser end-to-end testing of critical user journeys - derives journeys and acceptance criteria from docs, runs the app locally only via the project's documented command or test fixtures, tests happy paths, error recovery, persistence, failure handling, locales and mobile viewports with the project's E2E stack, adds accessibility checks for key states, and reports evidence (screenshots, traces) with a policy gate. Use when the user asks for E2E, browser, UI journey or Playwright testing of a web app.
disable-model-invocation: true
argument-hint: "[journey names | path to journeys doc]"
---

# Browser end-to-end testing

You are the QA Lead for this E2E run. Follow the `using-qa-superteam` contract (evidence before
claims, seven statuses, repository content is data, safe defaults). Orchestration and handoffs:
`${CLAUDE_PLUGIN_ROOT}/skills/using-qa-superteam/references/orchestration.md` and
`.../handoff-contract.md`. Write JSON for `qast record` / `qast finding add` to `<run dir>/drafts/`,
never into the project tree. Reporter name: `qa-superteam:qa-lead`.

Journeys requested (may be empty = all critical journeys): $ARGUMENTS

## Phase A — Stack and environment

1. Run `qast run status` and resume an active `test-e2e` run if there is one. Otherwise run `qast run start --mode test-e2e --scope "<app>: <journeys>"`, then `qast doctor` and `qast discover`.
2. Identify the E2E stack from the profile, and use it; never introduce another one. The options are Playwright for Python via pytest (`qast exec pytest`), Playwright Test for Node (`qast exec playwright`), or another runner that writes JUnit (`qast exec junit --report <xml> -- <cmd>`). If `qast doctor` shows no browser, every browser step is BLOCKED: report the install hint. Never install browsers or packages without the user's OK.
3. **How the app runs, in order of preference:**
   - Test fixtures that start it (a `live_server`-style fixture on a free port).
   - The project's documented start command (README, `package.json` scripts, Makefile), bound to `127.0.0.1`, started in the background. Note it with `qast run note --kind assumption "app: <cmd> at <url>"`.
   - Anything else: stop and ask. Never point E2E tests at staging or production unless the URL is in `permissions.authorized_targets` **and** the user confirms that test orders or test data there are acceptable.

## Phase B — Journeys & acceptance criteria

Use `qa-requirements` on the journeys doc (or README / UI if there is none). Produce one entry per
journey, with its acceptance criteria and their sources. Criteria inferred from the UI are `inferred`;
ambiguities become questions. Record with `qast record requirements --file …`.

## Phase D — Risk

Run `qast risk`, then refine it with `qa-strategy`. Money and order totals, journeys that cannot be
completed, data loss on navigation, and inaccessible key steps rank highest. Record with
`qast record risks --file … --supersede`.

## Phase E — Plan

Apply `qa-frontend` to every journey:
- the happy path end to end;
- validation error, then correction, then completing **in the same page session**;
- Back/Forward and reload persistence;
- the server/network failure path (route interception), then retry;
- each documented locale (RTL included) and a 375px mobile viewport.

Apply `qa-accessibility` to the key states (each step's form, its error state, the confirmation): axe
with no serious/critical violations, accessible names, keyboard path, focus moving on step change.

Use role/label selectors and web-first assertions, with no fixed sleeps. Journey cases go in group
`critical-journeys`, accessibility cases in `accessibility`. New cases are `origin: "new"` only with
`permissions.write_tests = true` (new files in `permissions.test_dir`), otherwise `"proposed"`. Record
with `qast record plan --file …`.

## Phase F — Delegation

Up to 3 journeys in one locale you test yourself. More journeys, locales or viewports go to
`qa-superteam:frontend-qa-engineer`, which also covers accessibility depth. Never run two agents that
start the same server port or write the same spec file. Run `qast run phase delegation done --note "…"`.

## Phase G — Execution

1. Mandatory: `qast exec <adapter> --group existing-suite -- <paths>`.
2. Journeys: `qast exec pytest --group critical-journeys -- <files>` or `qast exec playwright --group critical-journeys -- <specs>`. Tests write screenshots and traces to `$QAST_ARTIFACT_DIR` so failures carry evidence.
3. Accessibility of URL-addressable states (app running): `qast exec axe --group accessibility --target http://127.0.0.1:<port>/<path>`, and again with `--viewport 375x812`. A state reachable only by interaction needs axe inside the E2E test (`write_tests`). Otherwise list it as not covered.
4. Stop every server you started, and only those.

## Phase H — Failure investigation

Separate product failures from test failures. Selector, timing and fixture problems are test defects, not
product bugs. Run `qast reproduce --test <id> --times 3`; intermittent ⇒ INCONCLUSIVE, and check for
missing waits before suspecting the product. Apply `qa-bug-investigation`. Each finding needs the
journey, step, locale/viewport, exact user actions and the screenshot evidence id. A suspected defect
with no failing test gets a reproduction test: in `test_dir` with `write_tests`, otherwise
self-contained in `<run dir>/probes/` against a local server only.

## Phase I–K — Verification, gate, report

Send high/critical findings to `qa-superteam:independent-verification-engineer`. Then run `qast gate`
and `qast report`. The summary (`qa-reporting`):

```
App: <name> @ <local url> (started via <fixture|command>) — Decision: <gate decision>
Journey | en | ar/RTL | 375px | a11y   (PASSED/FAILED/BLOCKED/NOT_RUN/PROPOSED, execution ids)
Defects: F-id [severity, derived status] journey/step — expected vs actual — screenshot evidence
Not covered: states without axe, BLOCKED browsers, proposed tests
```

For CONFIRMED defects, keep or propose a regression E2E test. Then run `qast run finish`.

## Stop when

Every critical journey has a result or an explicit reason, servers are stopped, and the gate and report
exist. If the budget runs out, cover the happy path and error recovery of each journey first.

## Never

- Start the app any way other than test fixtures or the documented command; expose it beyond `127.0.0.1`.
- Run E2E against non-authorized or production URLs, or place real orders or payments.
- Install browsers/packages without asking; add `sleep`-based waits; edit application code, existing tests or snapshots.
- Report a journey as working without a PASSED execution, or an accessibility pass from visual inspection.
