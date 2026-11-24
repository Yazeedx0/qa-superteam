# Oracles and oracle anti-patterns

An oracle is how a test decides pass or fail. A case without one is not a test. Prefer
the strongest oracle the sources support, and combine a primary oracle with the
implicit one (no crash, no 5xx).

## Oracle types

| Type | What it is | Use when | Watch out for |
|---|---|---|---|
| Specified | the expected value is written in a requirement, acceptance criterion or table | the source gives concrete values | cite the source; recompute derived values by hand |
| Derived (model) | an independent, simpler model written from the spec computes the expected value: an integer formula, a state table, a reference function | many inputs, property-based tests | the model must come from the spec, not from the code under test, and stay simpler than it |
| Metamorphic | a relation between outputs of related inputs (prefix, permutation, scaling, symmetry) | no exact expected output: search, ranking, ML, numerical code, rendering | each relation must follow from the spec or algorithm; validate it on known cases; invalid relations produce false defects |
| Differential | compare against another implementation: previous release, alternative library, a second path to the same value (API vs UI, batch vs single) | refactors, migrations, duplicated logic | both may share a bug; the old version may be wrong; differences need triage, not automatic failure |
| Invariant | a property that must hold after every step | business rules over sequences, concurrency | needs observable state; also check after rejected operations (nothing changed) |
| Implicit | crash, unhandled exception, 5xx, timeout, console error, accessibility violation | always, as a secondary oracle; fuzzing; exploratory work | weak alone: a 200 with wrong data passes |
| Human (judgment) | a person, or a calibrated model judge, applies a written rubric | tone, clarity, UX, answer quality of LLM systems | write the rubric first; results stay INCONCLUSIVE until judged; model judges need calibration (`qast ai-eval calibrate`) |

**Complete oracle checklist:** what is returned; what is persisted; what must not change
(other accounts, other users' data, totals); what is emitted (events, emails, tool
calls); what must not be revealed (existence of other users' resources, internals,
secrets).

## Anti-patterns

| Anti-pattern | Example | Why it fails | Fix |
|---|---|---|---|
| Assertion-free test | calls the endpoint, asserts nothing or only "no exception" | passes when behaviour is wrong | assert the outcome |
| Status-only assertion | `assert r.status_code == 200` | wrong body or state passes | assert body fields and persisted state |
| Mirror-the-implementation oracle | `expected = calc_fee(amount)`, or the same formula copied into the test, or importing the production helper to build the expectation | reproduces the bug in the expectation | specified values, or an independent model written from the spec |
| Blessed current output | a snapshot or golden file captured from today's build and accepted without review | freezes the defect | a reviewed source of truth; never update a baseline to make a test pass |
| Over-mocking | mocking the store in a transaction test, the auth dependency in an authz test, the HTTP client in a contract test | the test checks mock wiring, not behaviour | use the real component at the level that can observe the failure; mock only true external boundaries |
| Call assertions instead of outcomes | `repo.save.assert_called_once()` | passes or breaks regardless of behaviour | assert observable outcomes; assert calls only for effects on external systems ("refund API called once with 4999") |
| Tautology | `assert x == x`; comparing a response with a re-read from the same cache | cannot fail | compare against an independent source |
| Over-broad exception | `pytest.raises(Exception)`, `toThrow()` without a type | the wrong error passes | assert the specific type and message or status |
| Lenient tolerance on exact values | `approx(rel=0.01)` for money | cent errors pass | exact integer equality for money and counts |
| Truthiness | `assert result`, `expect(x).toBeTruthy()` on structured values | any non-empty value passes | assert specific fields |
| Conditional assertion | `if r.status_code == 200: assert ...` | the check silently disappears | assert the precondition, then the outcome |
| Catch-and-pass | `try: ... except Exception: pass` in a test | failures are swallowed | let them fail |
| Shared or ordered state | test B relies on data test A created | results depend on order | fresh fixtures per test |
| Sleeps and retries as synchronization | `sleep(2)`; retrying until green | flaky, and retries hide real intermittent defects | wait on an observable condition; report retries; flaky ⇒ INCONCLUSIVE |
| Testing private helpers | asserting on an internal function no user reaches | refactors break tests, behaviour stays untested | test through the public behaviour |

## The "would it fail?" check

For every new or proposed case, name the specific defect that makes it fail: "fee
rounded down at 500 cents", "user B receives A's order", "second replay debits again".
If you cannot name one, the oracle is too weak. A quick mental mutation helps: delete
the guarding line or flip the comparison in the code under test; would this test
notice?

## Nondeterministic systems

Assert properties, not exact text (required facts present, forbidden content absent,
citations ⊆ retrieved, tool-call order). Sample repeatedly
(`qast exec ai-eval --samples N`); disagreement across samples is INCONCLUSIVE, never a
pass.
