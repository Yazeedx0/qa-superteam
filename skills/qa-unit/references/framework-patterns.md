# Unit test patterns by framework

Use the framework, fixtures, naming and directory conventions the project already has.
The examples test a hypothetical `shop.pricing` module whose rules are documented as:
"fee = 1 % of the amount in cents, rounded **up**, minimum 1 cent; amounts are positive
integers". Every expected value below comes from that sentence, not from the code.

## pytest

### Boundaries and equivalence classes with readable ids

```python
import pytest

from shop.pricing import fee_cents


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        pytest.param(1, 1, id="floor-minimum-fee"),
        pytest.param(99, 1, id="below-1-percent-still-minimum"),
        pytest.param(100, 1, id="exact-1-percent"),
        pytest.param(101, 2, id="rounds-up-not-to-nearest"),
        pytest.param(150, 2, id="half-cent-rounds-up"),
        pytest.param(199, 2, id="just-below-next-cent"),
        pytest.param(10_000_000, 100_000, id="large-amount-no-float-drift"),
    ],
)
def test_fee_is_one_percent_rounded_up_with_1_cent_minimum(amount, expected):
    # Oracle: pricing rules, "1 %, rounded up, minimum 1 cent"
    assert fee_cents(amount) == expected
```

Pick rows that distinguish the plausible wrong implementations: `101` separates
round-up from round-to-nearest, `99` separates "minimum 1" from plain rounding, a large
value exposes float arithmetic.

### Invalid input: type and message

```python
@pytest.mark.parametrize("amount", [0, -1, 1.5, "100", None, True])
def test_fee_rejects_non_positive_or_non_integer_amounts(amount):
    with pytest.raises((ValueError, TypeError), match=r"(?i)amount"):
        fee_cents(amount)
```

`pytest.raises(Exception)` without `match` passes on any crash, including a typo inside
the function: always narrow the type and match the message. `True` is an `int` in
Python; decide from the requirement whether it must be rejected.

### Money, decimals and floats

```python
from decimal import Decimal

def test_total_uses_exact_decimal_arithmetic():
    assert order_total([Decimal("0.10"), Decimal("0.20")]) == Decimal("0.30")
```

Exact equality for money (integer cents or `Decimal`). Use `pytest.approx` only for
quantities that are genuinely floating point (ratios, physics), and set `rel`/`abs`
from the requirement's tolerance, not from whatever makes the test pass.

### Time: inject or patch the clock at its lookup site

```python
from datetime import datetime, timedelta, timezone

import shop.sessions as sessions

FIXED = datetime(2024, 3, 31, 23, 59, 59, tzinfo=timezone.utc)


def test_token_valid_until_exactly_24h(monkeypatch):
    monkeypatch.setattr(sessions, "utcnow", lambda: FIXED)
    token = sessions.issue(user_id=1)

    monkeypatch.setattr(sessions, "utcnow", lambda: FIXED + timedelta(hours=24) - timedelta(seconds=1))
    assert sessions.is_valid(token)

    monkeypatch.setattr(sessions, "utcnow", lambda: FIXED + timedelta(hours=24))
    assert not sessions.is_valid(token)
```

Patch the name the module under test actually calls (`shop.sessions.utcnow`), not
`datetime.datetime.now` globally. If the code calls `datetime.now()` inline and offers no
seam, report the missing seam as a testability gap; use `freezegun`/`time-machine` only
if the project already depends on one. Time edges worth a row: DST transitions
(`zoneinfo.ZoneInfo("America/New_York")`, 2024-03-10 02:30 does not exist), month end,
29 February, the exact expiry instant, time-zone-naive vs aware comparisons.

### Randomness

Inject `random.Random(seed)` or patch the module's RNG function; assert properties of
the output (range, uniqueness, distribution bounds for large N), never a specific value
copied from one run.

### State machines: legal and illegal transitions

```python
import pytest

from shop.orders import Order, IllegalTransition

LEGAL = {("pending", "paid"), ("paid", "shipped"), ("pending", "cancelled"), ("paid", "refunded")}
STATES = ["pending", "paid", "shipped", "cancelled", "refunded"]


@pytest.mark.parametrize("src", STATES)
@pytest.mark.parametrize("dst", STATES)
def test_transition_table(src, dst):
    order = Order(status=src)
    if (src, dst) in LEGAL:
        order.transition(dst)
        assert order.status == dst
    else:
        with pytest.raises(IllegalTransition):
            order.transition(dst)
        assert order.status == src  # a rejected transition changes nothing
```

The full cross product is cheap and finds the forgotten `shipped → cancelled`.

### Collaborators: mock at the boundary, with autospec

```python
from unittest import mock

import shop.checkout as checkout


def test_charge_failure_does_not_send_receipt():
    with mock.patch.object(checkout, "gateway", autospec=True) as gw, \
         mock.patch.object(checkout, "mailer", autospec=True) as mailer:
        gw.charge.side_effect = checkout.PaymentDeclined("card declined")
        with pytest.raises(checkout.PaymentDeclined):
            checkout.place_order(order_id=7, amount_cents=500)
    mailer.send_receipt.assert_not_called()
    gw.charge.assert_called_once_with(order_id=7, amount_cents=500)
```

