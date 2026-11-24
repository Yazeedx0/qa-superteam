# In-process fault injection patterns (pytest)

Every pattern here runs in the test process: no network, no containers, no permissions
needed. The snippets were executed against a small client with retries, backoff, an
idempotency key and a circuit breaker; adapt names (`payclient`, `PayClient`, `charge`) to
the project's code. Patch names **where they are looked up**: if the module does
`import time`, patch `module.time.sleep`; if it does `from time import sleep`, patch `module.sleep`.

## Shared helpers

```python
import httpx
import pytest

import payclient                      # the module under test


def flaky_transport(failures, exc=httpx.ConnectTimeout, ok_json=None):
    """Fail the first `failures` requests, then answer 200. Records every request.

    exc: an httpx exception class to raise, or an int HTTP status to return.
    """
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if len(seen) <= failures:
            if isinstance(exc, int):
                return httpx.Response(exc, json={"error": "injected"})
            raise exc("injected", request=request)
        return httpx.Response(200, json=ok_json or {"status": "ok"})

    return httpx.MockTransport(handler), seen


@pytest.fixture
def sleeps(monkeypatch):
    """Record backoff delays instead of sleeping: fast and assertable."""
    recorded = []
    monkeypatch.setattr(payclient.time, "sleep", recorded.append)
    return recorded
```

## Retry recovers, and reuses the idempotency key

```python
def test_retry_recovers_and_reuses_idempotency_key(sleeps):
    transport, seen = flaky_transport(failures=2)
    client = payclient.PayClient("https://pay.test", transport=transport)
    assert client.charge(4999) == {"status": "ok"}
    assert len(seen) == 3
    keys = {r.headers["Idempotency-Key"] for r in seen}
    assert len(keys) == 1, f"retries used different idempotency keys: {keys}"
```

A retried `POST` with a fresh key per attempt can charge twice when the first attempt
succeeded server-side but the response was lost (read timeout). Inject `httpx.ReadTimeout`
to model exactly that.

## Retries are capped and backoff is bounded

```python
def test_retries_are_capped_and_backoff_is_bounded(sleeps, monkeypatch):
    monkeypatch.setattr(payclient.random, "uniform", lambda lo, hi: hi)  # worst-case jitter
    transport, seen = flaky_transport(failures=100, exc=503)
    client = payclient.PayClient("https://pay.test", transport=transport,
                                 max_attempts=4, base_delay=0.2, max_delay=0.5)
    with pytest.raises(httpx.HTTPStatusError):
        client.charge(100)
    assert len(seen) == 4                      # cap
    assert sleeps == [0.2, 0.4, 0.5]           # exponential, capped at max_delay
    assert sum(sleeps) <= 2.0                  # bounded total wait (from the contract)
```

Also worth one test each: non-retryable errors (400, 401, 422) are **not** retried; a 429
with `Retry-After` waits at least that long; the final error surfaces with the documented
type instead of `None` or a generic exception.

## Timeouts are declared

```python
def test_client_declares_timeouts():
    client = payclient.PayClient("https://pay.test",
                                 transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})))
    t = client.http.timeout
    assert t.connect is not None and t.read is not None, "unbounded timeouts can hang forever"
```

`httpx` defaults to 5 s; `requests` and `urllib.request.urlopen` default to **no timeout**.
For `requests`, assert the `timeout=` argument by patching the call:

```python
import requests

import rates as sut_module          # the module that calls requests.get


def test_requests_call_passes_timeout(monkeypatch):
    seen = {}

    def fake_get(url, **kwargs):
        seen.update(kwargs)
        raise requests.exceptions.ConnectTimeout("injected")

    monkeypatch.setattr(sut_module.requests, "get", fake_get)
    with pytest.raises(sut_module.UpstreamUnavailable):   # the project's documented error
        sut_module.fetch_rates()
    assert seen.get("timeout") is not None
```

## The code under test builds its own client

Inject the transport by wrapping the constructor the module uses:

```python
def test_sut_built_client_gets_injected_transport(monkeypatch):
    transport, seen = flaky_transport(failures=1)
    real_client = httpx.Client
    monkeypatch.setattr(payclient.httpx, "Client",
                        lambda *a, **kw: real_client(*a, **{**kw, "transport": transport}))
    monkeypatch.setattr(payclient.time, "sleep", lambda s: None)
    assert payclient.PayClient("https://pay.test").charge(10) == {"status": "ok"}
    assert len(seen) == 2
```

`payclient.httpx` is the shared `httpx` module, so the patch is global for the duration of
the test; monkeypatch restores it afterwards.

