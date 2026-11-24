# Session notes and session report

## Notes while probing

One line per event, written as it happens (not reconstructed at the end). Keep them in
your working context or in `.qa-superteam/runs/<run-id>/probes/EX-<n>-notes.md`; never in
the project tree.

```
[00:02] SETUP  in-process client, temp DB, users A (funded 10 000) and B
[00:04] OBS    ex-1a2b: POST with amount 10.5 -> 201, stored amount 10 (silent truncation)
[00:05] BUG?   H2 supported: float accepted; oracle SPEC 3.1 "positive integer" -> repeat
[00:07] OBS    ex-3c4d: same probe again -> FAILED again (consistent)
[00:09] Q      is a memo of only whitespace "present"? SPEC silent -> question, not a finding
[00:12] IDEA   amount as "100" string - try after H3
[00:15] BLOCKED browser probes: playwright-node missing (qast doctor); in-process only
[00:20] TIME   time-box reached; H3 not probed -> follow-up charter EX-2
```

Tags: `SETUP`, `OBS` (observed, cite the execution id), `BUG?` (oracle violation, not
yet a finding), `Q` (question for the product owner), `IDEA` (probe for later),
`BLOCKED` (could not probe, why), `TIME` (budget checkpoints). Inference is written as
inference: "probably because the handler casts to int" is a hypothesis, not an OBS.

## Session report (one per charter, in the final message)

```
SESSION EX-<n> - <charter mission, one line>
Area / risk:      <area> / <risk id>
Budget:           <time used> of <time-box> min, <probes run> of <probe budget> probes
Setup:            <in-process | local server origin>, <data used>

Hypotheses
  H1 <statement> - SUPPORTED by ex-... | REFUTED by ex-... | NOT PROBED (<why>)
  H2 ...

Findings (derived status from `qast finding list`)
  F-... [<severity>] <title> - <status>, executions ex-..., evidence ev-...

Questions / ambiguities (recorded as assumption notes)
  - <specific question, with the requirement section it concerns>

Limitations (recorded as limitation notes)
  - <what could not be probed, why, what would unblock it>

Test ideas
  - durable test added: <path> (only with write_tests) | proposed: <test, oracle, layer>

Not explored
  - <parts of the area or heuristics deliberately left out>

Follow-up charters
  - EX-<n+1>: <mission> - motivated by <execution/observation>
```

## Rules for the report

- Every OBS cited in the report names an execution id; anything without one is labelled "unrecorded observation - not evidence".
- A hypothesis is SUPPORTED only by a recorded execution whose result shows it. "Seemed fine" is NOT PROBED or REFUTED-with-evidence, never SUPPORTED.
- Intermittent outcomes are reported as such with the counts (e.g. 2/5 failed) and handed to `qa-bug-investigation`.
- No statement that an area "works" or "is safe": report what was probed, with which oracle, and what was not.
