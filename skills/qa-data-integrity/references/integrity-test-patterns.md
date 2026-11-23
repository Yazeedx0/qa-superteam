# Data-integrity test patterns (pytest 8+, FastAPI TestClient, SQLite/Postgres)

The examples test a hypothetical inventory service: `create_app(db_path)`, products with
a unique SKU (case-insensitive by requirement), warehouses, stock levels per
warehouse/SKU (never negative), stock moves between warehouses (must be atomic and
conserve units), soft-deleted products, and an asynchronous export job. The write path
for moves lives in `app.inventory` (`debit(...)` then `credit(...)`). Adapt names; keep
the oracles. Reuse the project's own fixtures where they exist.

## Fixtures: disposable database + read-only SQL oracle

```python
# tests/qa/conftest.py
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "integrity.db"  # created and destroyed with the test: disposable


@pytest.fixture
def app(db_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)  # never fall back to a configured real DB
    return create_app(str(db_path))


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture
def raw_client(app):
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def sql(db_path):
    """Read-only queries on the disposable test database. Oracle only, never setup."""

    def query(statement: str, params: tuple = ()) -> list[tuple]:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            return conn.execute(statement, params).fetchall()
        finally:
            conn.close()

    return query


def run_concurrently(n: int, fn):
    """Call fn(i) for i in range(n) from n threads released at the same instant."""
    barrier = threading.Barrier(n)

    def task(i):
        barrier.wait(timeout=10)
        return fn(i)

    with ThreadPoolExecutor(max_workers=n) as pool:
        return list(pool.map(task, range(n)))


@pytest.fixture
def concurrently():
    return run_concurrently


@pytest.fixture
def stocked(client):
    """Two warehouses and 100 units of SKU-1 in the first one."""
    a = client.post("/warehouses", json={"name": "A"}).json()["id"]
    b = client.post("/warehouses", json={"name": "B"}).json()["id"]
    client.post("/products", json={"sku": "SKU-1", "name": "Widget"})
    r = client.post("/stock/receive", json={"warehouse_id": a, "sku": "SKU-1", "qty": 100})
    assert r.status_code == 200, r.text
    return {"a": a, "b": b, "sku": "SKU-1"}
```

Setup goes through the public API (so the data is shaped exactly as production code
writes it); SQL is used only to *observe*. Opening the file in `mode=ro` makes an
accidental write impossible.

## Conservation and non-negativity

```python
# tests/qa/test_qa_conservation.py
import pytest


def level(client, warehouse, sku):
    return client.get(f"/warehouses/{warehouse}/stock/{sku}").json()["qty"]


def total_units(sql, sku):
    return sql("SELECT COALESCE(SUM(qty), 0) FROM stock WHERE sku = ?", (sku,))[0][0]


@pytest.mark.parametrize("qty", [1, 100, 0, -1, 101, 10**18], ids=["one", "all", "zero", "negative", "more-than-available", "huge"])
def test_a_move_either_fully_happens_or_changes_nothing(client, sql, stocked, qty):
    a, b, sku = stocked["a"], stocked["b"], stocked["sku"]
    before = (level(client, a, sku), level(client, b, sku), total_units(sql, sku))

    r = client.post("/stock/move", json={"from_warehouse_id": a, "to_warehouse_id": b, "sku": sku, "qty": qty})

    after = (level(client, a, sku), level(client, b, sku), total_units(sql, sku))
    assert after[2] == before[2], "units created or destroyed"
    assert min(after[:2]) >= 0, f"negative stock: {after}"
    if r.status_code == 200:
        assert after[:2] == (before[0] - qty, before[1] + qty)
    else:
        assert after == before, f"rejected move ({r.status_code}) still changed stock: {before} -> {after}"
```

The invariant is checked after **every** outcome, accepted or rejected. Choose inputs that
sit on and around the limit (exactly the available amount, one more), plus invalid ones.
For money: sum of all balances plus fees collected equals deposits minus withdrawals;
check it after each operation in a sequence, not only at the end.

## Atomicity: inject a failure between two writes

