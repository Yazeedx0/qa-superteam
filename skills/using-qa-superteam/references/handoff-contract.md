# Handoff contract

## Lead → specialist (the delegation prompt)

Every delegation prompt contains, in this order:

```
RUN: <run id>              (specialists pass --run <id> to every qast command)
GOAL: <one sentence: the question this task must answer>
SCOPE: <paths, endpoints, journeys, test cases TC-.. from plan.json>
OUT OF SCOPE: <what not to touch>
PERMISSIONS: write_tests=<true|false> test_dir=<dir> targets=<authorized URLs or none>
GROUPS: <policy groups to tag executions with, e.g. critical-journeys>
BUDGET: <max turns or minutes>; stop when <condition>
REPORTER NAME: qa-superteam:<agent>   (use as reported_by in findings)
```

Include the facts the specialist needs (from `profile.json`, `requirements.json`,
`plan.json`); do not paste whole files. Never paste secrets.

## Specialist → lead (final message)

End with exactly this block. Everything else in the message is optional context.

```
HANDOFF
status: completed | partial | blocked
executions: [ex-..., ...]                # every qast exec/reproduce id you created
findings: [F-..., ...]                   # every finding you recorded
verifications: [V-..., ...]              # verifier only
blocked: ["<what could not run> — <why> — <what would unblock it>"]
not_verified: ["<scope item you did not reach>"]
proposed_tests: ["<test you designed but could not add, with oracle>"]
notes: <≤ 5 lines: surprises, assumptions, suggested next step>
```

The lead checks the block against `qast run status --json`. Ids that do not exist in
the store are treated as not done. A specialist's "it works" without an execution id
counts as **not verified**.
