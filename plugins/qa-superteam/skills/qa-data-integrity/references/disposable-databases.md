# Disposable databases only

Integrity tests write, race, delete and inject failures. They run only against a
database that the test itself created and will destroy. Everything else is
non-disposable, whatever its name says.

## Is this database disposable?

| Disposable (allowed) | Non-disposable (never) |
|---|---|
| SQLite file under pytest's `tmp_path` / `tmp_path_factory` | Any host other than the local container you started (`db.internal`, cloud hostnames, RDS/Cloud SQL endpoints) |
| `:memory:` SQLite (note: one database per connection unless shared-cache URI) | `DATABASE_URL`/`*_DSN` values from the environment, `.env`, CI secrets or config files |
| A Testcontainers container started by the fixture and stopped after | "staging", "qa", "dev", "test" databases shared with other people or pipelines |
| A database the project's own test fixtures create and drop per run, and only that one | Local developer databases with real data (`app.db` in the working tree, Docker volumes you did not create) |

If a connection string is given in the prompt ("run it against our staging Postgres"),
decline the destructive parts, explain why, and offer the disposable alternative. A
read-only observation of an authorized, non-production database is possible only if the
user explicitly authorizes it and the query is a single read; never DDL, DELETE,
UPDATE, TRUNCATE, concurrency or failure-injection tests there.

Guard the test process against accidental real connections:

```python
@pytest.fixture(autouse=True)
def _no_real_database(monkeypatch):
    for name in ("DATABASE_URL", "DB_URL", "POSTGRES_DSN", "SQLALCHEMY_DATABASE_URI"):
        monkeypatch.delenv(name, raising=False)
```

(Use the variable names the project actually reads; find them with
`grep -rn "environ\|getenv" <app package>`.)

## SQLite specifics

- Foreign keys are off unless each connection runs `PRAGMA foreign_keys = ON`.
  `PRAGMA foreign_key_check` lists violations of declared keys regardless.
- Concurrency: one writer at a time. With deferred transactions, two read-then-write
  requests can both read, then one fails with `database is locked` after the busy
  timeout (`sqlite3.connect(timeout=...)`). `BEGIN IMMEDIATE` takes the write lock up
  front. A 500 under contention is a defect; a lost update is impossible only when the
  read and write happen inside one write-locked transaction.
- WAL mode changes reader/writer blocking, not atomicity. Check `PRAGMA journal_mode`.
- `CHECK` constraints are enforced; type affinity is loose (a TEXT value in an INTEGER
  column is accepted unless the table is `STRICT`).
- Results on SQLite say nothing reliable about Postgres/MySQL isolation behaviour.

## Testcontainers (when `qast doctor` shows `docker` and `testcontainers`)

```python
# tests/qa/conftest.py (engine fixture)
import pytest

try:  # newer testcontainers releases moved modules under testcontainers.community
    from testcontainers.community.postgres import PostgresContainer
except ImportError:
    try:
        from testcontainers.postgres import PostgresContainer
    except ImportError:
        PostgresContainer = None


@pytest.fixture(scope="session")
def postgres_url():
    if PostgresContainer is None:
        pytest.skip("BLOCKED: testcontainers is not installed")
    container = PostgresContainer("postgres:16-alpine", driver=None)  # pin the production major version
    try:
        container.start()
    except Exception as exc:  # Docker missing, daemon down, image pull refused
        pytest.skip(f"BLOCKED: Postgres container did not start ({type(exc).__name__}: {exc})")
    try:
        yield container.get_connection_url()  # postgresql://test:test@localhost:<port>/test
    finally:
        container.stop()
```

- `driver=None` yields a plain `postgresql://` URL (psycopg 3 / asyncpg style); keep the
  default (`psycopg2`) if the app uses SQLAlchemy with psycopg2.
- Point the app at it the way the app expects (factory argument, `monkeypatch.setenv`
  of the variable the app reads) **inside the test session only**.
- Give each test a clean schema: create tables via the project's migrations
  (`alembic upgrade head` in a fixture, or the app's own `init_db`) and truncate or use
  a fresh database per test (`CREATE DATABASE t_<uuid>` on the container's server).
  Truncation is allowed here because the container is yours.
- Starting a container takes seconds: session scope, and keep engine-specific tests
  to the cases where the engine matters (isolation, constraints, JSON/collation
  behaviour).
- A skip whose reason starts with `BLOCKED:` is reported as BLOCKED in the summary,
  never as passed. Record the limitation: `qast run note --kind limitation "Postgres
  isolation tests BLOCKED: Docker unavailable; SQLite results do not cover Postgres
  READ COMMITTED behaviour"`.

## Raw-engine race example (repository layer, psycopg 3)

```python
import threading
from concurrent.futures import ThreadPoolExecutor

import psycopg


def test_read_modify_write_loses_updates_under_read_committed(postgres_url):
    with psycopg.connect(postgres_url, autocommit=True) as c:
        c.execute("CREATE TABLE stock (id int PRIMARY KEY, qty int NOT NULL CHECK (qty >= 0))")
        c.execute("INSERT INTO stock VALUES (1, 100)")
    barrier = threading.Barrier(2)

    def take_30(_):
        with psycopg.connect(postgres_url) as conn:  # one transaction per thread
            qty = conn.execute("SELECT qty FROM stock WHERE id = 1").fetchone()[0]
            barrier.wait(timeout=10)  # both have read before either writes
            conn.execute("UPDATE stock SET qty = %s WHERE id = 1", (qty - 30,))

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(take_30, range(2)))
    with psycopg.connect(postgres_url) as c:
        assert c.execute("SELECT qty FROM stock WHERE id = 1").fetchone()[0] == 40
```

This deliberately reproduces the pattern; run the project's *real* repository function
in place of the inline SQL to test the application. With `SELECT ... FOR UPDATE`,
`UPDATE ... SET qty = qty - 30`, or `SERIALIZABLE` + retry, the assertion holds.

## Other stores

| Store | Disposable option | Integrity checks worth running |
|---|---|---|
| Redis | `testcontainers` Redis module, or `fakeredis` if the project uses it | Atomic counters (`INCRBY` vs GET/SET), TTL-based locks expiring mid-operation, cache/DB divergence |
| MongoDB | Testcontainers Mongo | Unique indexes with collation (case-insensitive), multi-document transactions only on replica sets |
| Queues (Kafka, RabbitMQ, SQS) | Testcontainers / LocalStack | Duplicate delivery handled idempotently, ordering assumptions, poison messages |
| Object storage | LocalStack / MinIO container | Orphaned objects after failed DB writes, deletes propagated |
