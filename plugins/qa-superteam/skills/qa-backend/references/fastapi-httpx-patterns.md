# FastAPI / httpx test patterns (pytest 8+, httpx 0.27+)

The examples assume an app factory `create_app(db_path: str)` in `app.main`, bearer-token
auth (`/auth/register`, `/auth/login`), and three resources: `/documents/{id}` (owned by a
user), `/payments` (accepts `Idempotency-Key`, calls a payment gateway obtained through the
dependency `get_gateway`) and `/products/{id}/reserve` (decrements stock). Adapt names to
the project; keep the structure. **Reuse the project's own fixtures first** (an existing
`client`, user factory or DB fixture in `tests/conftest.py` is inherited by `tests/qa/`).

## Fixtures: isolated app, two real users, a fake integration

```python
# tests/qa/conftest.py  (only fixtures the project does not already provide)
import itertools
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient

from app.main import create_app, get_gateway

PASSWORD = "correct-horse-battery-staple"


@pytest.fixture
def app(tmp_path):
    # A fresh file database per test: disposable, isolated, safe for destructive cases.
    return create_app(str(tmp_path / "qa.db"))


@pytest.fixture
def client(app):
    # The context manager runs lifespan startup/shutdown handlers.
    with TestClient(app) as c:
        yield c


@pytest.fixture
def raw_client(app):
    # Unhandled server exceptions become observable 500 responses instead of being
    # re-raised inside the test (where they would look like a broken test).
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@dataclass
class Actor:
    email: str
    user_id: int
    headers: dict


@pytest.fixture
def make_actor(client):
    seq = itertools.count(1)

    def make() -> Actor:
        email = f"qa-user-{next(seq)}@example.com"
        r = client.post("/auth/register", json={"email": email, "password": PASSWORD})
        assert r.status_code == 201, r.text
        user_id = r.json()["user_id"]
        r = client.post("/auth/login", json={"email": email, "password": PASSWORD})
        assert r.status_code == 200, r.text
        return Actor(email, user_id, {"Authorization": f"Bearer {r.json()['token']}"})

    return make


@pytest.fixture
def alice(make_actor):
    return make_actor()


@pytest.fixture
def mallory(make_actor):
    return make_actor()


class FakeGateway:
    """Records every charge; can be told to fail."""

    def __init__(self):
        self.charges: list[tuple] = []
        self.fail_with: Exception | None = None

    def charge(self, amount_cents, currency, reference):
        if self.fail_with is not None:
            raise self.fail_with
        self.charges.append((amount_cents, currency, reference))
        return f"ch_{len(self.charges)}"


@pytest.fixture
def gateway(app):
    fake = FakeGateway()
    app.dependency_overrides[get_gateway] = lambda: fake  # looked up per request
    yield fake
    app.dependency_overrides.clear()
```

Two *real* users through the public API, not hand-made tokens: authorization bugs hide
in how identities are resolved.

## Object-level authorization (BOLA / IDOR)

```python
# tests/qa/test_qa_authz.py
import pytest

MUTATIONS = [
    ("GET", {}),
    ("PATCH", {"json": {"title": "changed by another user"}}),
    ("DELETE", {}),
]


@pytest.mark.parametrize(("method", "kwargs"), MUTATIONS, ids=[m for m, _ in MUTATIONS])
def test_foreign_document_is_indistinguishable_from_missing(client, alice, mallory, method, kwargs):
    created = client.post("/documents", json={"title": "salary review", "body": "confidential"}, headers=alice.headers)
    assert created.status_code == 201, created.text
    doc_id = created.json()["id"]

    foreign = client.request(method, f"/documents/{doc_id}", headers=mallory.headers, **kwargs)
    missing = client.request(method, f"/documents/{doc_id + 100_000}", headers=mallory.headers, **kwargs)

    # Oracle: requirement "another user's document behaves exactly like one that does not exist"
    assert foreign.status_code == 404, foreign.text
    assert (foreign.status_code, foreign.json()) == (missing.status_code, missing.json())

    owner_view = client.get(f"/documents/{doc_id}", headers=alice.headers)
    assert owner_view.status_code == 200
    assert owner_view.json()["title"] == "salary review"  # nothing leaked, nothing changed


def test_lists_contain_only_own_objects(client, alice, mallory):
    client.post("/documents", json={"title": "a1"}, headers=alice.headers)
    client.post("/documents", json={"title": "m1"}, headers=mallory.headers)
    titles = [d["title"] for d in client.get("/documents", headers=alice.headers).json()]
    assert titles == ["a1"]


def test_owner_cannot_be_reassigned_through_the_body(client, alice, mallory):
    r = client.post("/documents", json={"title": "x", "owner_id": mallory.user_id}, headers=alice.headers)
    assert r.status_code in (201, 422), r.text
    if r.status_code == 201:  # extra field ignored: owner must still be the caller
        assert r.json()["owner_id"] == alice.user_id
        assert client.get("/documents", headers=mallory.headers).json() == []
```

