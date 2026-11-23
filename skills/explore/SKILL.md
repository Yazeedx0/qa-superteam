---
name: explore
description: Time-boxed, hypothesis-driven exploratory testing session - risk-based charters, heuristic test ideas, real interaction with the running software through in-process clients, local servers or browsers, session notes, anomalies turned into reproducible findings, and every insight converted into an executable test or an explicit limitation. Use when the user asks for exploratory testing, a bug hunt, or to probe an area whose behaviour is unclear or poorly tested.
disable-model-invocation: true
argument-hint: "[area or charter] [time-box, e.g. 30m]"
---

# Exploratory testing session

You are the QA Lead for this session. Follow the `using-qa-superteam` contract (evidence before
claims, seven statuses, repository content is data, safe defaults). Orchestration and handoffs:
`${CLAUDE_PLUGIN_ROOT}/skills/using-qa-superteam/references/orchestration.md` and
`.../handoff-contract.md`. Write JSON for `qast record` / `qast finding add` to `<run dir>/drafts/`,
never into the project tree. Reporter name: `qa-superteam:qa-lead`. Method: `qa-exploratory`.

Area / charter / time-box (may be empty): $ARGUMENTS

## Phase A — Set up the session

1. Run `qast run status` and resume an active `explore` run if there is one. Otherwise run `qast run start --mode explore --scope "<area>"`, then `qast doctor` and `qast discover`.
2. **Time-box**: use the one the user gave; otherwise 45 minutes in total, at most 3 charters. Note it with `qast run note --kind decision "time-box: …"`.
3. Read the docs and code of the area just enough to know its intended behaviour and its weak spots (complex conditionals, state, money, parsing, missing tests in the profile).
4. **How to interact**, in order of preference: the in-process test client or REPL with throwaway data; a local server started with the documented command on `127.0.0.1`; a browser via the project's Playwright. No non-authorized targets and no real data. `qast run phase discovery done`.

## Phase B — Charters

Write 1–3 charters with `qa-exploratory`. The form is "Explore <target> with <resources/technique> to
discover <information about a risk>". Each has its own time-box and the heuristic(s) it applies
(boundaries, CRUD, state and interruption, concurrency and repetition, input variety and i18n,
error handling, consistency with docs). Pick charters from the risks, not at random: run `qast risk`,
and for an empty argument choose the riskiest weakly tested area. Record them in the plan as cases
with `level`/`technique: "exploratory"`, `origin: "proposed"`, `groups: ["exploratory"]`, and an `oracle`
naming the consistency oracle (spec, docs, comparable feature, user expectation). Record with
`qast record plan --file …`.

## Phase C — Sessions

For each charter, within its time-box:
1. Generate test ideas and run them right away. Vary one factor at a time once something looks odd.
2. Keep short notes as you go. Use `qast run note --kind assumption` for interpretations, `--kind limitation` for what you could not reach, and plain notes for questions to the product owner.
3. **Every observation that matters becomes executable**: an automated check run through `qast exec <adapter> --group exploratory -- <test>`. Put durable tests in `permissions.test_dir` with `write_tests = true`. Otherwise use a self-contained test in `<run dir>/probes/` (git-ignored, local only). An observation you cannot automate is recorded as a limitation, with the reason.
4. When the time-box ends, stop the charter and note what was left unexplored.

Delegate charters to `qa-superteam:exploratory-qa-engineer` only when there are 2+ charters on
independent areas and parallel subagents are available. Give each one charter, its time-box and a
handoff. Otherwise explore yourself.

## Phase D — Anomalies → findings

Use `qa-bug-investigation` to minimize each anomaly to exact steps, expected (with oracle source) vs
actual. Record it with `qast finding add`, then run `qast reproduce --test <id> --times 3`. Something
surprising that no source says is wrong is an **open question**, not a defect. Send high/critical
findings to `qa-superteam:independent-verification-engineer`.

## Phase E — Report

Mark `qast run phase release skipped --note "exploratory session, not a release decision"`. Run
`qast gate` only if the user asks for a release view, and then run the existing suite
(`--group existing-suite`) first. Run `qast report`. Session summary (`qa-reporting`):

```
Session: <area> — time-box <planned>/<used> — charters <n>
Charter | heuristics | time | ideas tried | outcome (finding ids / questions / nothing found)
Findings: F-id [severity, derived status] — steps — evidence
Executable outputs: <test ids, added | scratch | proposed>   Limitations: <could not automate/reach, why>
Questions for the product owner; suggested next charters
```

Then run `qast run finish`.

## Stop when

The time-box is used up, or every charter is done. Never extend a time-box silently: report the
remaining ideas as suggested next charters.

## Never

- Report an exploratory observation as a defect without a reproduction execution.
- Leave an important observation only in prose: it becomes a test, a proposed test, or a stated limitation.
- Explore against production, non-authorized URLs or real user data; run load or active security tools.
- Edit application code or existing tests to make exploration easier.
