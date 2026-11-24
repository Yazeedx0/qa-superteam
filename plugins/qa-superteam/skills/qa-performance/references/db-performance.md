# Database performance and micro-benchmarks

Deterministic checks that need no load and produce stable PASSED/FAILED results. Run them
with `qast exec pytest --group performance -- <test_dir>/test_perf_<area>.py`. The sqlite3 and
SQLAlchemy snippets below were executed as written.

## N+1 detection: query count must not scale with rows

Absolute counts are brittle ("exactly 3 queries"); a **scaling test** is not: the number of
queries for a list of 10 items must equal the number for 1 item.

### sqlite3 (standard library)

```python
import sqlite3
from contextlib import contextmanager


@contextmanager
def count_sqlite_queries(conn: sqlite3.Connection):
    statements = []
    conn.set_trace_callback(statements.append)  # called once per executed statement
    try:
        yield statements
    finally:
        conn.set_trace_callback(None)
```

When the app opens its own connection per request (a `get_db` dependency), wrap the
connection factory instead so every connection is traced:

```python
def test_transfer_list_query_count_is_constant(client, make_user, monkeypatch):
    import app.db as db                      # the module that defines connect()
    statements = []
    real_connect = db.connect

    def traced_connect(*args, **kwargs):
        conn = real_connect(*args, **kwargs)
        conn.set_trace_callback(statements.append)
        return conn

    monkeypatch.setattr(db, "connect", traced_connect)

    def count_for(n):
        user = make_user(balance=10_000)
        other = make_user()
        for _ in range(n):
            client.post("/transfers", json={"to_wallet_id": other.wallet_id, "amount_cents": 1}, headers=user.headers)
        statements.clear()
        assert client.get("/transfers", headers=user.headers).status_code == 200
        return len(statements)

    assert count_for(1) == count_for(10)
```

Patch the name where it is looked up: if routes do `from app.db import connect`, patch
`app.routes.module.connect`, not `app.db.connect`. Use the project's real fixtures and routes.

### SQLAlchemy

```python
from sqlalchemy import event


def test_orders_listing_has_no_n_plus_one(engine, seed_orders, list_orders):
    statements = []

    def _count(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", _count)
    try:
        counts = {}
        for n in (1, 10):
            seed_orders(n)
            statements.clear()
            list_orders()
            counts[n] = len(statements)
    finally:
        event.remove(engine, "before_cursor_execute", _count)
    assert counts[1] == counts[10], counts
```

`engine`, `seed_orders` and `list_orders` stand for the project's own fixtures and service
call. Fix: `selectinload`/`joinedload`; the test documents the expectation.

### Django

`pytest-django` provides `django_assert_num_queries(n)` and
`django_assert_max_num_queries(n)`; Django's `TestCase.assertNumQueries` does the same.
Use the scaling form: run the view with 1 and 10 objects and compare.

## Query plans

Run `EXPLAIN` on the hot queries (from the code or the slow-query log) against a test
database with realistic row counts. An index that exists but is not used on 10 rows may be
used on 100,000: the planner depends on statistics.

```python
def test_transfer_lookup_by_wallet_uses_index(conn):
    plan = " ".join(row[-1] for row in conn.execute(
        "EXPLAIN QUERY PLAN SELECT * FROM transfers WHERE from_wallet_id = ?", (1,)))
    assert "USING INDEX" in plan or "USING COVERING INDEX" in plan, plan
    assert "SCAN transfers" not in plan, plan
```

| Database | Command | Red flags |
|---|---|---|
| SQLite | `EXPLAIN QUERY PLAN <query>` | `SCAN <table>` on a large table, `USE TEMP B-TREE FOR ORDER BY` |
| PostgreSQL | `EXPLAIN (ANALYZE, BUFFERS) <query>` | `Seq Scan` on large tables with selective filters, estimated vs actual rows off by 10x+, `Sort Method: external merge` |
| MySQL | `EXPLAIN ANALYZE <query>` | `type: ALL`, `Using filesort`, `Using temporary` |

`EXPLAIN ANALYZE` **executes** the statement. Run it only on a disposable test database,
and for `INSERT/UPDATE/DELETE` wrap it in `BEGIN; ... ROLLBACK;`.

## Unbounded work

Each is a cheap test with a stable oracle:

- List endpoints cap the page size: request `?limit=100000` and assert the response holds at
  most the documented maximum (or that the request is rejected).
- Queries behind list endpoints contain `LIMIT` (assert on the traced statements).
- Exports and reports stream or paginate instead of loading the whole table.
- Async handlers do not call blocking I/O (`requests`, `time.sleep`, sync DB drivers) on the
  event loop: inspection finds candidates; a test with two concurrent requests to a handler
  with a patched slow dependency shows whether they serialize.

## Micro-benchmarks

Only when the project already depends on `pytest-benchmark` (check `pyproject.toml`,
requirements files, `qast doctor`). Never add the plugin.

```python
def test_fee_calculation_speed(benchmark):
    result = benchmark(compute_fee, 123_456)
    assert result == 1235          # a benchmark still checks correctness
```

Run before and after the change on the same machine in the same session:
`qast exec pytest --group performance -- tests/qa/test_perf_fees.py --benchmark-only`
(arguments after the test path go to pytest). Report the relative change of the median
with both values; absolute timings describe this machine only. Without `pytest-benchmark`,
do not write timing assertions with `time.perf_counter()` and a fixed budget: they flake on
shared runners. Record the micro-benchmark as not run and why.
