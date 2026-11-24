# Test design techniques: worked examples

The features below are illustrations, not the project under test. Recompute every
expected value from your own requirements.

## A. Processing fee (equivalence, boundary, decision table, property)

> Merchants pay 2.9% of the charge amount plus 30 cents, rounded half up to the cent,
> capped at $25.00. Non-profit merchants pay 2.2% plus 30 cents, same cap. A charge is
> 50 cents to $5,000.00. All amounts are integer cents.

**Equivalence partitions**

| Input | Valid classes | Invalid classes |
|---|---|---|
| amount | 50..500000 below the cap; 50..500000 at or above the cap | < 50; > 500000; non-integer; negative; missing |
| merchant type | standard; non-profit | unknown value (behaviour unspecified: an ambiguity, not a case) |

**Boundary values** (standard merchant). Expected values from an independent integer
model of the text: `fee = min(2500, (29 * amount + 30000 + 500) // 1000)`.

| amount | why | expected fee |
|---|---|---|
| 49 | below minimum | rejected, nothing charged |
| 50 | minimum | 31 |
| 500 | 14.5 + 30: an exact half cent | 45 (44 means half-even or truncation, e.g. Python `round()`) |
| 1500 | 43.5 + 30: also a half, but half-even gives the same 74 | 74; does not distinguish rounding modes, so 500 is the better case |
| 85155 | last amount below the cap | 2499 |
| 85156 | first amount where the rounded fee reaches the cap | 2500 |
| 500000 | maximum | 2500 |
| 500001 | above maximum | rejected |

**Decision table** (conditions → action):

| Rule | amount valid | merchant | rounded fee ≥ 2500 | Action |
|---|---|---|---|---|
| R1 | no | any | — | reject, no charge |
| R2 | yes | standard | no | 2.9% + 30, half up |
| R3 | yes | standard | yes | 2500 |
| R4 | yes | non-profit | no | 2.2% + 30, half up |
| R5 | yes | non-profit | yes | 2500 |
| R6 | yes | unknown | — | **not specified**: record an ambiguity, do not invent an action |

A decision table that has a column the source does not cover has found a requirement
gap. That is a result.

**Properties** (Hypothesis; fast-check is equivalent):

```python
from hypothesis import given, strategies as st

def spec_fee(amount: int, nonprofit: bool) -> int:      # written from the requirement text
    per_mille = 22 if nonprofit else 29
    return min(2500, (per_mille * amount + 30_000 + 500) // 1000)

@given(st.integers(min_value=50, max_value=500_000), st.booleans())
def test_fee_matches_spec(amount, nonprofit):
    assert fee_for(amount, nonprofit) == spec_fee(amount, nonprofit)

@given(st.integers(min_value=50, max_value=499_999))
def test_fee_is_monotonic(amount):
    assert fee_for(amount + 1, False) >= fee_for(amount, False)

@given(st.integers(min_value=50, max_value=500_000))
def test_nonprofit_never_pays_more(amount):
    assert fee_for(amount, True) <= fee_for(amount, False)
```

```js
import fc from 'fast-check';
test('fee never exceeds the cap', () => {
  fc.assert(fc.property(fc.integer({ min: 50, max: 500000 }), fc.boolean(),
    (amount, nonprofit) => feeFor(amount, nonprofit) <= 2500));
});
```

As a plan case:

```json
{"id": "TC-07", "title": "Fee rounds half up at an exact half cent", "level": "unit",
 "technique": "boundary", "priority": "high", "origin": "proposed", "test_ref": null,
 "oracle": "fee_for(500, standard) == 45; 44 indicates half-even rounding or truncation",
 "inputs": {"amount_cents": 500, "merchant": "standard"},
 "requirement_ids": ["REQ-FEE-1"], "risk_ids": ["R-02"]}
```

## B. Checkout flow (state transition, equivalence, pairwise, negative)

> Steps: Cart → Address → Payment → Review → Confirmed. Back is allowed from Address,
> Payment and Review. Reload resumes on the last step whose data is complete. Confirmed
> is terminal. Countries US, DE, JP; invoice payment only for DE; locales en, de, ja.

**State transition table** (cells are the expected next state; "—" means the event is
not offered):

| From \ Event | next (valid) | next (invalid) | back | reload | place order ok | place order fails |
|---|---|---|---|---|---|---|
| Cart | Address | — | — | Cart | — | — |
| Address | Payment | Address + inline error | Cart | Address | — | — |
| Payment | Review | Payment + inline error | Address | Payment | — | — |
| Review | — | — | Payment | Review | Confirmed | Review + error, data kept |
| Confirmed | — | — | no resubmission | new Cart | — | — |

Cover every valid cell once (0-switch). Add 1-switch sequences for critical paths:
Review → fails → retry → Confirmed; Address invalid → corrected → Payment in the same
session. Probe forbidden moves: deep link to Review with an empty Address must land on
Address; double-click on "Place order" must create one order. Any cell the source does
not define becomes a question.

**Equivalence and boundaries for postal codes:** per country, valid format, one digit
short, one digit long, letters, surrounding whitespace, and a country change after a
valid code (a valid US code must be revalidated when switching to JP). Where the source
is silent (is the JP hyphen optional? are full-width digits accepted?), record an
ambiguity.

