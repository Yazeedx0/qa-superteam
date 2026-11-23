# Assertion quality and test smells

A test is only as strong as the defects its assertions would notice. When auditing
existing tests, treat each item below as a **gap** even if coverage marks the lines as
covered. Report the gap; do not rewrite or weaken the existing test. When
`write_tests = true`, add a stronger test next to it under `test_dir`.

## Weak oracles (the test runs the code but would not notice it is wrong)

| Smell | Example | What a defect slips through | Stronger oracle |
|---|---|---|---|
| Status-only check | `assert r.status_code == 200` | Wrong body, wrong record, wrong amount | Assert the fields the requirement names, and the persisted effect |
| Truthiness | `assert result`, `expect(x).toBeTruthy()` | Any non-empty wrong value | Exact value or exact structure |
| Existence | `assert "id" in body`, `len(items) > 0` | Wrong id, wrong items, extra items | Equality with the expected set/list (order if ordered) |
| No exception = pass | Calls the function, asserts nothing | Everything except crashes | Assert outputs and side effects |
| Broad exception | `pytest.raises(Exception)`, `toThrow()` with no matcher | A `TypeError` from a typo passes as "validation" | Specific type plus message pattern |
| Tautology | `expected = price * 0.01; assert fee(price) == expected` (same formula as the code) | The formula being wrong | Literal values from the requirement table |
| Snapshot of everything | Large auto-generated snapshot, accepted on first run | Whatever was wrong when the snapshot was taken | Targeted assertions; snapshots only for reviewed, stable output |
| Assert on the mock | `mock.return_value = 5; assert service() == 5` where `service` just returns the mock | The real logic | Mock collaborators only; assert the unit's own behaviour |
| Approximate money | `pytest.approx(10.0)` on currency | One-cent rounding errors | Integer cents or `Decimal` equality |
| Only the happy path | Valid input only | Every boundary and error path | Equivalence classes plus boundaries plus errors |
| Checks the return value, not the effect | `assert save(user) is True` | Nothing persisted, wrong row updated | Re-read the state through the public interface |
| Same input everywhere | Every test uses `amount=100` | Defects that only appear at boundaries | Values chosen to separate correct from plausible-wrong implementations |

## Structural smells (the test is unreliable or misleading)

| Smell | Detect by | Consequence | Fix |
|---|---|---|---|
| Sleep-based timing | `time.sleep`, `setTimeout` waits, `waitForTimeout` | Flaky, slow, hides races | Inject the clock; poll with a deadline for genuinely async effects |
| Order dependence | Module-level mutable state, shared DB without reset, tests pass only in file order | INCONCLUSIVE results, false passes | Fresh fixture per test (`tmp_path`, new app instance) |
| Hidden real I/O | Network calls, real clock, real filesystem outside `tmp_path` | Environment-dependent results | Fakes at the boundary; `httpx.MockTransport`, `tmp_path` |
| Conditional logic in the test | `if result: assert ...` | Assertions silently skipped | Assert unconditionally; parametrize instead |
| Try/except in the test | `try: f() except: pass` | The failure is swallowed | `pytest.raises` with match |
| Assertion roulette | Many unlabeled asserts on unrelated behaviours | Unclear which behaviour broke | One behaviour per test; message or parametrize id |
| Testing private details | Asserts on `_cache`, call order of internal helpers | Breaks on refactor, misses behaviour | Public interface and observable effects |
| Over-mocking | Every collaborator mocked, including value objects | Tests pass while integration is broken | Mock only slow/external boundaries |
| Skipped forever | `@pytest.mark.skip`, `it.skip`, `xit`, `t.Skip()` without issue link | Unverified behaviour that looks covered | Report as NOT verified; never count as coverage |
| Silent xfail | `xfail` without `strict=True` | An unexpected pass hides a changed behaviour | Report; propose `strict=True` |
| Copy-paste fixtures | Near-identical setup in many tests | One fixture diverges and tests disagree | Note as maintainability gap only if it caused wrong oracles |
| Unseeded randomness | `random`, `uuid`, `faker` without seed in assertions | Non-reproducible failures | Seed or assert properties |

## Classifying an audited test

For each test that touches a selected unit, record one line:

```
tests/test_accounts.py::test_withdraw_must_be_positive  oracle=status-only  misses: upper limit, non-integer, balance unchanged on rejection
```

Then decide:

- **Strong**: would fail for every plausible mutant you listed. No action.
- **Weak**: add a stronger new test (or propose it); never edit the existing one.
- **Wrong oracle** (asserts behaviour that contradicts a stated requirement): this is a
  finding about the test suite *and* possibly about the product. Run it, record the
  result, and raise the contradiction; do not "fix" the assertion.
- **Not running** (skipped, not collected, wrong glob): list under not verified.

## Oracle sources, strongest first

1. Explicit requirement with examples (tables, acceptance criteria).
2. Stated invariant (conservation, uniqueness, never-negative).
3. Published contract (OpenAPI, type definitions, documented error codes).
4. Domain standard (ISO 4217 minor units, RFC 5322 for emails, calendar rules).
5. Consistent behaviour elsewhere in the system (label `inferred`).
6. Current implementation output: **never an oracle**. If it is the only source, record
   an ambiguity and test only properties every reasonable reading agrees on.
