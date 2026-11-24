# Bug report template

A finding is a claim other people will act on. Write it so a stranger can reproduce it
from a clean checkout without asking you anything, and so every sentence is either an
observation with an execution id or explicitly a hypothesis.

## Recording (stdin, no scratch files in the project)

```bash
qast finding add --file - <<'EOF'
{
  "title": "<symptom> when <condition>",
  "category": "functional | security | data-integrity | performance | reliability | accessibility | contract | ai-quality | usability | other",
  "severity": "critical | high | medium | low | info",
  "summary": "<2-3 sentences: what happens, to whom, why it matters; matched severity clause>",
  "expected": "<expected result> (<source: requirement id / doc section, quoted>)",
  "actual": "<observed result> (ex-<id>)",
  "reproduction_steps": ["<step from a clean state>", "<step>", "<observe ...>"],
  "reported_by": "qa-superteam:<your agent name>",
  "test_identifiers": ["<exact id passed to qast reproduce>"],
  "execution_ids": ["ex-<failing execution>", "ex-<reproduction attempt>"],
  "evidence_ids": ["ev-<log/report/screenshot artifact>"],
  "affected": [{"path": "<source file>", "symbol": "<function or route>"}],
  "inputs": {"<minimal input name>": "<value>"},
  "environment_notes": "<runner, interpreter and tool versions, git head, dirty?, target origin>",
  "hypotheses": [
    {"statement": "<suspected cause>", "confidence": "low | medium | high", "confirmed": false, "evidence_ids": []}
  ],
  "requirement_ids": ["<REQ id>"],
  "invariant_ids": []
}
EOF
```

`qast` refuses the finding (exit 3) if any execution or evidence id does not exist or
its hash changed - fix the reference; never drop the evidence to make it pass. The
printed derived status (SUSPECTED, REPRODUCED, INCONCLUSIVE, NOT_REPRODUCED) is the
status you report. Findings are write-once: a correction is a new finding whose summary
names the one it supersedes.

## Field rules

| Field | Rule |
|---|---|
| title | Symptom and condition, not the cause: "Password-reset email sent twice when the form is submitted with Enter", not "Missing debounce in submit handler". |
| expected | Quote or cite the source. "Should obviously..." is not a source; mark it "(assumed)". |
| actual | What was observed, with the execution id. No interpretation. |
| reproduction_steps | Start from a clean state (fresh DB, new users). Include data values, headers, clicks. One action per step. Last step says what to observe. |
| test_identifiers | The exact identifier used with `qast reproduce`; otherwise the reproduction does not count toward the derived status. |
| inputs | The minimized values, including the boundary ("fails for quantity >= 101, passes at 100"). |
| environment_notes | Copy from the execution's `environment` block; add the target origin for HTTP/UI. |
| hypotheses | `confirmed: true` only with evidence ids of the execution that demonstrated it. Keep refuted hypotheses with `confirmed: false` and say "refuted by ex-..." in the statement. |
| severity | Match a clause of the policy's `[severity_definitions]` and name it in the summary. |
| reported_by | Your real agent name. The verifier must be someone else. |

## Human-readable summary (final message)

```
F-<id> [<severity>/<category>] <title>
Status:        <derived status> (<reproduction classification>, <failures>/<attempts>)
Classification:<product defect | test defect | environment | flaky (test-side | product-side) | not a defect>
Expected:      <...> - <source>
Actual:        <...> - ex-<id>
Minimal repro: <steps or test id>; boundary: <value>
Evidence:      ex-..., ev-... (log), ev-... (screenshot/trace for UI)
Severity:      <level> - matches "<policy definition clause>"
Hypotheses:    H1 <statement> - confirmed by ex-... | unconfirmed (<confidence>)
Next:          independent verification by qa-superteam:independent-verification-engineer | owner decision on <question>
Not verified:  <what was not checked and why>
```

## UI-specific evidence

- Screenshot of the wrong state and of the step before it; trace (`trace.zip`) for timing issues; HAR for network problems. Save them to `$QAST_ARTIFACT_DIR` inside the test so they are hashed and linked to the result.
- Record viewport, locale/direction, browser and version.
- Accessibility defects: the axe rule id and the affected selector, plus what a keyboard or screen-reader user experiences.
