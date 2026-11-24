# Security test patterns

Executed proofs for the access matrix. Examples use pytest with a FastAPI/Starlette
`TestClient` and two fixtures that most API suites already have in some form:
`client` (the app built on a temporary database) and `make_user()` (registers and logs in
a user with a fixed test password, here `"pw-123456"`, returning `.email` and `.headers`).
Reuse the project's fixtures; write new ones only if none exist.
The code runs as written against a typical FastAPI app with bearer-token auth.

Rules for every pattern:

- **Positive control first.** Prove the request works for the legitimate actor, or a
  "403 for everyone" bug passes your negative test.
- **One property per test**, named after it: `test_non_owner_cannot_read_invoice`.
- **Data you create.** The "victim" record belongs to a user created inside the test.
- **Oracle from the access matrix**, citing the requirement in the docstring or the plan.

## Client setup gotchas

```python
# Secure cookies are only sent back over https: give TestClient an https base_url.
# raise_server_exceptions=False turns an unhandled exception into an observable 500
# instead of an exception raised inside the test (needed for injection tests).
with TestClient(create_app(str(tmp_path / "t.db")), base_url="https://testserver",
                raise_server_exceptions=False) as c:
    ...
```

Django: `django.test.Client(enforce_csrf_checks=True)` (CSRF checks are off by default in
the test client). Flask: `app.test_client()`; set `SESSION_COOKIE_SECURE` from the real config.

## 1. BOLA / IDOR (API1:2023, A01:2021): two users

```python
def test_non_owner_cannot_read_invoice(client, make_user):
    alice, mallory = make_user(), make_user()
    created = client.post("/invoices", json={"amount": 1200, "note": "rent"}, headers=alice.headers)
    assert created.status_code == 201, created.text
    invoice_id = created.json()["id"]

    # positive control: the owner can read it
    assert client.get(f"/invoices/{invoice_id}", headers=alice.headers).status_code == 200

    foreign = client.get(f"/invoices/{invoice_id}", headers=mallory.headers)
    missing = client.get("/invoices/999999", headers=mallory.headers)
    assert foreign.status_code == 404, f"non-owner got {foreign.status_code}: {foreign.text[:200]}"
    # no existence oracle: a foreign id looks exactly like a missing one
    assert foreign.json() == missing.json()
```

Extend the same shape to every verb on the resource:

- **Write BOLA**: `PUT/PATCH/DELETE` by the non-owner returns the matrix status **and** the
  owner re-reads the record unchanged afterwards (the status code alone is not the oracle).
- **List filtering**: the non-owner's list/search/export endpoints never contain the
  owner's id. Check every collection endpoint, including ones with filters such as `?user_id=`.
- **Indirect references**: ids inside bodies (`{"account_id": 7}`), nested routes
  (`/users/{uid}/invoices/{iid}` with a mismatched pair) and batch endpoints.
- **Id guessing is not required**: sequential ids make BOLA trivially reachable, but the
  defect is the missing check, so the test uses the known id.

## 2. BFLA / role escalation (API5:2023)

```python
def test_regular_user_cannot_call_admin_function(client, make_user):
    user, victim = make_user(), make_user()
    r = client.delete("/admin/users/2", headers=user.headers)
    assert r.status_code in (401, 403, 404), r.status_code
```

Add the positive control with an admin fixture when one exists. Also try the same path
with other methods (`GET` allowed, `DELETE` not) and the non-admin twin route
(`/users/{id}` vs `/admin/users/{id}`): authorization is often enforced per router, not per method.

## 3. Mass assignment (API3:2023 property-level authorization)

```python
def test_profile_update_ignores_privileged_fields(client, make_user):
    user = make_user()
    r = client.patch("/me", json={"email": "new@example.com", "role": "admin"}, headers=user.headers)
    assert r.status_code in (200, 422), r.status_code
    # oracle: re-read state, do not trust the echo in the response
    assert client.get("/me", headers=user.headers).json()["role"] == "user"
```

Candidates to inject: `role`, `is_admin`, `owner_id`, `tenant_id`, `balance*`, `status`,
`verified`, `price`, `created_at`, ids. Take them from the persistence model, not guesses.
Excessive data exposure is the read-side twin: assert responses do not contain
`password*`, `*_hash`, `token`, `secret`, internal flags or other users' emails.

## 4. Authentication (API2:2023, A07:2021)

```python
@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": "Bearer "}, {"Authorization": "Bearer not-a-real-token"},
     {"Authorization": "Basic Zm9vOmJhcg=="}],
    ids=["missing", "empty", "invalid", "wrong-scheme"],
)
def test_protected_endpoint_requires_valid_token(client, headers):
    assert client.get("/me", headers=headers).status_code == 401
```

More properties worth a test each:

- **Expiry**: move the clock instead of waiting. If the auth module calls `time.time()`,
  `monkeypatch.setattr(auth_module.time, "time", lambda: start + ttl + 1)` (this patches the
  shared `time` module for the duration of the test only).