Where authorization bugs hide (test each one that exists):

- ids in the **path** (`/documents/{id}`), in the **query** (`?account_id=`), and in the
  **body** (`{"from_account_id": ...}`, `{"document_ids": [...]}`): a write that takes a
  source object from the body must check the caller owns it;
- secondary endpoints: list, search, export, count, download, nested
  (`/documents/{id}/comments`), bulk operations;
- every HTTP method on the same path (GET protected, PATCH forgotten);
- "indistinguishable" oracle: same status *and* same body as a missing id, otherwise
  existence leaks (enumeration);
- function level (BFLA): a normal user calling admin endpoints, or a user setting
  `role`/`is_admin`/`balance` via mass assignment.

## Authentication matrix

```python
# tests/qa/test_qa_authn.py
import pytest

# Valid-shaped bodies: the credential is the only thing wrong with each request.
PROTECTED = [
    ("GET", "/documents", None),
    ("POST", "/documents", {"title": "x"}),
    ("GET", "/documents/1", None),
    ("POST", "/payments", {"amount_cents": 100}),
]
BAD_HEADERS = {
    "missing": {},
    "empty-bearer": {"Authorization": "Bearer "},
    "garbage": {"Authorization": "Bearer not-a-token"},
    "wrong-scheme": {"Authorization": "Basic dXNlcjpwYXNz"},
}


@pytest.mark.parametrize(("method", "path", "body"), PROTECTED, ids=[f"{m} {p}" for m, p, _ in PROTECTED])
@pytest.mark.parametrize("variant", list(BAD_HEADERS))
def test_protected_endpoints_reject_bad_credentials(raw_client, gateway, method, path, body, variant):
    r = raw_client.request(method, path, headers=BAD_HEADERS[variant], json=body)
    assert r.status_code == 401, (variant, r.status_code, r.text)
    assert gateway.charges == []  # nothing happened on behalf of nobody
```

Add expired tokens when the app exposes a clock seam (patch the module's `now`
function) and tokens of a deleted or disabled user when the API supports deletion.
Whether 401 also wins over 422 for an *invalid* body is a separate, lower-severity check
(schema disclosure to anonymous callers); keep it out of this oracle so a validation-order
choice is not reported as an authentication defect.

## Validation boundaries and the error contract

```python
# tests/qa/test_qa_validation.py
import pytest

INVALID_PAYMENTS = {
    "zero": {"amount_cents": 0},
    "negative": {"amount_cents": -1},
    "above-max": {"amount_cents": 1_000_001},
    "float": {"amount_cents": 10.5},
    "numeric-string": {"amount_cents": "100"},
    "bool": {"amount_cents": True},
    "null": {"amount_cents": None},
    "int64-overflow": {"amount_cents": 2**63},
    "missing": {},
}


@pytest.mark.parametrize("payload", list(INVALID_PAYMENTS.values()), ids=list(INVALID_PAYMENTS))
def test_invalid_payment_is_rejected_cleanly_and_charges_nothing(raw_client, alice, gateway, payload):
    r = raw_client.post("/payments", json=payload, headers=alice.headers)
    assert r.status_code == 422, r.text
    assert "detail" in r.json()
    lowered = r.text.lower()
    assert "traceback" not in lowered and "sqlite" not in lowered and "select " not in lowered
    assert gateway.charges == []
    assert raw_client.get("/payments", headers=alice.headers).json() == []


@pytest.mark.parametrize("amount", [1, 1_000_000], ids=["min", "max"])
def test_payment_limits_are_inclusive(client, alice, gateway, amount):
    r = client.post("/payments", json={"amount_cents": amount}, headers=alice.headers)
    assert r.status_code == 201, r.text
```

