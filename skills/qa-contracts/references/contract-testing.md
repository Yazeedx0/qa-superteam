# Implementation-vs-contract tests and consumer impact

A spec diff tells you how the *document* changed. Contract tests tell you whether the
*running implementation* honours the document. Run both. Every execution here is tagged
`--group contract`.

## Option A: schemathesis (only if installed; v4 API shown)

Property-based requests generated from the OpenAPI document against the in-process app,
with a disposable database and faked integrations.

```python
# tests/qa/test_qa_contract_schemathesis.py
import tempfile
from pathlib import Path

import pytest
import schemathesis
from fastapi.testclient import TestClient
from hypothesis import HealthCheck, settings

from app.main import create_app, get_gateway


class FakeGateway:
    def charge(self, amount_cents, currency, reference):
        return "ch_fake"


# One disposable database for the module: schemathesis sends many writes.
APP = create_app(str(Path(tempfile.mkdtemp(prefix="qa-contract-")) / "contract.db"))
APP.dependency_overrides[get_gateway] = lambda: FakeGateway()  # never call real integrations
schema = schemathesis.openapi.from_asgi("/openapi.json", APP)


@pytest.fixture(scope="module")
def auth_headers():
    with TestClient(APP) as c:
        creds = {"email": "contract@example.com", "password": "correct-horse-battery"}
        c.post("/auth/register", json=creds)
        token = c.post("/auth/login", json=creds).json()["token"]
    return {"Authorization": f"Bearer {token}"}


@schema.parametrize()
@settings(max_examples=25, database=None, deadline=None,
          suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much])
def test_api_conforms_to_its_openapi_document(case, auth_headers):
    case.call_and_validate(headers=auth_headers)
```

```bash
HYPOTHESIS_STORAGE_DIRECTORY=.qa-superteam/hypothesis \
  qast exec pytest --group contract --label contract-schemathesis -- tests/qa/test_qa_contract_schemathesis.py
```

- schemathesis 3.x uses `schemathesis.from_asgi(...)`; check `pip show schemathesis`.
- Never point schemathesis at a shared or live environment unless it is an authorized
  target *and* the user accepted that it sends many generated, mutating requests.
- Each failure names a check. Classify before reporting:
  - server error (5xx) for schema-valid input: implementation defect;
  - response does not match the documented schema / undocumented status code: contract
    defect (spec or implementation wrong: say which matches the requirements);
  - "schema-valid request rejected": the spec is looser than the implementation (missing
    `format`, `pattern`, `minLength`): a documentation contract defect, usually medium/low
    unless consumers generate requests from the spec.
- Reproduce with the `curl` line schemathesis prints, as a plain pytest case, so the
  finding has a deterministic test id for `qast reproduce`.

## Option B: pytest + jsonschema against the document

When schemathesis is absent but `jsonschema` is installed. Validate real responses from
targeted scenarios (including error responses) against the documented schema.

```python
# tests/qa/test_qa_contract_responses.py
import jsonschema
import pytest


@pytest.fixture(scope="module")
def openapi(tmp_path_factory):
    from app.main import create_app  # or json.load(open("api/openapi.json"))
    return create_app(str(tmp_path_factory.mktemp("spec") / "spec.db")).openapi()


def assert_matches_contract(spec: dict, path: str, method: str, response) -> None:
    responses = spec["paths"][path][method]["responses"]
    code = str(response.status_code)
    assert code in responses, f"undocumented status {code} for {method.upper()} {path}: {response.text[:200]}"
    content = responses[code].get("content", {})
    if not content:
        return  # documented without a body
    media = content.get("application/json")
    assert media is not None, f"{code} documents {list(content)} but not application/json"
    schema = {"$schema": "https://json-schema.org/draft/2020-12/schema", **media["schema"],
              "components": spec.get("components", {})}
    jsonschema.validate(response.json(), schema, cls=jsonschema.Draft202012Validator)


def test_create_payment_response_matches_contract(client, alice, gateway, openapi):
    r = client.post("/payments", json={"amount_cents": 500}, headers=alice.headers)
    assert_matches_contract(openapi, "/payments", "post", r)


def test_validation_error_matches_contract(client, alice, openapi):
    r = client.post("/payments", json={"amount_cents": "five"}, headers=alice.headers)
    assert r.status_code == 422
    assert_matches_contract(openapi, "/payments", "post", r)
```

- Putting `components` at the schema root lets `#/components/schemas/...` references
  resolve. This is exact for OpenAPI 3.1 (JSON Schema 2020-12). For 3.0 documents,
  `nullable: true` and `example` keywords differ: convert or validate the affected fields
  by hand.
- Cover: every documented success code, the common error codes (401, 404, 409, 422),
  list endpoints (array item schema), and the undocumented-status check above (an
  endpoint returning 401 that documents only 200/422 is a contract gap).
- Without `jsonschema`, assert the documented required fields and their JSON types
  explicitly; do not install packages unasked.

## Consumer-driven contracts (Pact and similar)

If the repository has pact files (`pacts/*.json`) or a provider verification task, run
the project's own verification command through `qast exec junit` (if it writes JUnit
XML) or `qast exec command --group contract -- <verify command>`. A pact failure is a
consumer-visible break by definition. Never regenerate or edit pact files to pass.

## Consumer impact analysis

For every breaking or potentially breaking item:

1. **Find consumers in the repository:** front-end calls (`grep -rn "/payments" src/ web/`),
   generated clients (`openapi-generator` output, `*.gen.ts`), SDK packages, other services
   in a monorepo, contract/pact files, docs and examples, mobile apps.
2. **Read how each consumer uses the changed element:** does it read the removed field,
   send the newly required one, switch exhaustively on the enum, check the status code
   (`if (res.status === 201)`)? Quote file and line.
3. **Unknown consumers** (public API, partners): treat as present. Say "consumers outside
   this repository are unknown".
4. **Quantify where possible:** number of call sites, which journeys they belong to,
   whether the failure is loud (exception) or silent (wrong value displayed/charged).
5. **Write the impact into the finding:** affected consumers (`affected` source refs),
   failure mode, and what a non-breaking alternative would be (keep old field and add the
   new one, accept both, version the endpoint).

A consumer in the same repository that the change also updated is still evidence: older
deployed versions of that consumer (mobile apps, cached SPAs, other services deployed
independently) keep the old expectations until they are upgraded.
