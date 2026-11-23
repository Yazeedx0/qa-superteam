# Orchestration model

## Roles

- **Main thread = QA Lead.** Workflow skills (`full-audit`, `review-pr`, ...) run in the
  main conversation, which acts as the QA Lead. Users who want a dedicated session can
  run `claude --agent qa-superteam:qa-lead`.
- **Specialists** are subagents with isolated context and a bounded task. They do
  *not* have the Agent tool, so they cannot delegate further (no recursive delegation).
- **`qast`** is the shared, deterministic state. Specialists communicate results by
  recording executions and findings in the run store, plus a short structured handoff.
  The lead reads `qast run status --json`, never only the specialist's prose.

## Phases

| Phase | Name | Produces | Typical owner |
|---|---|---|---|
| A | discovery | `profile.json` (`qast discover`), `qast doctor` capabilities | lead |
| B | requirements | `requirements.json` (requirements, invariants, ambiguities) | lead or `product-quality-analyst` |
| C | impact | `impact.json` (`qast impact`) — diff-based modes only | lead |
| D | risk | `risks.json` (`qast risk`, refined) | lead or `test-architect` |
| E | planning | `plan.json` (`qast record plan`) | `test-architect` for large scopes |
| F | delegation | `plan.specialists` + reasons | lead |
| G | execution | executions (`qast exec`) | specialists / lead |
| H | investigation | findings (`qast finding add`), reproductions (`qast reproduce`) | specialists, `bug-investigation-engineer` |
| I | verification | verifications (`qast verify`) for every high/critical finding | `independent-verification-engineer` |
| J | release | `decision.json` (`qast gate`) | lead / `release-qa-manager` |
| K | reporting | `report.md`, `report.json` (`qast report`) | lead |
| L | regression | durable regression tests for confirmed defects (if `write_tests`), else proposals | specialist that found it |

Checkpoint each phase: `qast run phase <name> started|done|skipped|blocked --note "..."`.
A skipped phase must carry a reason; it appears in the report's limitations.

## Choosing specialists (Phase F)

Select the smallest set that covers the top risks:

| Signal in profile/impact/risks | Specialist |
|---|---|
| API routes, services, DB, auth logic changed or high-risk | `backend-qa-engineer` |
| UI, forms, journeys, RTL, responsive | `frontend-qa-engineer` |
| LLM calls, RAG, tools/agents, prompts, eval datasets | `ai-quality-engineer` |
| AuthN/Z, sessions, secrets, tenant isolation, input handling | `security-qa-engineer` |
| Latency/throughput SLOs, retries, timeouts, queues | `performance-reliability-engineer` |
| Unclear behaviour, high-risk area with weak tests | `exploratory-qa-engineer` |
| A failure whose cause is unclear | `bug-investigation-engineer` |
| Any high/critical finding | `independent-verification-engineer` (always a different agent from the reporter) |

Do not spawn a specialist for something one `qast` command answers. For a small scope
(one feature, a handful of files) the lead does the work itself.

## Parallelism

Run specialists in parallel only when (a) the host supports concurrent subagents,
(b) their areas do not overlap, and (c) they do not mutate shared state other than
the run store (records are write-once with unique ids, so the store is safe). Never
run two specialists that start/stop the same local server port or write the same test
file. Otherwise run sequentially.

## Budgets and loop prevention

- Each delegation states a goal, scope, budget (turns/minutes) and stop condition.
- A specialist is re-dispatched at most once for the same task; if it fails twice,
  record the gap as a limitation (`qast run note`) and move on.
- Reproduction is capped by `budgets.max_reproduce_attempts`.
- No debates between agents. Disagreement is resolved by evidence: the verifier's
  executions decide.
