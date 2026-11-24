# Reading code without executing it

Discovery and requirements work is read-only. This is how to get execution-grade
understanding from text, and how to grade what you learned.

## Why not execute during discovery

- Importing a module runs its top-level code: connections, migrations, network calls.
  `python -c "import app"` is execution.
- Installing dependencies runs lifecycle scripts (`postinstall`, build hooks).
- Starting the app can create files, seed data or contact third parties.

Execution belongs to later phases, through `qast exec`, where it is recorded as
evidence with environment metadata.

## Trace a workflow from boundary to store

1. Find the entry: the route decorator or route table entry for the operation
   (`rg -n '"/orders"'`, `rg -n "def create_order"`).
2. Follow each call one hop at a time by grepping the symbol name. Write the chain with
   locations: `routes/orders.py:42 create → services/orders.py:88 place_order → db.py:15 insert_order`.
3. At each hop note: is input validated here? Is identity or ownership checked here?
   What state is read or written? Which errors are raised, and how are they mapped to a
   response?
4. Stop at the persistence call or the outbound client. Record where the transaction
   begins, commits and rolls back.
5. Mark what you could not resolve statically (dependency injection containers,
   `getattr` dispatch, plugin registries, event buses) as `inferred` with the reason.

## Find trust boundaries

- Where external input enters: HTTP parameters, bodies and headers, uploaded files,
  queue messages, webhooks, retrieved documents, LLM output.
- Where identity is established (token parsing, session lookup) versus where it is used
  (ownership and role checks). A check that exists only in the UI is not a boundary.
- Every query that loads user data by an id taken from the request: is the caller's
  identity part of the query, or checked after loading? If neither, write it down as a
  risk signal. It becomes a defect only when an executed test fails.

## Read data rules

- Constraints in the database (UNIQUE, CHECK, FOREIGN KEY, NOT NULL) hold on every
  path. Checks in application code hold only on the paths that call them: list both,
  and the paths that skip the application check.
- Read-modify-write sequences (`balance = read(); write(balance - x)`) without a lock,
  an atomic `UPDATE ... SET x = x - ?`, or a serializable transaction are concurrency
  risk signals.
- Money and quantity arithmetic: note the type (integer minor units, decimal, float),
  the rounding function and mode, and where rounding happens (per line or on the
  total).
- Normalization: where strings are lowercased, trimmed or unicode-normalized (emails,
  codes, usernames), and whether lookups apply the same normalization as writes.

## Read tests as evidence of intent and of gaps

- The assertion is the oracle. A test that asserts nothing about the outcome covers
  nothing, however much code it executes.
- Fixtures show the data shapes the team considers valid.
- Overrides and mocks (`dependency_overrides`, `force_authenticate`, `mock.patch`,
  `jest.mock`, `vi.mock`, `msw`) mark exactly what the suite does not test.
- Skip and xfail markers, and their reasons, often point at known defects.
- When a test's name and its assertion disagree, trust the assertion and note the gap.

## Read configuration and CI

- Defaults that change behaviour (feature flags, `DEBUG`, timeouts, retry counts, page
  sizes): note the default and every place it is overridden.
- CI: which commands gate merges. Anything with `continue-on-error`, `allow_failure`,
  `|| true` or test retries is weaker than it looks.

## Evidence ladder

| What you have | Basis | Confidence |
|---|---|---|
| An enforced artifact read directly: DB constraint, route decorator, CI job, declared dependency | observed | high |
| A code path read end to end at cited lines | observed | high; medium if it passes through dynamic dispatch |
| A pattern match you have not followed (grep hit, import present) | inferred | medium |
| A file or directory name only | inferred | low |
| Documentation or a comment describing behaviour | observed that the document says it | the behaviour itself stays inferred until code or a test confirms it |
| Nothing | assumed | low; record it as an assumption with the impact if wrong |

Two independent sources that agree raise confidence one step. A source that contradicts
another lowers it and becomes a question.

## Read-only commands that are safe here

`rg`, `git log --oneline -n 30 -- <path>`, `git show --stat <sha>`,
`git log --since=<date> --name-only --format= | sort | uniq -c | sort -rn | head -20`
(change hot spots), `qast discover`, `qast doctor`, `qast ai-eval validate <dataset>`.
