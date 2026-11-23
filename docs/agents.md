# QA Superteam agents

QA Superteam ships twelve subagents in `agents/<name>.md`, addressed as
`qa-superteam:<name>`. One lead coordinates; eleven specialists do bounded work and
report through `qast`, the shared and deterministic run store. Skills hold the
methodology; agents give it an isolated context, a tool allowlist and a handoff contract.

## Roster

"May write" means files the agent creates with Write/Edit. Every agent records executions,
findings, verifications and analysis only through `qast` (via Bash). Drafts are JSON files
in `.qa-superteam/runs/<RUN>/drafts/` that the agent submits with `qast record` or
`qast finding add`.

| Agent | Responsibility | Tools | May write? | May delegate? | maxTurns |
|---|---|---|---|---|---|
| `qa-lead` | Runs the engagement: phases A–L, specialist selection, handoff reconciliation, verification routing, gate, report | Agent, Skill, Read, Grep, Glob, Bash, Write | Drafts; new regression tests under `test_dir` if `write_tests` (Phase L) | **Yes**, the only one | 100 |
| `product-quality-analyst` | Requirements, acceptance criteria, invariants with oracles, ambiguities (`qa-requirements`) | Read, Grep, Glob, Bash, Write, Skill | Requirements draft only | No | 40 |
| `test-architect` | Risk refinement and test plan (`qa-strategy`, `qa-test-design`); executes nothing | Read, Grep, Glob, Bash, Write, Skill | Risk and plan drafts only | No | 50 |
| `backend-qa-engineer` | APIs, services, contracts, persistence, invariants (`qa-backend`, `qa-contracts`, `qa-data-integrity`) | Read, Grep, Glob, Bash, Write, Edit, Skill | New tests under `test_dir` if `write_tests`; drafts | No | 80 |
| `frontend-qa-engineer` | Browser journeys, forms, responsive, RTL, accessibility (`qa-frontend`, `qa-accessibility`) | Read, Grep, Glob, Bash, Write, Edit, Skill | New tests under `test_dir` if `write_tests`; drafts | No | 80 |
| `ai-quality-engineer` | LLM/RAG/agent evals: correctness, groundedness, tools, injection, nondeterminism (`qa-ai-systems`) | Read, Grep, Glob, Bash, Write, Edit, Skill | New datasets/tests under `test_dir` if `write_tests`; drafts | No | 70 |
| `security-qa-engineer` | AuthN/Z, isolation, injection, secrets, dependencies (`qa-security`); active probing only if authorized | Read, Grep, Glob, Bash, Write, Edit, Skill | New tests under `test_dir` if `write_tests`; drafts | No | 70 |
| `performance-reliability-engineer` | Latency/throughput vs SLOs, timeouts, retries, failure handling (`qa-performance`, `qa-reliability`) | Read, Grep, Glob, Bash, Write, Edit, Skill | New tests and k6 scripts under `test_dir` if `write_tests`; drafts | No | 60 |
| `exploratory-qa-engineer` | Charter-based, time-boxed exploration (`qa-exploratory`) | Read, Grep, Glob, Bash, Write, Edit, Skill | New checks under `test_dir` if `write_tests`; drafts | No | 60 |
| `bug-investigation-engineer` | Reproduction, minimization, classification, hypotheses vs facts (`qa-bug-investigation`) | Read, Grep, Glob, Bash, Write, Edit, Skill | Minimized repro tests under `test_dir` if `write_tests`; drafts | No | 60 |
| `independent-verification-engineer` | Re-executes or builds an alternate oracle and records `qast verify` (`qa-verification`) | Read, Grep, Glob, Bash, Write, Skill | Alternate-oracle tests under `test_dir` if `write_tests`; drafts; **no Edit** | No | 50 |
| `release-qa-manager` | Runs `qast gate` and `qast report`, explains triggered rules, lists human decisions (`qa-release-gate`, `qa-reporting`) | Read, Grep, Glob, Bash, Skill | **Nothing** (only `qast` writes) | No | 30 |

No agent sets `model`, so each inherits the session's model. Agents do not use the `skills`
frontmatter field: each body tells the agent which skill to load with the Skill tool, so
methodology is loaded only when the task needs it. Plugin agents cannot carry `hooks`,
`mcpServers` or `permissionMode`; the plugin-level guard hook (`hooks/hooks.json`) applies to
every agent's tool calls during an active run anyway.

Each agent file has the same sections: Scope of responsibility, Inputs, Required evidence,
Tools & skills to load, Procedure, Output contract, Delegation boundaries, Escalation
conditions, Must not.

## Delegation model

- **Who leads.** When a user starts a workflow (`/qa-superteam:full-audit`, ...), the main
  conversation is the QA Lead. Alternatively the whole session is `qa-lead`
  (`claude --agent qa-superteam:qa-lead`), or the main thread delegates a large scope to
  `qa-lead` as a subagent. The deepest possible chain is main thread → `qa-lead` → specialist.