**Pairwise:** country (3) × locale (3) × viewport (2) × payment (2) with the constraint
invoice ⇒ DE has 24 valid combinations. These 10 rows cover every valid pair:

| # | country | locale | viewport | payment |
|---|---|---|---|---|
| 1 | US | en | desktop | card |
| 2 | US | de | mobile | card |
| 3 | US | ja | desktop | card |
| 4 | DE | en | mobile | invoice |
| 5 | DE | de | desktop | invoice |
| 6 | DE | ja | mobile | invoice |
| 7 | JP | en | desktop | card |
| 8 | JP | de | mobile | card |
| 9 | JP | ja | mobile | card |
| 10 | DE | en | desktop | card |

Use all combinations only for pairs that carry money or legal risk (country × payment).
Generate larger arrays with a tool and verify pair coverage rather than trusting a
hand-built table.

**Negative:** missing required fields, malformed email, markup characters in the name
rendered as text (a benign marker such as `<i>QA</i>`), payment provider error,
expired session at Review. Each oracle names the message, the step the user stays on,
and that entered data is kept.

## C. Retrieval function (metamorphic, invariant, specified)

> `search(query, k)` returns up to `k` document ids from a help-centre corpus, ranked
> by BM25.

There is no exact expected ranking for most queries, so use relations and invariants.

**Invariants** (every call): results ⊆ corpus ids; no duplicates; `len(results) <= k`;
same input → same output.

**Metamorphic relations.** Derive each one from the algorithm and validate it on a few
known cases before trusting it:

| Relation | Valid for BM25? |
|---|---|
| top-k is a prefix of top-(k+1) for the same query | yes |
| permuting the corpus order does not change results (ties excepted, unless a tie rule is specified) | yes |
| case and whitespace variants of the query give identical results | only if the tokenizer normalizes them: check the tokenizer first |
| adding a document that contains no query term leaves the ranking unchanged | **no**: IDF and average document length change with the corpus, so scores and even order can change. An invalid relation produces false defects |

```python
def test_topk_is_prefix_of_topk_plus_one(index):
    for q in ["reset password", "export invoices", "change billing address"]:
        assert index.search(q, k=3) == index.search(q, k=4)[:3]
```

**Specified oracle:** for a small set of queries with a human-labelled relevant
document, assert the labelled document is in the top k. Run labelled sets as
`qast exec ai-eval` cases with `retrieved_include` when the project has a golden
dataset.

**Boundaries for k:** 0, 1, corpus size, corpus size + 1, negative. Behaviour for 0 and
negative values is usually unspecified: record it.

## D. Inventory reservations (invariant, stateful property)

> Stock has `on_hand`, `reserved`, `available`. Reserving more than `available` is
> rejected. Invariant: `available >= 0` and `available + reserved == on_hand`.

Check the invariant after every step of random sequences, including rejected ones:

```python
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule

class Inventory(RuleBasedStateMachine):
    def __init__(self):
        super().__init__()
        self.api = make_client()                    # project fixture with a fresh store
        self.api.set_stock("SKU-1", on_hand=10)

    @rule(qty=st.integers(min_value=-1, max_value=12))
    def reserve(self, qty):
        before = self.api.stock("SKU-1")
        if self.api.reserve("SKU-1", qty).status_code != 201:
            assert self.api.stock("SKU-1") == before   # rejected: nothing changed

    @rule()
    def release_all(self):
        self.api.release_all("SKU-1")

    @invariant()
    def stock_is_consistent(self):
        s = self.api.stock("SKU-1")
        assert s["available"] >= 0
        assert s["available"] + s["reserved"] == s["on_hand"]

TestInventory = Inventory.TestCase
```

Sequential properties do not find races. For check-then-act risks add a concurrent case:
N parallel reservations that are each affordable alone but not together; oracle: the
number of successes × qty ≤ initial available, and the invariant holds afterwards.

## E. Regression test for a confirmed defect

> Finding F-3 (CONFIRMED): the order total is one cent low when a 10% discount applies
> to 3 items at 333 cents.

- Pin the exact failing input: 3 × 333, 10% off.
- Add neighbours that exercise the same rounding step: 2 × 333, 4 × 333, 3 × 334.
- Assert the specified value (from the pricing rule, computed by hand), never the value
  the buggy build produces, and add the invariant (displayed total == charged amount).
- The test must fail on the current build and pass once fixed; name it after the
  finding (`test_f3_discount_rounding_three_items`), group `regression`, origin `new`
  only when `write_tests = true`, otherwise `proposed` with full code in the report.

## Negative test inventory (any feature)

| Category | Cases | Oracle must state |
|---|---|---|
| Input validation | missing, empty, wrong type, out of range, too long, malformed format | status/message and that nothing changed |
| Authorization | no credentials, expired credentials, another user's id, lower role | status, no foreign data in the body, no state change |
| State | action in the wrong state, after a terminal state, repeated action | status and unchanged state |
| Protocol | wrong content type, malformed JSON, unexpected fields, oversized body | status; unexpected fields ignored or rejected as specified |
| Duplicates | same request twice, same unique key, concurrent duplicates | exactly one effect |
| Dependencies | downstream timeout or error (only through test doubles unless fault injection is authorized) | user-visible error, no partial effect, retry behaviour |
