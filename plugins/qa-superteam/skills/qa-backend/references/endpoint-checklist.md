# Per-endpoint checklist

Work through this per endpoint in risk order (money, auth, personal data, irreversible
writes first). Each line is a question; a "no/unknown" becomes a test case (with an
oracle) or an explicit out-of-scope entry. Skip rows that cannot apply and say why in the
plan, not silently.

## 0. Inventory (once per service)

- [ ] Route list with methods, auth requirement and owning resource. FastAPI:
      `python3 -c "import json; from app.main import create_app; print(json.dumps(create_app('/tmp/x.db').openapi()['paths'], indent=1))"`
      (or `app.routes`), Flask: `app.url_map`, Express: router stacks, Spring: `@RequestMapping` scan.
- [ ] Undocumented routes (in code, not in the spec or docs): test them like the rest.
- [ ] Identity model: how the caller is resolved (dependency, middleware), roles, tenants.
- [ ] Data stores, transactions (where they begin/commit), background jobs, caches,
      outbound integrations, feature flags.
- [ ] Requirements and invariants that each endpoint must preserve.

## 1. Authentication

- [ ] Missing, malformed, wrong-scheme, expired, revoked tokens → 401 with no data.
- [ ] (Lower severity) 401 rather than 422 for anonymous requests with invalid bodies
      (no schema disclosure); test it separately from the credential matrix.
- [ ] Login errors do not reveal whether the account exists (same status, body, and
      roughly the same work for unknown email vs wrong password).
- [ ] Identifiers compared the way the requirement says (e.g. email case-insensitive).
- [ ] Session/token lifetime matches the requirement at the exact boundary.

## 2. Authorization

- [ ] Object level: every id in path, query and body checked against the caller
      (owner/tenant/membership), for every method on the path.
- [ ] Foreign object indistinguishable from a missing one when the requirement says so
      (status and body).
- [ ] Lists/search/export/count return only the caller's objects.
- [ ] Function level: non-admin cannot reach admin operations; role cannot be raised via
      the body (mass assignment of `role`, `is_admin`, `owner_id`, `balance`, `status`).
- [ ] Cross-tenant: same checks with two tenants when multi-tenant.

## 3. Input validation

- [ ] Each field: type, required/optional, null, boundaries (min-1, min, max, max+1),
      length limits, format (email, dates, currency codes), enum membership.
- [ ] Type confusion: `"10"` vs `10`, `10.0`, `true`, arrays/objects where scalars are
      expected, int64 overflow, NaN/Infinity where JSON parsers accept them.
- [ ] Strings: leading/trailing whitespace, Unicode normalisation, zero-width characters,
      very long input, control characters.
- [ ] Unknown fields: ignored or rejected as documented, never applied.
- [ ] Rejected requests leave state unchanged (re-read; check fakes).

## 4. Business rules and state

- [ ] Every stated rule has a test with values that separate correct from plausible-wrong
      implementations (rounding direction, inclusive/exclusive limits, fees).
- [ ] Invariants hold after success *and* after rejection (never-negative, conservation,
      uniqueness).
- [ ] State transitions: illegal transitions rejected, terminal states final.
- [ ] Self-referencing operations (transfer to self, follow self, approve own request).

## 5. Error contract

- [ ] Status codes as documented (400/401/403/404/409/422/429), consistent across
      endpoints.
- [ ] Error body shape stable and machine-readable; no stack traces, SQL, file paths,
      internal hostnames or other users' data.
- [ ] Unhandled exceptions surface as 5xx with a generic body (use
      `raise_server_exceptions=False` to observe this).

## 6. Persistence and transactions

- [ ] Multi-write operations are atomic: inject a failure after the first write and check
      no partial state remains.
- [ ] Constraints enforced in the database, not only in Python (uniqueness, foreign keys,
      non-negative checks) when the requirement is absolute.
- [ ] Deletes: cascades/soft-delete semantics as documented; deleted objects disappear
      from every read path. Depth in `qa-data-integrity`.

## 7. Concurrency and idempotency

- [ ] Parallel identical writes (barrier + thread pool) preserve invariants; no 500s.
- [ ] Idempotency key: replay returns the original response, effects once, conflicting
      body rejected, scoped per user, concurrent replays charge once.
- [ ] Optimistic locking/version fields reject stale updates, when present.

## 8. Asynchronous work

- [ ] Background tasks/jobs: run synchronously in tests if the framework allows (eager
      mode, direct call of the task function) and assert their effects.
- [ ] Otherwise poll the observable effect with a deadline; a timeout is FAILED (or
      INCONCLUSIVE if the environment is suspect), never a reason to add `sleep`.
- [ ] Job failure and retry do not duplicate effects; poison messages do not block the
      queue.

## 9. Caching

- [ ] Write-then-read returns the new value (no stale cache).
- [ ] Cache keys include the caller/tenant: user B never receives user A's cached body.
- [ ] Authenticated responses carry `Cache-Control: private` or `no-store` as appropriate.

## 10. Integrations

- [ ] Outbound calls faked at the boundary (dependency override, `httpx.MockTransport`).
- [ ] Timeouts, 5xx, 4xx, malformed responses map to documented errors; no success is
      reported when the integration failed; no local state committed for a failed charge
      unless the design records it as pending.
- [ ] Retries are bounded and idempotent (reference/idempotency key passed through).
- [ ] Secrets are never echoed in responses or logs.

## 11. Pagination, filtering, sorting (when present)

- [ ] Default and maximum page size, last page, empty page, stable order with ties,
      filters combined with authorization (filtering never widens access).

## Recording the result

For each endpoint, the plan entry lists the rows covered by tests (with test ids), rows
proposed, and rows out of scope with reasons. That list is what "tested" means in the
summary; nothing else is implied.
