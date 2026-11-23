# Finding integrity risks by reading schema and write paths

Static review tells you where to aim the executed tests. A suspicion from reading code
is a hypothesis (`SUSPECTED` at most) until a test fails.

## 1. Invariants first

From requirements, docs and domain knowledge, list the invariants with an oracle each:

| Kind | Example statement | Oracle |
|---|---|---|
| Conservation | Units/money moved, never created or destroyed | Sum over all holders constant across operations (+ explicit sources/sinks such as fees, deposits) |
| Non-negativity / bounds | Stock and balances never below 0; limits never exceeded | `MIN(qty) >= 0` after every operation, including rejected and concurrent ones |
| Uniqueness | One account per email ignoring case | Count of normalised key = 1 after sequential and concurrent creation |
| Referential | Every child row points to an existing parent | `PRAGMA foreign_key_check` empty / anti-join returns nothing |
| State machine | Order states follow allowed transitions; terminal states final | Transition table test; DB never holds an illegal state |
| Exactly-once | A retried request has one effect | Row/side-effect counts after replays |
| Audit/history | Every balance change has a ledger entry | Sum of entries = balance; count of entries = count of operations |
| Lifecycle | Deleted data hidden everywhere / purged after N days | Every read path; retention job boundary |

## 2. Schema review

For each table holding an invariant, check what the database itself enforces:

- [ ] `NOT NULL` on columns the code assumes are present.
- [ ] `UNIQUE` on the *normalised* key (functional index on `lower(email)`, `citext`,
      `COLLATE NOCASE`, or a separate normalised column). A plain `UNIQUE(email)` with
      case-insensitive requirements is a gap.
- [ ] `CHECK (qty >= 0)`, `CHECK (amount > 0)` for absolute rules.
- [ ] Foreign keys declared, with `ON DELETE` behaviour matching the requirement
      (`RESTRICT`, `CASCADE`, `SET NULL`); SQLite: enforcement pragma on every connection.
- [ ] Unique constraint backing idempotency keys, scoped as the requirement says
      (`UNIQUE(user_id, key)`).
- [ ] Integer widths: cents in 32-bit columns overflow at about $21M; ids/amounts larger
      than the engine's integer type must be rejected cleanly at the API.
- [ ] Money as integer minor units or `NUMERIC`, never float.
- [ ] Soft delete: unique constraints must account for deleted rows as specified
      (partial unique index `WHERE deleted_at IS NULL`).

## 3. Write-path review

For each operation that mutates an invariant:

- [ ] **Transaction boundary:** all writes of one business operation in one transaction;
      no commit between debit and credit; no external call (HTTP, queue publish) inside
      the transaction that can fail after a commit (or outbox pattern in place).
- [ ] **Check-then-act:** `SELECT` to validate, then `INSERT/UPDATE` later. Safe only
      under a lock (`FOR UPDATE`, `BEGIN IMMEDIATE`) or if the write itself is
      conditional (`UPDATE ... WHERE qty >= ?` and check `rowcount`) or a constraint backs
      it (`UNIQUE` + catch `IntegrityError` → 409).
- [ ] **Read-modify-write in application code** (`new = old - n` then write `new`):
      lost-update candidate under concurrency.
- [ ] **Validation vs effect mismatch:** the amount validated differs from the amount
      applied (fees, rounding, currency conversion added after the check).
- [ ] **Normalisation consistency:** the same normalisation on create, update, lookup,
      login, import.
- [ ] **Error handling:** broad `except` that swallows a failed second write and still
      returns success; retries that re-run non-idempotent writes.
- [ ] **Isolation level** in use (engine default or configured) and whether the code
      relies on more than it provides.
- [ ] **Async consumers:** at-least-once delivery handled with dedup keys; ordering
      assumptions documented.

## 4. Turn each suspicion into an executed test

| Suspicion | Test pattern (`integrity-test-patterns.md`) |
|---|---|
| Check-then-act or read-modify-write | Barrier-synchronised concurrency, invariant after, bounded repeats, production engine if it differs |
| Missing transaction / commit between writes | Failure injection between the writes |
| Validation vs effect mismatch | Boundary values where the difference matters (exactly the balance, one unit more) |
| Missing normalised uniqueness | Sequential duplicate variants, then concurrent creation |
| Missing FK / wrong cascade | Create child for missing parent; delete parent; `foreign_key_check`/anti-join |
| Overflow / width | Max+1 values through the API; expect 422, never 500 or wraparound |
| Soft-delete leaks | Every read path after delete; re-create rules |

Record the static evidence (file, line, symbol) in the finding's `affected` and
`hypotheses` (`confirmed: false` until a failing execution backs it).