```python
# tests/qa/test_qa_atomicity.py
import app.inventory as inventory


def test_move_is_rolled_back_when_the_credit_fails(raw_client, sql, stocked, monkeypatch):
    def fail_after_debit(*args, **kwargs):
        raise RuntimeError("injected failure after the debit was written")

    monkeypatch.setattr(inventory, "credit", fail_after_debit)  # the name the move code calls
    r = raw_client.post("/stock/move", json={"from_warehouse_id": stocked["a"], "to_warehouse_id": stocked["b"], "sku": "SKU-1", "qty": 40})

    assert r.status_code >= 500
    rows = dict(sql("SELECT warehouse_id, qty FROM stock WHERE sku = 'SKU-1'"))
    assert rows.get(stocked["a"]) == 100, f"debit survived a failed move: {rows}"
    assert rows.get(stocked["b"], 0) == 0
```

- Patch the function at the module where the write path looks it up. If there is no seam
  between the writes, failure injection is not possible without changing code: record
  that as a testability gap; do not edit application code to create one.
- Other failure points: constraint violation on the second insert, a raised exception in
  an event hook, a timeout from an integration called mid-transaction.

## Referential integrity

```python
# tests/qa/test_qa_references.py
def test_stock_cannot_reference_a_missing_warehouse(client, sql):
    client.post("/products", json={"sku": "SKU-9", "name": "Bolt"})
    r = client.post("/stock/receive", json={"warehouse_id": 999_999, "sku": "SKU-9", "qty": 5})
    assert r.status_code in (404, 422), r.text
    assert sql("SELECT COUNT(*) FROM stock WHERE warehouse_id = 999999")[0][0] == 0


def test_database_reports_no_foreign_key_violations(client, sql, stocked):
    client.post("/stock/move", json={"from_warehouse_id": stocked["a"], "to_warehouse_id": stocked["b"], "sku": "SKU-1", "qty": 5})
    # SQLite checks declared foreign keys even when enforcement was off for the app's connections.
    assert sql("PRAGMA foreign_key_check") == []
    orphans = sql("SELECT s.rowid FROM stock s LEFT JOIN warehouses w ON w.id = s.warehouse_id WHERE w.id IS NULL")
    assert orphans == []
```

SQLite enforces foreign keys only on connections that ran `PRAGMA foreign_keys = ON`:
check that the app's connection factory does. Postgres/MySQL: query
`information_schema.table_constraints` to confirm the constraint exists, then test the
behaviour (delete parent with children, create child for missing parent).

## Isolation: lost updates and races

```python
# tests/qa/test_qa_races.py
import pytest


@pytest.mark.parametrize("attempt", range(3))  # races are probabilistic: bounded repeats
def test_parallel_receipts_are_not_lost(raw_client, stocked, concurrently, attempt):
    a, sku = stocked["a"], stocked["sku"]
    start = raw_client.get(f"/warehouses/{a}/stock/{sku}").json()["qty"]
    responses = concurrently(10, lambda i: raw_client.post("/stock/receive", json={"warehouse_id": a, "sku": sku, "qty": 1}))
    assert [r.status_code for r in responses] == [200] * 10
    assert raw_client.get(f"/warehouses/{a}/stock/{sku}").json()["qty"] == start + 10


@pytest.mark.parametrize("attempt", range(3))
def test_parallel_moves_never_overdraw(raw_client, sql, stocked, concurrently, attempt):
    a, b, sku = stocked["a"], stocked["b"], stocked["sku"]
    start = raw_client.get(f"/warehouses/{a}/stock/{sku}").json()["qty"]
    responses = concurrently(8, lambda i: raw_client.post(
        "/stock/move", json={"from_warehouse_id": a, "to_warehouse_id": b, "sku": sku, "qty": 30}))
    codes = [r.status_code for r in responses]
    assert set(codes) <= {200, 409, 422}, codes  # 500/"database is locked" is a defect too
    moved = codes.count(200) * 30
    assert moved <= start
    assert raw_client.get(f"/warehouses/{a}/stock/{sku}").json()["qty"] == start - moved
    assert total_units_constant(sql, sku, start)


def total_units_constant(sql, sku, expected):
    return sql("SELECT SUM(qty) FROM stock WHERE sku = ?", (sku,))[0][0] == expected
```

