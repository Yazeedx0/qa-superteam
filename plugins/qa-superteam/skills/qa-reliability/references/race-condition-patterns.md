# Race-condition test patterns

A race test is only useful if (a) the operations really overlap, (b) the oracle is an
invariant checked after all of them finish, and (c) a failure reproduces. The patterns
below were executed: the barrier test catches an unlocked check-then-act on every run.

## Release N threads at once

```python
import threading
from concurrent.futures import ThreadPoolExecutor


def run_concurrently(fn, n):
    """Run fn(0..n-1) in n threads released together by a barrier; return results in order."""
    barrier = threading.Barrier(n)

    def task(i):
        barrier.wait(timeout=5)        # bounded: a broken barrier fails instead of hanging
        return fn(i)

    with ThreadPoolExecutor(max_workers=n) as pool:
        return list(pool.map(task, range(n)))
```

`pool.map` re-raises the first exception from a worker, so an error inside `fn` fails the
test with the real traceback.

## Invariant: no overdraft under concurrent spends (in-process API)

```python
def test_concurrent_spends_cannot_overdraw(client, make_user):
    sender = make_user(balance=1000)
    recipient = make_user()
    body = {"to_wallet_id": recipient.wallet_id, "amount_cents": 600}
    statuses = run_concurrently(
        lambda i: client.post("/transfers", json=body, headers=sender.headers).status_code, n=6)
    assert statuses.count(201) == 1, statuses
    assert client.get("/wallets/me", headers=sender.headers).json()["balance_cents"] >= 0
```

Starlette/FastAPI `TestClient` is safe to call from several threads, and synchronous
endpoints run in a worker thread pool, so requests overlap for real. Each request must use
its own DB connection (as in production) for the test to mean anything: a single shared
connection serializes everything and hides the race. Check the app's connection handling
before trusting a PASSED result.

## Invariant: concurrent retries with one idempotency key move money once

```python
def test_concurrent_retries_with_same_key_move_money_once(client, make_user):
    sender = make_user(balance=1000)
    recipient = make_user()
    body = {"to_wallet_id": recipient.wallet_id, "amount_cents": 100}
    headers = {**sender.headers, "Idempotency-Key": "retry-1"}
    responses = run_concurrently(lambda i: client.post("/transfers", json=body, headers=headers), n=5)
    assert all(r.status_code == 201 for r in responses), [r.status_code for r in responses]
    assert len({r.json()["id"] for r in responses}) == 1
    assert client.get("/wallets/me", headers=recipient.headers).json()["balance_cents"] == 100
```

If the contract allows a `409` "request in progress" for concurrent duplicates, accept it
explicitly in the oracle; the money invariant stays the same.

## Make a suspected race deterministic

Barrier tests are probabilistic: the window between "read" and "write" may be microseconds.
When inspection shows a check-then-act (read balance → compute → write) without a lock,
row lock or atomic statement, force the interleaving instead of hoping for it:

```python
import threading


def test_check_then_act_is_atomic(monkeypatch):
    account = Account(balance=100)               # the object under test
    original_check = account.has_funds           # the "read" half of check-then-act
    both_checked = threading.Barrier(2, timeout=1)

    def check_then_wait(amount):
        ok = original_check(amount)
        try:
            both_checked.wait()                  # both threads pass the check before either writes...
        except threading.BrokenBarrierError:
            pass                                 # ...unless access is serialized (correct code)
        return ok

    monkeypatch.setattr(account, "has_funds", check_then_wait)
    results = run_concurrently(lambda i: account.withdraw(60), n=2)
    assert results.count(True) == 1 and account.balance == 40, (results, account.balance)
```

With correct locking the second thread cannot reach the check until the first has written,
so the barrier times out after 1 s, both threads continue, and the invariant holds. Without
locking both threads pass the check before either writes, and the test fails on **every**
run (verified on both variants). Adapt the hook to the code: patch the repository's read
method, the ORM query, or the dependency the code calls between read and write.

When forcing is impossible (the window is inside a library), raise the odds instead:
repeat the barrier test in a loop inside one test (for example 50 rounds on fresh state)
and report the observed failure rate. Then classify with `qast reproduce --times 5`:
`consistent` supports a finding; `intermittent` is INCONCLUSIVE until made deterministic.

## Database-level races

- **Unique constraints**: two concurrent creates with the same natural key (email,
  idempotency key, order number) yield one row and a clean conflict response, not a 500
  from an `IntegrityError`.
- **Lost update**: two concurrent increments of a counter or stock level; the final value
  equals the sum of both.
- **SQLite** serializes writers; a race that cannot occur on SQLite may occur on PostgreSQL
  under `READ COMMITTED`. If production uses another database, say that the test environment
  cannot show this class of defect, and propose a test against a disposable instance of the
  production database (testcontainers, if the project already uses it).

## Async code

For asyncio, overlap with `asyncio.gather` and synchronize with `asyncio.Event` at the
suspected await point (patch the awaited call to wait on the event). Races in async code
happen only at `await` points, which makes forcing them straightforward.

## Hygiene

- Every wait has a timeout (`Barrier(timeout=...)`, `Event.wait(timeout)`, `future.result(timeout)`).
- Fresh state per test (temp DB, new objects); never share state between race tests.
- Thread count small (2-8): enough to overlap, not a load test.
- Run race tests under `qast exec pytest --group reliability`; never retry them by hand to get a green run.