The rejection oracle has three parts: the status code from the requirement, a stable
error body shape, and **no side effect** (re-read state, check the fake integration).
Bodies must not contain stack traces, SQL, file paths or other users' data.

## Idempotency

```python
# tests/qa/test_qa_idempotency.py
import threading
from concurrent.futures import ThreadPoolExecutor

BODY = {"amount_cents": 1500, "currency": "USD"}


def test_retry_with_same_key_returns_original_and_charges_once(client, alice, gateway):
    headers = {**alice.headers, "Idempotency-Key": "qa-key-1"}
    first = client.post("/payments", json=BODY, headers=headers)
    retry = client.post("/payments", json=BODY, headers=headers)
    assert first.status_code == 201, first.text
    assert (retry.status_code, retry.json()) == (first.status_code, first.json())
    assert len(gateway.charges) == 1
    assert len(client.get("/payments", headers=alice.headers).json()) == 1


def test_same_key_with_different_body_is_a_conflict(client, alice, gateway):
    headers = {**alice.headers, "Idempotency-Key": "qa-key-2"}
    assert client.post("/payments", json=BODY, headers=headers).status_code == 201
    r = client.post("/payments", json={**BODY, "amount_cents": 1501}, headers=headers)
    assert r.status_code == 409, r.text
    assert len(gateway.charges) == 1


def test_keys_are_scoped_per_user(client, alice, mallory, gateway):
    a = client.post("/payments", json=BODY, headers={**alice.headers, "Idempotency-Key": "shared"})
    m = client.post("/payments", json=BODY, headers={**mallory.headers, "Idempotency-Key": "shared"})
    assert a.status_code == m.status_code == 201
    assert a.json()["id"] != m.json()["id"]
    assert len(gateway.charges) == 2


def test_concurrent_retries_with_same_key_charge_once(client, alice, gateway):
    headers = {**alice.headers, "Idempotency-Key": "qa-key-race"}
    n = 8
    barrier = threading.Barrier(n)

    def send(_):
        barrier.wait(timeout=10)
        return client.post("/payments", json=BODY, headers=headers)

    with ThreadPoolExecutor(max_workers=n) as pool:
        responses = list(pool.map(send, range(n)))

    assert {r.status_code for r in responses} <= {201, 409}, [r.status_code for r in responses]
    assert len({r.json()["id"] for r in responses if r.status_code == 201}) == 1
    assert len(gateway.charges) == 1
```

Also check: the key's length/charset limits, a retry *after* the first request failed
(gateway timeout: the retry must be allowed to succeed, not replay the failure forever,
unless the contract says otherwise), and key expiry if documented.

## Concurrency: invariants under parallel requests

```python
# tests/qa/test_qa_concurrency.py
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest


@pytest.mark.parametrize("attempt", range(3))  # races are probabilistic: bounded repeats
def test_parallel_reservations_never_oversell(client, alice, attempt):
    product = client.post("/products", json={"stock": 5}, headers=alice.headers).json()
    n = 12
    barrier = threading.Barrier(n)

    def reserve(_):
        barrier.wait(timeout=10)  # release all requests at once
        return client.post(f"/products/{product['id']}/reserve", json={"qty": 1}, headers=alice.headers)

    with ThreadPoolExecutor(max_workers=n) as pool:
        codes = [r.status_code for r in pool.map(reserve, range(n))]

    assert set(codes) <= {200, 409}, codes  # no 500s, no lock timeouts leaking out
    assert codes.count(200) == 5, codes
    assert client.get(f"/products/{product['id']}", headers=alice.headers).json()["stock"] == 0
```

- `TestClient` from many threads works: sync (`def`) endpoints run in a thread pool, so
  their database code truly overlaps; `async def` endpoints interleave only at `await`.
- A pass does not prove absence of a race; a single failure is real evidence but must be
  reproduced (`qast reproduce`) before it is a claim.
- SQLite serialises writers; a race that cannot happen on SQLite may happen on Postgres
  and vice versa. When production uses another engine and Docker is available, rerun the
  concurrency cases against it (Testcontainers patterns in `qa-data-integrity`).
- For real sockets and a real server loop use the live fixture below with one
  `httpx.Client` per thread.

## Failure injection: no partial effects