- **Lead → specialist.** The delegation prompt carries the eight fields of
  `skills/using-qa-superteam/references/handoff-contract.md`: RUN, GOAL, SCOPE, OUT OF SCOPE,
  PERMISSIONS, GROUPS, BUDGET, REPORTER NAME. It includes the facts the specialist needs
  rather than whole files, and never includes secrets. Permissions in a prompt can narrow
  `.qa-superteam/config.toml`, never widen it.
- **Specialist → lead.** Every specialist ends with the HANDOFF block. The lead checks it
  against `qast run status --json` and `qast finding list --json`. Ids that are not in the
  store count as not done, and prose without an execution id counts as not verified.
- **Shared state is the store, not the conversation.** Executions, findings and verifications
  are write-once with unique ids. Singletons (requirements, risks, plan) are replaced only with
  `--supersede`, which keeps the old version in `history/`. No agent supersedes another
  agent's record.
- **Independence.** A finding's reporter is its `reported_by` (the REPORTER NAME).
  `qast verify` refuses CONFIRMED when verifier equals reporter, when no execution of the
  verifier's own shows the failure, or when the reproduction is intermittent. The lead never
  sends the verifier a finding the verifier reported, and never confirms its own findings.
- **Ownership.** Only the lead checkpoints phases (`qast run phase`), records limitations
  (`qast run note`) and finishes the run. Only the release decision from `qast gate` counts.
- **Bounded effort.** Each task is re-dispatched at most once. After a second failure the lead
  records a limitation and moves on. Agents do not debate: the verifier's executions decide.

## Why specialists cannot spawn agents

Only `qa-lead` lists `Agent` in `tools`. Every specialist omits it, so it cannot delegate.

1. **Bounded cost and depth.** The tree has at most two levels below the main thread, so the
   turn budget in each delegation actually bounds the work.
2. **Accountability.** Each execution and finding has one author. Verification independence is
   checked by name, and that check only means something if a reporter cannot hand its work to
   an unnamed helper.
3. **No loops or debates.** A specialist cannot re-dispatch itself, retry through a proxy, or
   get a second agent to argue with the verifier.
4. **Prompt-injection containment.** Specialists read untrusted repository content. Without
   `Agent`, injected instructions cannot fan out into fresh agents with new context and tools.
5. **Global view stays with the lead.** Budgets, port and file conflicts, and specialist
   selection need the whole run in view.

When a specialist needs work outside its boundary, it returns `partial` or `blocked` and names
the next step in `notes`. The lead decides who does it.

## Parallelism

Run specialists concurrently only when all of these hold (from `orchestration.md`):

1. The host supports concurrent subagents. The lead sends the parallel dispatches in one message.
2. Their areas do not overlap: different paths, endpoints, journeys and test cases.
3. They share no mutable state except the run store. The store is safe because records are
   write-once and execution ids include the process id.
4. No two specialists start or stop the same local server port or write the same test file.
   Give each one its own port and its own file names under `test_dir`.

Some steps are always sequential: requirements → planning → execution → verification → release.
The verifier starts after the reporters' handoffs. Bug investigation of a failure starts after
the execution that produced it. A typical safe parallel set is `backend-qa-engineer`,
`frontend-qa-engineer` and `security-qa-engineer` on disjoint areas, each with its own server port.

Colors: the host offers eight agent colors. The eight specialists that can run concurrently
during execution and verification have distinct colors. The other four agents reuse a color,
each sharing with an agent that never runs at the same time as it: `product-quality-analyst`,
`test-architect` and `release-qa-manager` run in other phases, and `qa-lead` is the parent.

## Running a dedicated QA Lead session

```bash
qast init                                  # once: writes .qa-superteam/config.toml (read-only defaults)
claude --agent qa-superteam:qa-lead        # the whole session runs as the QA Lead
```

Before starting, set the permissions you intend to grant in `.qa-superteam/config.toml`:
`write_tests`, `test_dir`, `authorized_targets`, and only if wanted `allow_load_testing`,
`allow_active_security` or `allow_fault_injection`. Then ask for the engagement in plain words
("full QA audit, focus on payments") or start a workflow command such as
`/qa-superteam:full-audit` or `/qa-superteam:review-pr main`.

The lead loads `using-qa-superteam`, starts or resumes a run, follows the workflow's phases,
delegates to the smallest set of specialists, and finishes with `qast gate`, `qast report` and
a summary that links `report.md`.

- **Resuming:** start a new lead session and ask it to continue. It reads `qast run status`
  and resumes from the first phase that is not `done`, without redoing recorded executions.
- **Budget:** the lead has `maxTurns: 100`. If the budget runs out, it runs the gate and report
  on what exists and lists what was not completed.
- **Without a dedicated session:** ask Claude to "use the qa-lead agent" for a large QA scope;
  the main thread then delegates to `qa-superteam:qa-lead` as a subagent.
