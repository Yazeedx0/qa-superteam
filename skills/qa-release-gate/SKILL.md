---
name: qa-release-gate
description: Use when a release decision is needed - checks the required evidence exists, runs the deterministic qast gate, explains PASS, REVIEW_REQUIRED or BLOCK from the triggered rules, and never overrides policy with opinion.
---

# QA release gate

> `qast` is on PATH in Claude Code. In other agents, run `../using-qa-superteam/scripts/qast` (path relative to this file) wherever this skill says `qast`.

## Purpose

Turn recorded evidence into a release decision anyone can audit: same evidence plus
same policy gives the same decision. Your job is to make sure the evidence is complete
and honest before gating, run the gate, and explain the outcome. You do not judge
release readiness yourself.

## Use when / Do not use when

Use when:
- Phase J of any workflow; "can we ship / merge this?"; CI needs `qast gate --exit-code`.
- Someone asks what a rule means or how to customize the policy.

Do not use when:
- There is no evidence yet and the user wants an instant verdict: say no decision exists without executed tests, start a run (the user's `/qa-superteam:release-check`, or `qast run start --mode release-check`) and gather evidence first.
- The question is whether one specific failure is real: `qa-bug-investigation`, then `qa-verification`.

## Inputs & assumptions

- An active run with executions from `qast exec`, findings from `qast finding add`, verifications from `qast verify`, and `plan.json`/`risks.json` if planning happened.
- The policy from `[policy] path` in `.qa-superteam/config.toml`, else the plugin's `policies/default.toml`; `strict.toml` exists for regulated or high-stakes releases.

## Tools

| Command | Use |
|---|---|
| `qast run status --json` | what evidence exists: phases, executions with groups and status, findings with derived status |
| `qast validate` | schema and sha256 check of every record and artifact (feeds `R-EVIDENCE-INTEGRITY`) |
| `qast finding list` | derived finding statuses |
| `qast gate [--policy FILE] [--json] [--exit-code]` | the decision; writes `decision.json`, replaced on every run |
| `qast run note "<text>" --kind decision` | record a decision a human states, verbatim, with who made it |
| `qast report` | renders the decision with the evidence (then `qa-reporting`) |

If `qast gate` prints a policy error there is no decision: report the error and stop.
Never substitute your own verdict.

## Method

1. **Evidence pre-check** with `qast run status --json`:
   - the existing suite ran with `--group existing-suite` (mandatory under the default policy);
   - every plan case in `critical-journeys`, `contract` or `regression` ran through its `test_ref`;
   - every FAILED or ERROR result is explained by a finding or has been triaged (`qa-bug-investigation`);
   - every high/critical finding went to independent verification (`qa-verification`);
   - `qast validate` reports no problems.

   Close a gap first when scope, budget and permissions allow, using the owning skill. Otherwise gate anyway: missing evidence is an input the policy handles, and it never becomes a pass.
2. **Policy.** Use the configured policy. Pass `--policy` only when the user asks (bundled strict policy: `qast gate --policy policies/strict.toml`; a relative path is tried against the current directory, then the project root, then the plugin). Each gate run replaces `decision.json`, so after a comparison run the configured policy again last, unless the user chose the other policy for this release. Never switch policy to obtain a better outcome. Name policy, version and sha in every answer.
3. **Run** `qast gate --json` (CI: `qast gate --exit-code`; 0 PASS, 10 REVIEW_REQUIRED, 20 BLOCK).
4. **Read every triggered rule** (`"triggered": true`): its reason, its refs (finding ids, test ids), and what would change it. Semantics: `references/policy.md`. Per-rule resolutions: [references/rule-playbook.md](references/rule-playbook.md).
5. **Explain the decision.** It is the most severe triggered outcome (BLOCK > REVIEW_REQUIRED > PASS); PASS also requires positive evidence (`R-POSITIVE-EVIDENCE`). Quote each rule id and translate it into one plain sentence.
6. **REVIEW_REQUIRED: list the human decisions.** One per triggered REVIEW rule, addressed to a role (release manager, product owner, security lead): the question, the evidence ids, the risk if accepted, and the options (accept with a recorded rationale, produce the missing evidence, fix first). Do not answer them yourself and never describe REVIEW_REQUIRED as "basically a pass".
7. **BLOCK: the path to unblock.** Each blocking item with evidence, and the sequence that changes it: fix → new run on the fixed build → re-execute → re-verify → `qast gate`.
8. **Re-gate** after any new evidence and immediately before `qast report`; the report flags a decision whose inputs digest no longer matches the records.
9. **Policy questions.** Explain keys from `docs/policy.md`. Changing policy is a team decision: draft a proposed policy file or diff only when asked, apply it only on the user's explicit instruction, and never to change the decision for the run being evaluated.

## Stop when

The gate has run on the final evidence, every triggered rule is explained, and REVIEW
or BLOCK items are listed with owners. At most one "close evidence gap → re-gate" cycle
per new execution; no re-gating loops without new evidence.

## Safety

Never:
- Override, reinterpret or round up the decision, or claim PASS when `qast gate` did not print PASS.
- Edit the policy, `.qa-superteam/config.toml`, plan groups, priorities, risk levels, finding severities or execution tags to change an outcome.
- Re-run a failing mandatory suite hoping for green: every execution in a mandatory group counts for the run.
- Record a verdict to clear a rule without the evidence `qast verify` requires, or file product findings you do not believe in to silence `R-UNTRIAGED-FAILURES`.
- Edit or delete anything under `.qa-superteam/runs/`.

## Output contract

- `decision.json` written by `qast gate`.
- The answer, in this shape:

```
RELEASE DECISION: <PASS|REVIEW_REQUIRED|BLOCK> — policy <name> v<version> (sha <first 12>), inputs digest <first 12>
Why:
- <RULE-ID>: <plain-language reason> (refs: <ids>)
Blocking items (BLOCK):             <finding/test> — <evidence> — <what unblocks it>
Human decisions needed (REVIEW):    1. <role>: <question> — evidence <ids> — risk if accepted: <...> — options: <...>
Evidence gaps that fed the decision: <not executed / BLOCKED / skipped items>
```

## Quality checklist

- [ ] The gate ran after the last execution, finding and verification.
- [ ] The stated decision matches `decision.json` exactly.
- [ ] Every triggered rule is listed with its id and refs.
- [ ] REVIEW_REQUIRED lists concrete human decisions; the agent answered none of them.
- [ ] No policy, config, tag, severity, priority or level changed to alter the outcome.
- [ ] Policy name, version and sha are stated.

## References

- `references/policy.md`: every rule id and policy key, defaults, customization examples.
- [references/rule-playbook.md](references/rule-playbook.md): per rule, typical causes, legitimate resolutions, the human question, and moves that are never acceptable.