- **Enumeration**: login with an unknown email and with a wrong password for a known email
  give the same status and body.
- **Case and normalization**: `Alice@x` vs `alice@x` at register and login, if the requirements say emails are case-insensitive.
- **Token scope**: a token issued for user A never authorizes a request about user B's resources (the BOLA tests cover this).

## 5. Sessions and cookie flags (A07:2021)

```python
def test_session_cookie_flags(client, make_user):
    user = make_user()
    r = client.post("/session/login", json={"email": user.email, "password": "pw-123456"})
    cookies = [c for c in r.headers.get_list("set-cookie") if c.lower().startswith("sid=")]
    assert cookies, "no session cookie set"
    attrs = {p.strip().split("=", 1)[0].lower(): (p.split("=", 1)[1].strip().lower() if "=" in p else True)
             for p in cookies[0].split(";")[1:]}
    assert attrs.get("httponly") is True
    assert attrs.get("secure") is True
    assert attrs.get("samesite") in ("lax", "strict")
```

Also: the session id changes at login (fixation); logout invalidates it server-side (replay
the old cookie and expect 401); `SameSite=None` must come with `Secure`.

## 6. CSRF (cookie-authenticated state changes)

```python
def test_state_change_rejects_cross_site_origin(client, make_user):
    user = make_user()
    client.post("/session/login", json={"email": user.email, "password": "pw-123456"})
    same = client.post("/session/email", headers={"Origin": "https://testserver"})
    cross = client.post("/session/email", headers={"Origin": "https://evil.invalid"})
    assert same.status_code == 200, same.text  # control
    assert cross.status_code == 403, cross.status_code
```

Only applicable when the browser sends credentials automatically (cookies, basic auth).
Bearer tokens in an `Authorization` header are not CSRF-prone; do not report missing CSRF
tokens on them. Also check that `GET` handlers have no side effects and that CORS does not
combine `allow_credentials` with a reflected or `*` origin.

## 7. Injection with read-only payloads (A03:2021)

```python
PAYLOADS = ["'", "' OR '1'='1", "%' OR 1=1 --", '" OR ""="', "1;SELECT 1", "\\", "%00",
            "{{7*7}}", "${7*7}", "<script>x</script>"]


@pytest.mark.parametrize("payload", PAYLOADS)
def test_search_handles_hostile_input(client, make_user, payload):
    alice, mallory = make_user(), make_user()
    client.post("/invoices", json={"amount": 1, "note": "alice-secret"}, headers=alice.headers)
    r = client.get("/invoices", params={"q": payload}, headers=mallory.headers)
    assert r.status_code < 500, f"server error for {payload!r}"
    body = r.text.lower()
    assert "alice-secret" not in body, "query returned another user's data"
    for marker in ("sqlite", "syntax error", "traceback", "psycopg", "ora-"):
        assert marker not in body, f"error detail leaked for {payload!r}"
```

The oracles are behaviour, not payload echo: no 5xx, no other user's marker row, no
database or stack detail, no template evaluation (`49` appearing for `{{7*7}}`). Payload
rules: detection only (tautologies, quote breaking, template arithmetic), never
`DROP`/`DELETE`/`UPDATE`, stacked writes, OS commands, sleeps over 1 s or out-of-band
callbacks. A `'` that yields a 500 is enough to report injection-prone query building;
you do not need to extract data to prove it.

For shell, path and SSRF sinks, assert the guard instead of exploiting it: `../` in a file
parameter is rejected; a URL parameter pointing at `http://127.0.0.1:1/` or
`http://169.254.169.254/` is refused **before** any request is made (patch the HTTP client
with a recording fake so the test never sends anything).

## 8. Tenant isolation

Same as BOLA with users from two tenants (`make_user(tenant="t1")`, `make_user(tenant="t2")`).
Cover the paths that bypass per-request filters: list and search endpoints, exports,
background jobs and reports, caches keyed without the tenant, and admin roles scoped to one tenant.

## 9. AI tool permissions (LLM06:2025 excessive agency)

Prompt-level rules are not access control. Call the tool layer directly with an identity
that must not use it and expect a refusal from the tool, not from the model:

```python
def test_refund_tool_enforces_caller_permission(make_tool_context):
    ctx = make_tool_context(role="customer", user_id=1)
    with pytest.raises(PermissionError):
        tools.issue_refund(ctx, order_id="order-of-user-2", amount_cents=100)
```

Adapt the names to the project's tool interface. Injection payloads that try to *reach*
such tools through retrieved content belong in the `qa-ai-systems` dataset with
`forbidden_tools`.

## Running and recording

```
qast exec pytest --group security -- tests/qa/test_security_authz.py
qast reproduce --test tests/qa/test_security_authz.py::test_non_owner_cannot_read_invoice --times 3
```

New test files only under `permissions.test_dir` with `write_tests = true`. Each FAILED
test becomes one finding (`qast schema DefectFinding --template` shows the shape); a whole
parametrized payload family failing for the same reason is one finding with the payloads
listed in `inputs`.
