# Discovery checklists by stack

Pick the sections that match the `framework` and `runtime` facts from `qast discover`.
Each row says where to look, what to extract and why QA cares. Grep patterns are
ripgrep starting points, not proof: a hit is `inferred` until you read the code path.

## Python · FastAPI / Starlette

| Look at | Extract | QA consequence |
|---|---|---|
| App factory (`FastAPI(`, `create_app`), `lifespan`, `@app.on_event("startup")` | how the app is built and configured, what runs at startup, settings source (`BaseSettings`, `os.environ`) | can tests build an isolated app? which env vars change behaviour? |
| `include_router(`, `APIRouter(prefix=` and route decorators | full route table: method, path, handler module | the API surface; compare with README and requirement docs |
| `Depends(`, `Security(`, `OAuth2PasswordBearer`, `HTTPBearer`, custom `current_user` | which dependency authenticates; routes without it | public vs protected routes; one authz case per route and method |
| Handler and service bodies after authentication | where ownership is enforced (`WHERE owner_id = ?`, `if obj.user_id != user.id`) | an id-based lookup without an owner filter is a cross-user access risk signal |
| Pydantic models: `Field(gt=, ge=, lt=, le=, min_length=, max_length=, pattern=)`, validators | declared input constraints | boundary values; a constraint that differs from the requirement is a finding candidate |
| `response_model=`, `status_code=`, `HTTPException(status_code=`, `@app.exception_handler` | response contract and error→status mapping | oracles for negative tests; error messages that leak existence or internals |
| DB layer: `sqlite3`, `Session`, `engine`, `BEGIN`, `commit`, `rollback`, `with conn:` | transaction boundaries, isolation level, locking | read-modify-write races; partial writes on error |
| `CORSMiddleware`, custom middleware | allowed origins, credentials, ordering | input for `qa-security` |
| `tests/conftest.py`, `TestClient(`, `app.dependency_overrides`, `monkeypatch` | fixtures, DB isolation per test, overridden dependencies | an overridden auth dependency means auth is not tested by those tests |

```
rg -n "@(router|app)\.(get|post|put|patch|delete)\(" ; rg -n "Depends\(|Security\("
rg -n "dependency_overrides|monkeypatch|mock\.patch" tests ; rg -n "skip|xfail" tests
```

## Python · Django / Django REST Framework

| Look at | Extract | QA consequence |
|---|---|---|
| `settings.py` | `INSTALLED_APPS`, `MIDDLEWARE` order, `AUTH_USER_MODEL`, `DATABASES` engine, `REST_FRAMEWORK` default authentication/permission classes, `DEBUG`, `ALLOWED_HOSTS` | default permission `AllowAny` makes every view public unless it overrides |
| `urls.py` include tree, routers | route table | API surface |
| Views/viewsets: `permission_classes`, `get_queryset`, `get_object`, `@action` | per-view authorization; tenancy filtering by `request.user` | `Model.objects.all()` in `get_queryset` for user-owned data is an IDOR signal |
| Serializers: `validate_<field>`, `read_only_fields`, `extra_kwargs`, `fields = "__all__"` | input constraints, mass-assignment exposure | writable fields that should be read-only |
| `models.py`: `unique=True`, `UniqueConstraint`, `CheckConstraint`, `on_delete`, `choices` | which invariants the database enforces | app-only uniqueness checks race under concurrency |
| `migrations/` | the schema actually applied | authoritative when it disagrees with `models.py` |
| `transaction.atomic`, `select_for_update`, `F(` expressions | concurrency control | missing lock on balance or stock updates |
| `signals.py`, `post_save`, `pre_delete` | hidden side effects | one write triggers others; tests must observe both |
| Celery `@shared_task`, management commands | async and batch paths | not reached by request tests |
| Tests: `TestCase` vs `pytest-django`, `fixtures/*.json`, factories, `force_authenticate` | data setup and auth shortcuts | `force_authenticate` bypasses the authentication stack |

## Node · React / Next.js / Express

| Look at | Extract | QA consequence |
|---|---|---|
| `package.json` scripts, lockfile, `devDependencies` | `test`, `e2e`, `lint`, `build` commands; runner (vitest, jest, Playwright) | the `qast exec vitest\|jest\|playwright` command to use later |
| Next.js `app/` or `pages/`, `route.ts`, `pages/api/`, server actions, `middleware.ts` `matcher` | routes and server entry points | auth in middleware covers only matched paths |
| Express/Fastify `app.use(`, router mount order | whether auth middleware is mounted before each router | routes registered before the auth middleware are public |
| Client guards (`<ProtectedRoute>`, `useSession`, redirects) | UI gating | client-only guards are not authorization; the API must check too |
| Form rules (`zod`, `yup`, `react-hook-form`, HTML `required`/`pattern`/`maxlength`) | client validation | the server must re-validate; boundary values for both |
| API client (`fetch(`, `axios.create({ baseURL`) and its error handling | backend dependencies of each screen | contract seam; failure and retry paths |
| `localStorage`, `sessionStorage`, IndexedDB | what survives reload and what is restored | resume, stale-state and tampered-state tests |
| i18n (`i18next`, locale files, `dir="rtl"`) | supported locales, RTL | locale × journey matrix |
| `playwright.config.*` | `baseURL`, `webServer`, projects/browsers, `retries` | retries hide flakiness: note the count |
| `msw` handlers, `jest.mock(`, `vi.mock(` | what is mocked | mocked boundaries are untested by those tests |
| `.env.example`, `process.env.` | configuration surface | never read `.env` |

## Any other stack

| Look at | Extract | QA consequence |
|---|---|---|
| `Dockerfile` `CMD`/`ENTRYPOINT`, `Procfile`, `main` functions, `cmd/` | what actually runs in production | the real entry points to trace |
| OpenAPI/Swagger, `.proto`, GraphQL schema, JSON Schema | the declared contract | compare with handlers; mismatches are contract risks |
| `*.sql`, migration directories, ORM models | constraints and indexes | which invariants the store enforces |
| `docker-compose`, Kubernetes, Terraform | runtime dependencies | what tests must stub or start locally; never apply |
| `.github/workflows`, `.gitlab-ci.yml`, `Jenkinsfile` | jobs that gate merges | `continue-on-error`, `allow_failure`, `\|\| true`, path filters and skipped jobs weaken the signal |
| `CODEOWNERS`, `CHANGELOG`, ADRs, `git log --oneline -n 30 -- <path>` | hot spots and recent fixes | failure history for `qa-strategy` |
| Test inventory: `skip`, `xfail`, `.skip(`, `.only(`, `@Disabled`, `t.Skip` | disabled or focused tests | skipped behaviour is untested; `.only` silently drops the rest of a suite |

## AI / LLM components (any stack)

| Look at | Extract | QA consequence |
|---|---|---|
| Model client calls, prompt templates, system prompts | where model output enters the system and what it can trigger | output handling and injection surface |
| Retrieval: corpus location, chunking, retriever, top-k | which documents can reach the prompt, including user-contributed ones | indirect prompt injection via retrieved text |
| Tool/function definitions and their guards | which tools have side effects (refunds, emails, deletes) and what precondition guards them | tool-call safety and ordering tests |
| Eval datasets (`*.jsonl`, golden files) | case schema, tags, which requirements they cover | validate with `qast ai-eval validate <dataset>` before relying on them |
