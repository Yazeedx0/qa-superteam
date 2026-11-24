# Reliability checklist

Use it twice: during inspection (each "no" is a hypothesis to test) and at the end (each
row needs a status in the summary: PASSED / FAILED / INCONCLUSIVE / BLOCKED / proposed /
not applicable).

## Timeouts

- [ ] Every outbound call (HTTP, DB, cache, queue, SDK) has a connect **and** read timeout.
      Watch for libraries without defaults: `requests`, `urllib.request.urlopen`, many DB
      drivers, `subprocess.run` without `timeout=`.
- [ ] Timeouts are shorter than the caller's own deadline (a 30 s upstream timeout behind a
      10 s gateway timeout wastes work and holds resources).
- [ ] A timeout surfaces as the documented error (status code, exception type), not a
      generic 500, not `None`, not an empty success.

## Retries

- [ ] Retries happen only for transient failures (timeouts, connection errors, 502/503/504,
      429), never for 400/401/403/404/409/422.
- [ ] Attempts are capped; total wait is bounded and fits the caller's deadline.
- [ ] Backoff is exponential with jitter; `Retry-After` is honoured.
- [ ] Non-idempotent operations retry only with an idempotency key that is the same on
      every attempt, and the server deduplicates on it.
- [ ] Retries are not layered (client retries × SDK retries × gateway retries multiply load).

## Partial failure and transactions

- [ ] Multi-step writes are atomic (one transaction) or compensated; a failure after step 1
      leaves no half-applied state.
- [ ] External side effects (emails, payments, webhooks) happen after commit, or through an
      outbox, so a rollback cannot leave an orphan side effect.
- [ ] Exceptions are not swallowed: `except Exception: pass` / logging-and-continuing on
      write paths is a defect candidate.

## Idempotency and duplication

- [ ] Message consumers are idempotent (dedupe on message or business id).
- [ ] Repeating a request with the same idempotency key returns the original result and moves nothing twice.
- [ ] Reusing a key with a different body is rejected (if the contract says so).
- [ ] Keys are scoped correctly (per user or per client), so two users' keys never collide.

## Concurrency

- [ ] Check-then-act sequences on shared state hold a lock, row lock (`SELECT ... FOR UPDATE`),
      use an atomic statement (`UPDATE ... SET x = x - ? WHERE x >= ?`) or a serializable transaction.
- [ ] Uniqueness is enforced by a database constraint, not only by a prior `SELECT`.
- [ ] In-memory caches and singletons are thread-safe or per-request.
- [ ] The test environment's database can show the race (see SQLite note in race-condition-patterns.md).

## Circuit breakers, bulkheads, degradation

- [ ] A failing dependency trips a breaker (or equivalent) so callers fail fast instead of piling up.
- [ ] Half-open lets a limited number of trial calls through; success closes the breaker.
- [ ] Pools (DB connections, worker threads) are bounded; one slow dependency cannot exhaust them for all routes.
- [ ] Degraded responses are explicit (flag, header, status) and documented.

## Reconnection and recovery

- [ ] Clients reconnect after the dependency returns, without process restart.
- [ ] Startup tolerates a dependency that is not ready yet (retry with deadline, or fail fast with a clear error).
- [ ] Background workers resume pending work after a crash without duplicating completed work.
- [ ] Health checks reflect dependency state accurately (not always "ok").

## Tests themselves

- [ ] No fixed `sleep` used to wait for effects; polling with a deadline or fake time instead.
- [ ] Each injected fault is undone by fixture teardown (monkeypatch, context managers).
- [ ] Every thread/event wait has a timeout.
- [ ] Intermittent outcomes are reported with their rate, not retried until green.