```python
# tests/qa/test_qa_failures.py
def test_gateway_timeout_returns_gateway_error_and_records_nothing(raw_client, alice, gateway):
    gateway.fail_with = TimeoutError("provider timed out")
    r = raw_client.post("/payments", json={"amount_cents": 500}, headers=alice.headers)
    assert r.status_code in (502, 503, 504), r.text
    assert raw_client.get("/payments", headers=alice.headers).json() == []


def test_unexpected_gateway_error_is_not_reported_as_success(raw_client, alice, gateway):
    gateway.fail_with = RuntimeError("boom")
    r = raw_client.post("/payments", json={"amount_cents": 500}, headers=alice.headers)
    assert r.status_code >= 500
    assert "boom" not in r.text  # internal error text must not leak
    assert raw_client.get("/payments", headers=alice.headers).json() == []
```

Inject at the seam the app already offers (dependency override, injected client,
`monkeypatch.setattr(module, "function", failing)` on the name the module calls). Fail
*after* the first write when possible: that is where missing transactions show up.

## Outbound HTTP integrations without a network

```python
import httpx


def payments_api(request: httpx.Request) -> httpx.Response:
    if request.method == "POST" and request.url.path == "/v1/charges":
        return httpx.Response(503, json={"error": "temporarily unavailable"})
    return httpx.Response(404)


fake_http = httpx.Client(transport=httpx.MockTransport(payments_api), base_url="https://payments.invalid")
# app.dependency_overrides[get_http_client] = lambda: fake_http
```

Cover: 5xx, 4xx with error bodies, timeouts (`raise httpx.ReadTimeout("t", request=request)`
inside the handler), malformed JSON, slow responses vs configured timeouts, retries that
must not duplicate side effects. `respx` is fine if the project already uses it.

## Async tests (only if the project already has an async test setup)

```python
import httpx
import pytest


@pytest.mark.anyio
async def test_health_async(app):
    transport = httpx.ASGITransport(app=app)  # note: does not run lifespan handlers
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
        r = await ac.get("/documents")
    assert r.status_code == 401
```

`pytest.mark.anyio` needs the anyio pytest plugin (installed with anyio);
`pytest-asyncio` projects use `@pytest.mark.asyncio`. If startup code matters, keep using
`TestClient` as a context manager.

## A real server in a thread (for socket-level behaviour)

```python
import threading
import time

import httpx
import pytest
import uvicorn

from app.main import create_app


@pytest.fixture
def live_base_url(tmp_path):
    app = create_app(str(tmp_path / "live.db"))
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:  # poll with a deadline, never a fixed sleep
        if not thread.is_alive() or time.monotonic() > deadline:
            pytest.fail("API server did not start within 10 s")
        time.sleep(0.05)
    port = server.servers[0].sockets[0].getsockname()[1]
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=10)


def test_health_over_tcp(live_base_url):
    with httpx.Client(base_url=live_base_url, timeout=10) as c:
        assert c.get("/documents").status_code == 401
```

## Authorized live targets only

When the user asks to test a running deployment, the URL must fall under
`permissions.authorized_targets` (`.qa-superteam/config.toml`; default
`http://127.0.0.1`, `http://localhost`). Read it before writing a single request.

```python
import os

import httpx
import pytest

BASE_URL = os.environ.get("QA_BASE_URL")  # set by the command line, never hard-coded


@pytest.fixture(scope="session")
def live():
    if not BASE_URL:
        pytest.skip("QA_BASE_URL not set; live checks not run")
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as c:
        yield c
```

`QA_BASE_URL=http://127.0.0.1:8000 qast exec pytest --group critical-journeys -- tests/qa/test_qa_live_smoke.py`

Against live targets: read-only or self-cleaning requests on test accounts the user
provided, no destructive operations, no bulk or parallel traffic, and no authorization
probing or injection payloads unless `permissions.allow_active_security = true`. A
skipped live test is NOT_RUN evidence, never a pass.

## Running and recording

```bash
qast exec pytest --group critical-journeys --label qa-backend-authz -- tests/qa/test_qa_authz.py
qast reproduce --test "tests/qa/test_qa_authz.py::test_foreign_document_is_indistinguishable_from_missing[GET]" --times 3
```

Use the identifiers exactly as `qast exec` printed them (parametrized ids included).