## Async clients

`MockTransport` accepts an async handler for `httpx.AsyncClient`. Without an async pytest
plugin, drive the coroutine with `asyncio.run` inside a normal test; with one, use the
project's marker (`@pytest.mark.anyio` or `@pytest.mark.asyncio`).

```python
def test_async_client_read_timeout_surfaces():
    import asyncio

    async def handler(request):
        raise httpx.ReadTimeout("injected", request=request)

    async def main():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://x.test") as c:
            await c.get("/")

    with pytest.raises(httpx.ReadTimeout):
        asyncio.run(main())
```

## Circuit breaker with a fake clock

```python
def test_breaker_opens_then_half_opens_with_fake_clock(sleeps):
    now = [1000.0]
    breaker = payclient.Breaker(threshold=2, cooldown_s=30, clock=lambda: now[0])
    transport, seen = flaky_transport(failures=10**6)
    client = payclient.PayClient("https://pay.test", transport=transport, max_attempts=1, breaker=breaker)
    for _ in range(2):
        with pytest.raises(httpx.ConnectTimeout):
            client.charge(1)
    calls = len(seen)
    with pytest.raises(payclient.CircuitOpen):
        client.charge(1)
    assert len(seen) == calls, "open breaker must not touch the dependency"
    now[0] += 31                                   # cooldown elapsed: half-open
    with pytest.raises(httpx.ConnectTimeout):
        client.charge(1)
    assert len(seen) == calls + 1                  # exactly one trial call
```

If the code reads `time.monotonic()` directly instead of an injectable clock, patch it in
the module: `monkeypatch.setattr(mod.time, "monotonic", lambda: now[0])`. Use `freezegun`
or `time-machine` only if the project already depends on them.

## Duplicate delivery (at-least-once consumers)

```python
def test_duplicate_delivery_applies_once():
    ledger = Ledger()                                   # the consumer under test, on a temp DB
    msg = {"id": "msg-1", "account": 2, "amount_cents": 500}
    ledger.handle(msg)
    ledger.handle(msg)  # the broker redelivers after a lost ack
    assert ledger.balance(2) == 500
```

Variations: redelivery after the handler crashed mid-way (patch a later step to raise on the
first call only), out-of-order delivery of two related messages, the same logical event with
a new message id (idempotency must key on the business id, if the contract says so).

## Partial failure rolls back

```python
def test_failure_after_debit_rolls_back(monkeypatch):
    ledger = Ledger()

    def boom(*args, **kwargs):
        raise RuntimeError("injected: credit step failed")

    monkeypatch.setattr(ledger, "credit", boom)
    with pytest.raises(RuntimeError):
        ledger.transfer(1, 2, 300)
    assert (ledger.balance(1), ledger.balance(2)) == (1000, 0)
```

Through an HTTP API, build `TestClient(app, raise_server_exceptions=False)` and assert the
5xx plus the unchanged balances read back through the API. The oracle is the stored state,
never the response alone.

## Reconnection and recovery

- Fail the first N connection attempts (transport or patched `connect`), then succeed:
  the client reconnects without a restart, with bounded backoff, and does not replay
  non-idempotent work.
- After the fault clears, the next request succeeds (no permanently poisoned pool or cached failure).
- Long outage: the component reports unhealthy (health endpoint, metric) instead of hanging.

## Graceful degradation

With the dependency failing, the user-facing operation returns the documented fallback
(cached value with a staleness flag, partial page, queued for later) within the time
budget, and logs or metrics record the degradation. A 500, an empty success, or stale data
presented as fresh are failures.

## Waiting for asynchronous effects

```python
import time


def poll_until(predicate, timeout_s=5.0, interval_s=0.05):
    deadline = time.monotonic() + timeout_s
    while True:
        value = predicate()
        if value:
            return value
        if time.monotonic() >= deadline:
            raise AssertionError(f"condition not met within {timeout_s}s")
        time.sleep(interval_s)
```

Use it for background jobs, consumers and eventual consistency. The deadline makes a missing
effect a FAILED test instead of a hang; the short interval keeps passing tests fast.

## Process and network level (permission required)

Only with `permissions.allow_fault_injection = true`, a disposable environment, and tools
the project already uses: toxiproxy (latency, bandwidth, `reset_peer`, timeouts between the
app and a dependency), stopping a throwaway database container mid-test, or testcontainers
fixtures. Never against shared or production systems. Without permission, record the
process-level case as BLOCKED or proposed and cover the same failure in-process.
