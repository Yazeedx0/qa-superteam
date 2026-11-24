# Risk scoring rubric

Used by `qa-strategy` to refine the `qast risk` baseline. This rubric is identical to
the "Refinement rubric" section of `risk-model.md`, which also
documents how the baseline is computed.

Score every risk item on seven factors, 1 (low) to 5 (high), using the anchors below.
Record each factor as a `RiskFactor` whose `name` is exactly the column name, with
`value`, a one-line `rationale` naming the evidence, and `basis`: `observed` when read
from code, the diff, git history, test results or a finding; `inferred` when derived
from a pattern; `assumed` when no evidence was available.

### Probability factors

| Value | change surface | complexity | failure history | coverage weakness |
|---|---|---|---|---|
| 1 | Unchanged in the scope under test, or comments/docs only | Declarative config or static content; no branching | No defect, fix commit or skipped test known for the area | Targeted tests with boundary and negative cases exist and PASSED in this run |
| 2 | < 20 changed lines in one unit; no interface change | Straight-line CRUD; a few independent branches | Isolated minor fixes in the past, none recent | Targeted tests including some negative cases exist but have not run in this run |
| 3 | 20–99 changed lines, or several units of one module | Validation with interacting conditions; money, date or rounding arithmetic; text normalization | Recurring fix/revert commits in the area, or `TODO`/`FIXME`/`xfail` near the logic | Happy-path tests only, or tests at a level that cannot observe the failure (e.g. a mocked store for a transaction rule) |
| 4 | 100–399 changed lines, or a change spanning modules | Multi-step workflows or state machines, multi-entity transactions, caching, retries, parsing untrusted input | Known open defect, recent revert or hotfix, or flaky tests in the area | Incidental coverage only: exercised by broader tests that do not assert this behaviour |
| 5 | ≥ 400 changed lines, a new component or rewrite, or a public interface, schema or migration change | Concurrency or shared mutable state, idempotency, authorization decisions, cryptography, nondeterministic components (LLM, ranking) | A FAILED execution or a finding for this area in this run, or a documented incident | No test touches the area (`changed_source_without_related_tests`, or no suite at all) |

Without a diff (full audit), **change surface** comes from recent churn
(`git log --since=<window> --name-only --format=`): the most-changed fifth of areas
score 4, areas with no commits in the window score 1, the rest 2. No git history
available: 3 with basis `assumed`. **Failure history** with no history available: 2
with basis `assumed`.

### Impact factors

| Value | business criticality | users affected | exposure |
|---|---|---|---|
| 1 | Internal tooling, docs, dev-only scripts | One user in a rare configuration, or operators only | None: cosmetic, recoverable by reload |
| 2 | Convenience feature with an easy workaround | A small segment: an edge configuration, one rare browser | Wrong data shown but not stored; recoverable by retry |
| 3 | Core but non-transactional feature (search, profile, notifications) | A significant segment: one platform, locale, country, or the users of one optional feature | Persistent wrong data that support can repair; minor compliance gap |
| 4 | Primary workflow step (signup, login, checkout, a core API used by clients) | Most users | Data loss or corruption needing a restore; an accessibility barrier that blocks a journey; limited personal-data exposure |
| 5 | Money movement, billing, authentication/authorization, a legally mandated function, or a configured `[project] critical_paths` entry | All users, or external consumers of a public API or contract | Money created, lost or misrouted; cross-user or cross-tenant data exposure; auth bypass; secret leakage; regulatory breach; irreversible loss |

### Aggregation

1. **probability** = mean of the four probability factors, rounded half up
   (2.5 → 3). Then: failure history 5 ⇒ probability 5; coverage weakness 5 and
   complexity ≥ 4 ⇒ probability at least 4.
2. **impact** = max(business criticality, exposure). Then +1 if users affected is 5
   and the value is ≥ 3; −1 if users affected ≤ 2 and exposure < 5. Clamp to 1..5.
3. **score** = probability × impact (`qast record risks` refuses anything else).
4. **level** by score: ≥ 20 `critical`, 12–19 `high`, 6–11 `medium`, ≤ 5 `low` — the
   same bands `qast risk` uses. `qast record risks` rejects a `level` that does not match the band.

A deviation from these rules is allowed only with a written reason in the risk's
`assumptions` (for example a regulatory requirement that makes an otherwise medium
item critical).

### Planning attributes (never part of the score)

| Value | execution cost |
|---|---|
| 1 | In-process unit or API test using existing fixtures; seconds |
| 2 | Needs a local server, a browser, new fixtures or data builders |
| 3 | Needs an external environment, credentials, a permission (load, active security, fault injection) or human judgment |

**Regression likelihood** is `high` when the area is in the top churn fifth, is shared
code with many callers, or had a defect confirmed in this or an earlier run; otherwise
`low`. High-likelihood items get durable tests in the `regression` group.

Cost and regression likelihood order the work and decide which low/medium items are
declared out of scope. They never raise or lower probability or impact, and cost never
justifies leaving a high or critical risk untested without a limitation note.

### Worked example

```json
{
  "id": "R-03",
  "area": "order export tenant isolation",
  "description": "The export endpoint may return orders that belong to other tenants",
  "probability": 4,
  "impact": 5,
  "score": 20,
  "level": "critical",
  "factors": [
    {"name": "change surface", "value": 2, "rationale": "14 lines changed in exports/query.py", "basis": "observed"},
    {"name": "complexity", "value": 5, "rationale": "authorization decision: tenant filter built from request parameters", "basis": "observed"},
    {"name": "failure history", "value": 2, "rationale": "no git history in this checkout", "basis": "assumed"},
    {"name": "coverage weakness", "value": 5, "rationale": "no test calls /exports as a second tenant", "basis": "observed"},
    {"name": "business criticality", "value": 5, "rationale": "authorization", "basis": "inferred"},
    {"name": "users affected", "value": 5, "rationale": "every tenant", "basis": "inferred"},
    {"name": "exposure", "value": 5, "rationale": "cross-tenant personal data", "basis": "inferred"}
  ],
  "paths": ["exports/query.py"],
  "existing_coverage": "tests/test_exports.py checks CSV columns only",
  "related_requirements": ["REQ-EXP-2"],
  "assumptions": ["Baseline R-03 was P2xI2=4 (low): the path carries no sensitive-name signal. Raised: complexity 5 (the tenant filter is an authorization decision), coverage weakness 5, exposure 5."]
}
```

Probability: mean(2, 5, 2, 5) = 3.5 → 4; coverage weakness 5 with complexity 5 keeps it
≥ 4. Impact: max(5, 5) = 5. Score 20 → `critical`.
