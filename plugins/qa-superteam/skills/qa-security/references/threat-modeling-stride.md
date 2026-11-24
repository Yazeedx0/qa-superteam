# Threat modeling quick sheet (STRIDE)

Fifteen minutes of modeling decides where the security tests go. Output: a short list
of threats ranked by probability × impact, each with a test type and an oracle, added to
the risk register and plan (`qa-strategy`, `qa-test-design`).

## 1. Draw the system in text

```
Actors:        anonymous, customer, support agent, admin, other tenant, background job, LLM
Entry points:  routes (method + path), webhooks, file uploads, queue consumers, CLI, LLM tools
Assets:        credentials and sessions, personal data, money/balances, permissions, tenant data, secrets
Data stores:   databases, caches, object storage, vector stores, logs
Boundaries:    internet → API, API → DB, service → third party, user text → prompt, model → tools
```

Take entry points from the profile (`qast discover`), the router files and the API docs;
take assets from the requirements. Every arrow that crosses a boundary gets the STRIDE pass below.

## 2. STRIDE per boundary crossing

| Threat | Question at this boundary | Typical defects | Test type | OWASP |
|---|---|---|---|---|
| **S**poofing | Can a caller claim another identity? | Missing or weak auth on a route, tokens that never expire, unverified webhook signatures, user enumeration | Auth negatives, expiry with a patched clock, signature-required tests | A07:2021, API2:2023 |
| **T**ampering | Can a caller change data or parameters they should not? | Mass assignment, client-side price/role, unsigned ids in hidden fields, injection | Mass-assignment re-read, read-only injection payloads, write-BOLA with owner re-read | A03:2021, A08:2021, API3:2023 |
| **R**epudiation | Can an action happen without a trace? | No audit record for money movement or permission change, logs without the actor | Assert audit row/log entry with actor and target after the action | A09:2021 |
| **I**nformation disclosure | Can a caller read what they should not? | BOLA, list endpoints without filters, verbose errors, secrets in repo, excessive response fields, existence oracles | Two-user BOLA, list filtering, error-detail assertions, gitleaks | A01:2021, A02:2021, API1:2023, API3:2023 |
| **D**enial of service | Can one caller exhaust shared resources? | Unbounded page size, no upload limit, regex backtracking, expensive unauthenticated endpoints | Bounds tests (page size capped, upload limit enforced) in-process; volume tests only via `qa-performance` with permission | API4:2023 |
| **E**levation of privilege | Can a caller gain a role or reach a function above their own? | BFLA, role checks per router but not per method, tenant admin acting cross-tenant, tool reachable from untrusted text | BFLA per method, cross-tenant admin, tool-permission tests | A01:2021, API5:2023, LLM06 |

Also walk the API-specific risks that STRIDE tends to miss:

| Risk | What to check |
|---|---|
| API6:2023 unrestricted access to sensitive business flows | Can a flow be automated to abuse business logic (coupon redemption, sign-up bonus)? Test the limit, not volume. |
| API7:2023 SSRF | Every parameter that becomes an outbound URL: allowlist enforced before any request. |
| API8:2023 misconfiguration | Debug mode, permissive CORS with credentials, default credentials, stack traces. |
| API9:2023 inventory | Old versions (`/v1/` next to `/v2/`), undocumented routes, test endpoints left enabled. |
| API10:2023 unsafe consumption | Data from third-party APIs treated as trusted (no validation, followed redirects). |
| A04:2021 insecure design | Business rules that make abuse possible regardless of implementation (no limit on transfers to self). |
| A10:2021 SSRF | Same as API7. |

## 3. LLM features (OWASP Top 10 for LLM Applications, 2025)

| Risk | Boundary | Check |
|---|---|---|
| LLM01 prompt injection (direct and indirect) | user text, retrieved documents, tool output → prompt | Canary dataset cases via `qa-ai-systems`; instructions in retrieved text are never followed or repeated |
| LLM02 sensitive information disclosure | model → user | Secret and system-prompt probes; answers never contain credentials, other users' data or internal codes |
| LLM05 improper output handling | model output → HTML, SQL, shell, URLs | Model output is escaped/validated like user input; test with output containing markup |
| LLM06 excessive agency | model → tools | Tools enforce permissions server-side; destructive tools need confirmation; `forbidden_tools` cases |
| LLM07 system prompt leakage | prompt → user | Probe cases; no secret should live in the prompt in the first place |
| LLM08 vector and embedding weaknesses | vector store | Tenant filter applied in retrieval queries, not after generation |
| LLM10 unbounded consumption | user → model | Max input/output size enforced before calling the model |

## 4. Rank and cut

Score each threat: probability (exposed entry point? authenticated? known pattern in this
code?) × impact (asset value from the requirements). Keep the top threats that fit the
budget; every threat you drop goes into the summary as not covered, with the reason. A
threat with no test type you can run here (for example DoS volume without permission) is a
limitation, not a silent omission.

## 5. Turn threats into plan cases

Each case: `id`, threat (`STRIDE letter + boundary`), OWASP id, preconditions (actors, data),
steps, **oracle** from the access matrix, policy group `security`, priority from the ranking.
Example oracle: "As user B, `GET /invoices/{A's id}` returns 404 with the same body as a
non-existent id (REQ-INV-2); the owner's request returns 200."