Never mock the unit under test or the data structure it returns. `autospec=True` makes a
call with the wrong signature fail instead of silently passing. Use `pytest-mock`'s
`mocker` only if the project already uses it.

### Property-based (only when `hypothesis` is installed)

```python
from hypothesis import given, settings, strategies as st


@settings(database=None, max_examples=300)  # no example database written
@given(st.integers(min_value=1, max_value=10**12))
def test_fee_bounds(amount):
    fee = fee_cents(amount)
    assert fee >= 1
    assert fee * 100 >= amount            # never below 1 %
    assert (fee - 1) * 100 < amount       # rounded up by less than one cent
```

Hypothesis still writes a `.hypothesis/` cache into the working directory; keep the
project tree clean with
`HYPOTHESIS_STORAGE_DIRECTORY=.qa-superteam/hypothesis qast exec pytest ...`.
A failing property prints the minimal falsifying example: put that exact input into a
plain parametrized regression test so the defect reproduces deterministically.

Properties come from the rule, not from the implementation: bounds, round trips
(`parse(format(x)) == x`), idempotence (`normalize(normalize(x)) == normalize(x)`),
monotonicity, commutativity of independent operations.

## vitest (jest is almost identical)

```ts
import { afterEach, describe, expect, it, vi } from 'vitest';
import { feeCents } from '../src/pricing';
import { isTokenValid, issueToken } from '../src/sessions';

describe('feeCents', () => {
  it.each([
    { amount: 1, fee: 1 },
    { amount: 99, fee: 1 },
    { amount: 100, fee: 1 },
    { amount: 101, fee: 2 },
    { amount: 150, fee: 2 },
  ])('fee for $amount cents is $fee', ({ amount, fee }) => {
    expect(feeCents(amount)).toBe(fee);
  });

  it.each([0, -1, 1.5, Number.NaN])('rejects %s', (amount) => {
    expect(() => feeCents(amount)).toThrowError(/amount/i);
  });
});

describe('token expiry', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('is valid until exactly 24h after issue', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2024-03-31T23:59:59Z'));
    const token = issueToken(1);
    vi.setSystemTime(new Date('2024-04-01T23:59:58Z'));
    expect(isTokenValid(token)).toBe(true);
    vi.setSystemTime(new Date('2024-04-01T23:59:59Z'));
    expect(isTokenValid(token)).toBe(false);
  });
});
```

- `toBe` for primitives, `toEqual`/`toStrictEqual` for objects (`toStrictEqual` also
  fails on `undefined` properties and class mismatches).
- Async errors: `await expect(promise).rejects.toThrow(/declined/)`. Without `await`
  the assertion is never checked.
- `toBeCloseTo(x, digits)` is for floats only.
- Jest: `jest.fn`, `jest.spyOn`, `jest.useFakeTimers().setSystemTime(...)`,
  `test.each`. Restore spies (`restoreMocks` config or `afterEach(() => jest.restoreAllMocks())`).
- Run: `qast exec vitest --group <g> --label qa-unit -- src/pricing.test.ts` (the
  adapter adds `run --reporter=json`); `qast exec jest --group <g> -- src/pricing.test.ts`.

## go test

```go
func TestFeeCents(t *testing.T) {
	tests := []struct {
		name   string
		amount int64
		want   int64
	}{
		{"minimum fee floor", 1, 1},
		{"below one percent still minimum", 99, 1},
		{"exact one percent", 100, 1},
		{"rounds up not to nearest", 101, 2},
		{"half cent rounds up", 150, 2},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			if got := FeeCents(tc.amount); got != tc.want {
				t.Errorf("FeeCents(%d) = %d, want %d", tc.amount, got, tc.want)
			}
		})
	}
}

func TestFeeCentsRejectsNonPositive(t *testing.T) {
	for _, amount := range []int64{0, -1} {
		if _, err := FeeCentsChecked(amount); !errors.Is(err, ErrInvalidAmount) {
			t.Errorf("FeeCentsChecked(%d) error = %v, want ErrInvalidAmount", amount, err)
		}
	}
}
```

- Compare errors with `errors.Is`/`errors.As`, not strings.
- Concurrency-sensitive units: run with `-race`; a race report is evidence, a clean run
  is not proof of absence.
- Run with per-test results: `qast exec junit --report .qa-superteam/tmp/go-junit.xml --
  gotestsum --junitfile .qa-superteam/tmp/go-junit.xml -- -run 'TestFeeCents' ./pricing/...`.
  Without gotestsum: `qast exec command --label "go test pricing" -- go test -run TestFeeCents ./pricing/...`
  (coarse, exit-code only).

## Placing new tests

- New files only under `permissions.test_dir`; give them unique basenames
  (`test_qa_pricing.py`, `pricing.qa.test.ts`). pytest's default import mode fails with
  "import file mismatch" when two test files share a basename in different folders.
- `tests/qa/` inherits fixtures from `tests/conftest.py`; reuse them instead of
  re-creating apps, clients or factories.
- A vitest/jest file outside the configured `include`/`testMatch` globs is silently not
  collected: check the config and confirm the new tests appear in the execution counts.