- Use `raw_client` in race tests so a crash under contention is observed as a 500
  (product defect) instead of an exception that looks like a broken test.
- Code smells that predict lost updates: read a value, compute in Python, write it back
  (`qty = row.qty - n; UPDATE ... SET qty = ?`) without `SELECT ... FOR UPDATE`, an
  atomic `UPDATE ... SET qty = qty - ? WHERE qty >= ?`, a version column, or a
  serialising transaction (`BEGIN IMMEDIATE` in SQLite).
- Engine semantics differ: SQLite serialises writers (races show up as
  `database is locked`/500s rather than lost updates); Postgres `READ COMMITTED` and
  MySQL `REPEATABLE READ` allow lost updates with read-modify-write. A clean SQLite run
  proves little about a Postgres production: rerun the race tests on the production
  engine with Testcontainers (`disposable-databases.md`) or record the limitation.

## Duplicates and normalisation

```python
# tests/qa/test_qa_duplicates.py
import pytest

# Include a variant only if the requirement defines that normalisation.
SAME_SKU = {
    "lower-case": "ab-100",
    "mixed-case": "Ab-100",
    "surrounding-space": " AB-100 ",
}


@pytest.mark.parametrize("variant", list(SAME_SKU.values()), ids=list(SAME_SKU))
def test_sku_uniqueness_ignores_case_and_whitespace(client, sql, variant):
    assert client.post("/products", json={"sku": "AB-100", "name": "Original"}).status_code == 201
    r = client.post("/products", json={"sku": variant, "name": "Duplicate"})
    assert r.status_code == 409, r.text
    assert sql("SELECT COUNT(*) FROM products WHERE lower(trim(sku)) = 'ab-100'")[0][0] == 1


def test_lookup_accepts_any_case(client):
    client.post("/products", json={"sku": "AB-200", "name": "x"})
    assert client.get("/products/ab-200").status_code == 200


def test_concurrent_creation_of_the_same_key_yields_one_record(client, sql, concurrently):
    responses = concurrently(8, lambda i: client.post("/products", json={"sku": "ab-300" if i % 2 else "AB-300", "name": f"n{i}"}))
    codes = sorted(r.status_code for r in responses)
    assert codes.count(201) == 1 and set(codes) <= {201, 409}, codes
    assert sql("SELECT COUNT(*) FROM products WHERE lower(sku) = 'ab-300'")[0][0] == 1
```

- Every path that accepts the key must normalise the same way: create, update/rename,
  lookup, login/search, import, and uniqueness checks. A unique index on the raw column
  does not enforce case-insensitive uniqueness (`lower()` functional index, `citext`,
  `COLLATE NOCASE`, or a normalised column are needed).
- Unicode: NFC vs NFD (`"é"` vs `"é"`), full-width forms, zero-width characters,
  Turkish dotless i, `ß`. Test the ones the requirement or locale makes relevant.

## Idempotency and exactly-once effects

API-level replay tests are in `qa-backend` (`fastapi-httpx-patterns.md`). Add the
database oracle here: after sequential and concurrent replays, count the rows the
operation creates (`SELECT COUNT(*) FROM moves WHERE idempotency_key = ?`) and the side
effects (jobs enqueued, messages outboxed): exactly one.

## Eventual consistency: poll with a deadline

```python
# tests/qa/polling.py
import time


def wait_until(probe, *, timeout: float = 10.0, interval: float = 0.05, description: str = "condition"):
    """Return probe()'s first truthy value; fail with the last observation at the deadline."""
    deadline = time.monotonic() + timeout
    last = None
    while True:
        last = probe()
        if last:
            return last
        if time.monotonic() >= deadline:
            raise AssertionError(f"{description} not reached within {timeout}s; last observation: {last!r}")
        time.sleep(interval)
```

