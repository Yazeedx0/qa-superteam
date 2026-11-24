# Other stacks: in-process API testing and how qast records it

The method (checklist, two-actor authorization tests, idempotency, concurrency, failure
injection) is stack-agnostic. Only the harness changes. Always use the test framework the
project already has.

## Node.js: supertest with jest or vitest

```ts
import request from 'supertest';
import { describe, expect, it } from 'vitest';
import { buildApp } from '../src/app';

async function actor(app: Parameters<typeof request>[0], email: string) {
  await request(app).post('/auth/register').send({ email, password: 'correct-horse-battery' }).expect(201);
  const res = await request(app).post('/auth/login').send({ email, password: 'correct-horse-battery' }).expect(200);
  return { Authorization: `Bearer ${res.body.token}` };
}

describe('documents authorization', () => {
  it('hides a foreign document exactly like a missing one', async () => {
    const app = buildApp({ databaseUrl: 'sqlite::memory:' });
    const alice = await actor(app, 'alice@example.com');
    const mallory = await actor(app, 'mallory@example.com');
    const doc = await request(app).post('/documents').set(alice).send({ title: 'x' }).expect(201);

    const foreign = await request(app).get(`/documents/${doc.body.id}`).set(mallory);
    const missing = await request(app).get(`/documents/${doc.body.id + 100000}`).set(mallory);
    expect(foreign.status).toBe(404);
    expect([foreign.status, foreign.body]).toEqual([missing.status, missing.body]);
  });
});
```

- `request(app)` binds an ephemeral port per call; parallel requests: `await
  Promise.all(Array.from({ length: 8 }, () => request(app).post(...)))` (concurrent I/O on
  one event loop; truly parallel DB access depends on the pool).
- Record: `qast exec vitest --group <g> -- test/api/documents.qa.test.ts` or
  `qast exec jest --group <g> -- test/api/documents.qa.test.ts`.

## Go: net/http/httptest

```go
// register, createDocument and get are small helpers in the same _test.go file;
// get returns a struct{ StatusCode int; Body string }.
func TestForeignDocumentIsHidden(t *testing.T) {
	srv := httptest.NewServer(api.NewRouter(api.Config{DB: testdb.New(t)}))
	t.Cleanup(srv.Close)

	alice := register(t, srv.URL, "alice@example.com")
	mallory := register(t, srv.URL, "mallory@example.com")
	id := createDocument(t, srv.URL, alice, "salary review")

	foreign := get(t, srv.URL+"/documents/"+id, mallory)
	missing := get(t, srv.URL+"/documents/999999", mallory)
	if foreign.StatusCode != http.StatusNotFound || foreign.Body != missing.Body {
		t.Fatalf("foreign = %d %q, missing = %d %q", foreign.StatusCode, foreign.Body, missing.StatusCode, missing.Body)
	}
}
```

- `httptest.NewRecorder()` for handler-level tests; `httptest.NewServer` when middleware,
  routing and real connections matter.
- Concurrency: `sync.WaitGroup` + goroutines released by a closed channel, run with
  `-race`.
- Record with per-test results: `qast exec junit --report .qa-superteam/tmp/go-junit.xml --
  gotestsum --junitfile .qa-superteam/tmp/go-junit.xml -- -race -run 'TestForeign' ./internal/api/...`
  (exit-code only fallback: `qast exec command --label "go api tests" -- go test -race -run TestForeign ./internal/api/...`).

## Java / Spring: MockMvc

```java
// static imports: MockMvcRequestBuilders.get, MockMvcResultMatchers.status, Assertions.assertEquals
// tokenFor/createDocument: helpers that go through the real register/login/create endpoints
@SpringBootTest
@AutoConfigureMockMvc
class DocumentAuthorizationQaTest {
    @Autowired MockMvc mvc;

    @Test
    void foreignDocumentIsIndistinguishableFromMissing() throws Exception {
        String alice = tokenFor("alice@example.com");
        String mallory = tokenFor("mallory@example.com");
        long id = createDocument(alice, "salary review");

        String foreign = mvc.perform(get("/documents/{id}", id).header("Authorization", "Bearer " + mallory))
            .andExpect(status().isNotFound()).andReturn().getResponse().getContentAsString();
        String missing = mvc.perform(get("/documents/{id}", 999_999L).header("Authorization", "Bearer " + mallory))
            .andExpect(status().isNotFound()).andReturn().getResponse().getContentAsString();
        assertEquals(missing, foreign);
    }
}
```

- Use the project's test profile and its disposable database (H2, Testcontainers);
  never point a test profile at a shared database.
- Record one test class per execution (Surefire writes one XML per class):
  `qast exec junit --report target/surefire-reports/TEST-com.example.DocumentAuthorizationQaTest.xml -- mvn -q test -Dtest=DocumentAuthorizationQaTest`
  (Gradle: `build/test-results/test/TEST-<class>.xml` with `./gradlew test --tests <class>`).

## Testcontainers (any stack)

Use when the production engine's behaviour matters (isolation levels, constraints,
JSON operators) and `qast doctor` shows `docker` (and the language's Testcontainers
library). The container is disposable by construction. Patterns and the Python fixture
live in `qa-data-integrity`'s references. Without Docker the case is BLOCKED for that
engine: say so and keep the SQLite/in-memory results labelled with their engine.
