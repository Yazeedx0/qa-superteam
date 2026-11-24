# Business invariant catalogue

An invariant is a property that must hold after every committed operation, under any
sequence and interleaving of requests. Invariants make the strongest oracles because
they need no per-case expected value: check them after every step of any sequence,
whether example-based, property-based or concurrent.

Each entry: statement template · oracle (what a test reads and how it compares) ·
how implementations typically break it · how to exercise it.

## 1. Conservation (money, stock, points)

- **Statement:** the total across all accounts, including fee, house and escrow
  accounts, changes only by external inflows and outflows. Internal movements conserve
  it exactly.
- **Oracle:** read every affected account before and after the operation; assert, in
  integer minor units, `after_total - before_total == sum(external amounts)`. Per
  movement: `sender_delta == -(amount + fee)`, `recipient_delta == amount`,
  `fee_account_delta == fee`.
- **Breaks via:** fee rounded differently in two places; partial commit on error; float
  arithmetic; fee credited but not debited; retries applying twice.
- **Exercise:** check after each step of example sequences; property-based random
  operation sequences; concurrent movements from one account.
- If a fee or house account is not observable through any interface, the oracle reduces
  to sender and recipient deltas: record the gap as a limitation.

## 2. Non-negativity and bounds

- **Statement:** a quantity stays within [min, max] (often ≥ 0) after any sequence.
- **Oracle:** read the value after every operation and assert the bound. For a rejected
  operation assert both the specified error and that the value is unchanged.
- **Breaks via:** check-then-act races (check, then debit in a separate statement);
  the check ignores the fee; the check reads the wrong account; overflow.
- **Exercise:** boundaries (balance exactly equal to the debit; one minor unit short);
  N concurrent debits that are each affordable but not together.

## 3. Uniqueness

- **Statement:** at most one entity per natural key (email, username, order number,
  idempotency key within its scope), under the key's normalization (case, whitespace,
  unicode).
- **Oracle:** a second create with an equivalent key returns the specified conflict
  response; lookup and listing return exactly one entity.
- **Breaks via:** write and lookup normalize differently; uniqueness checked in code
  without a database constraint (race); constraint on the raw value while lookups
  normalize.
- **Exercise:** equivalence classes of the key (case variants, surrounding spaces,
  composed vs decomposed unicode when in scope); concurrent duplicate creates.

## 4. Idempotency

- **Statement:** repeating a request with the same idempotency key in the same scope
  returns the original result and has no further effect; the same key with a different
  payload is rejected as specified; different scopes are independent.
- **Oracle:** compare id, body and status of the first and repeated responses; compare
  state deltas (exactly one effect). Payload mismatch: specified status and no effect.
- **Breaks via:** key stored after the effect (crash or race window); key scoped
  globally instead of per principal (cross-user replay or denial); payload comparison
  ignores a field; replay returns a new object or a different status.
- **Exercise:** decision table over {same key, same payload, same principal};
  concurrent duplicates with one key.

## 5. Ownership and tenancy isolation

- **Statement:** a principal can read or change only resources it owns or was granted.
  Where specified, a hidden resource is indistinguishable from a non-existent one.
- **Oracle:** as user B, request A's resource by id: the specified status (often 404)
  and a body that contains none of A's data; list endpoints return only B's resources
  (compare id sets).
- **Breaks via:** lookup by id without an owner filter (IDOR/BOLA); list filtered but
  detail not; update or delete paths missing the check that read has; 403 vs 404
  revealing existence.
- **Exercise:** a two-principal fixture for every id-taking route and method; other
  tenants' ids, non-existent ids, malformed ids.

## 6. Monotonic state machines

- **Statement:** status moves only along allowed transitions; terminal states are
  final; timestamps and sequence numbers never go backwards.
- **Oracle:** a transition table; for each attempted transition assert
  accepted ⇔ allowed, and state unchanged when rejected.
- **Breaks via:** one endpoint without the guard; concurrent transitions; retries that
  reset state; a UI that resumes past a step whose data is incomplete.
- **Exercise:** state-transition testing (every valid transition, each invalid one from
  each state); model-based sequences.

## 7. Referential integrity

- **Statement:** every reference points to an existing entity; deleting or archiving a
  referenced entity follows the specified rule (cascade, restrict, nullify).
- **Oracle:** after operations every referenced id resolves; deleting a referenced
  entity produces the specified outcome.
- **Breaks via:** foreign keys declared but not enforced by the store configuration;
  soft deletes leaving visible dangling references; create accepting a non-existent
  foreign id.
- **Exercise:** negative cases with non-existent and other-tenant references;
  delete-then-read sequences.

## 8. Atomicity

- **Statement:** a failed operation leaves no partial effect.
- **Oracle:** trigger a failure mid-operation (invalid later step, constraint violation)
  and assert all affected state equals the pre-state.
- **Exercise:** rejected requests inside invariant sequences; fault injection only when
  `permissions.allow_fault_injection = true`.

## 9. Displayed equals charged

- **Statement:** values shown to the user equal the values persisted, charged or sent
  (prices, discounts, totals, currency).
- **Oracle:** for the same action compare the displayed total with the request payload
  or the stored record.
- **Breaks via:** client-side recalculation diverging from the server; totals cached
  before a cart change; per-line vs per-total rounding.

## 10. AI-system invariants (LLM, RAG, tool calling)

- citations ⊆ retrieved documents; a refusal makes no side-effecting tool call;
  side-effecting tools run only after their precondition (e.g. lookup before refund)
  with the exact amount; secrets and instructions from retrieved text never appear in
  output; output size within the stated limit.
- **Oracle:** structured response fields and the ordered tool-call log, checked per case
  by `qast exec ai-eval` expectations.

## Writing the oracle field

| Good | Bad |
|---|---|
| "After each API call, the sum of `balance_cents` over sender, recipient and fee account equals the sum before plus that step's deposits (integer equality)." | "Balances are correct." |
| "As user B, GET /orders/{A's id} returns 404 with a body identical to the response for a random non-existent id." | "Users cannot see other users' orders." |

Criticality comes from the policy's severity definitions: conservation and
non-negativity of money, tenancy isolation and payment idempotency are `critical`.