```python
# tests/qa/test_qa_async.py
from polling import wait_until

LEGAL = {"queued", "running", "done", "failed"}


def test_export_job_reaches_done_with_every_row(client, stocked):
    client.post("/stock/move", json={"from_warehouse_id": stocked["a"], "to_warehouse_id": stocked["b"], "sku": "SKU-1", "qty": 10})
    job_id = client.post("/exports", json={"sku": "SKU-1"}).json()["id"]
    seen = []

    def finished():
        body = client.get(f"/exports/{job_id}").json()
        seen.append(body["status"])
        return body if body["status"] in ("done", "failed") else None

    final = wait_until(finished, timeout=10, description=f"export {job_id} finished")
    assert set(seen) <= LEGAL, f"illegal intermediate status: {seen}"
    assert final["status"] == "done"
    assert final["rows"] == 2  # both warehouses now hold SKU-1: one row each, per the export spec
```

- The timeout comes from the requirement/SLA when one exists; otherwise choose a
  generous bound and say it is inferred. A deadline miss is FAILED; if the environment is
  suspect (machine overloaded, queue not running), report ERROR/INCONCLUSIVE instead.
- Prefer running the worker synchronously when the framework allows it (call the job
  function directly, Celery `task_always_eager`, FastAPI `BackgroundTasks` complete
  before `TestClient` returns) and keep polling for genuinely external processes.
- Never `time.sleep(N)` followed by a single assertion.

## Data lifecycle: soft delete and retention

```python
# tests/qa/test_qa_lifecycle.py
def test_soft_deleted_product_disappears_from_every_read_path(client, sql):
    client.post("/products", json={"sku": "DEL-1", "name": "Old"})
    assert client.delete("/products/DEL-1").status_code in (200, 204)

    assert client.get("/products/DEL-1").status_code == 404
    assert "DEL-1" not in [p["sku"] for p in client.get("/products").json()]
    assert client.get("/products", params={"q": "DEL"}).json() == []
    # Soft delete per requirement: the row is kept and marked, not removed.
    assert sql("SELECT deleted_at IS NOT NULL FROM products WHERE sku = 'DEL-1'") == [(1,)]
```

Then check, per requirement: re-creating the same key after deletion (allowed or 409),
references to the deleted object (stock rows, history) still resolve or are hidden
consistently, exports/reports exclude it, restore brings back exactly the original.
Retention jobs: inject the clock (patch the module's `now()`), seed rows just inside and
just outside the retention age, run the job function directly, assert exactly the
expired rows are gone and nothing else.

## Property-based sequences (only if `hypothesis` is installed)

For invariants that must hold after *any* sequence of operations, a stateful test finds
orderings humans miss. Keep `max_examples` small (each example builds an app), use
`database=None`, and turn every falsifying sequence it prints into a plain regression
test before reporting it.

```python
# tests/qa/test_qa_stateful.py
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient
from hypothesis import settings, strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule

from app.main import create_app


class InventoryMachine(RuleBasedStateMachine):
    def __init__(self):
        super().__init__()
        self.client = TestClient(create_app(str(Path(tempfile.mkdtemp()) / "state.db")))
        self.client.__enter__()
        self.wh = [self.client.post("/warehouses", json={"name": n}).json()["id"] for n in ("A", "B")]
        self.client.post("/products", json={"sku": "SKU-1", "name": "Widget"})
        self.client.post("/stock/receive", json={"warehouse_id": self.wh[0], "sku": "SKU-1", "qty": 100})

    def teardown(self):
        self.client.__exit__(None, None, None)

    def level(self, i):
        return self.client.get(f"/warehouses/{self.wh[i]}/stock/SKU-1").json()["qty"]

    @rule(src=st.integers(0, 1), qty=st.integers(min_value=-5, max_value=150))
    def move(self, src, qty):
        self.client.post("/stock/move", json={
            "from_warehouse_id": self.wh[src], "to_warehouse_id": self.wh[1 - src], "sku": "SKU-1", "qty": qty})

    @invariant()
    def units_are_conserved_and_non_negative(self):
        a, b = self.level(0), self.level(1)
        assert a >= 0 and b >= 0, (a, b)
        assert a + b == 100, (a, b)


TestInventory = InventoryMachine.TestCase
TestInventory.settings = settings(max_examples=20, stateful_step_count=15, database=None, deadline=None)
```
