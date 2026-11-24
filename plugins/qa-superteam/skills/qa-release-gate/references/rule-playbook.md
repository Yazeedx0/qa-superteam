# Gate rule playbook

What to do when a rule triggers. Exact semantics are in
`policy.md`. Two facts shape most resolutions:

- **A run describes one build.** Executions are write-once and every execution in a
  mandatory group counts. After a fix or an environment change, evaluate in a new run
  (`qast run start`) rather than piling passing executions onto failing ones.
- **The human question** is what you hand to a person when the outcome is
  REVIEW_REQUIRED. Ask it; do not answer it.

## R-EVIDENCE-EXISTS

- **Cause:** no primary execution in this run (nothing ran, or only `qast reproduce`).
- **Resolve:** run the existing suite: `qast exec <adapter> --group existing-suite -- <paths>` (the profile's `suggested_command`).
- **Human question:** "Release with no executed tests in this run?"
- **Never:** cite executions from another run or session as if they were this run's evidence.

## R-EVIDENCE-INTEGRITY

- **Cause:** an artifact is missing or its sha256 changed, or a finding/verification references an execution or artifact that does not exist.
- **Resolve:** `qast validate` for details. Find out how the evidence changed. Produce fresh evidence with new executions; record findings that reference existing ids.
- **Human question:** "Evidence <ids> was modified or is missing; accept a decision built on the remaining evidence?"
- **Never:** edit artifacts, records or hashes.

## R-CONFIRMED-BLOCKING (always BLOCK)

- **Cause:** a CONFIRMED finding at or above `block_at` for its category.
- **Resolve:** fix the defect; in a new run on the fixed build, execute the regression test and related suites, re-verify, re-gate. Within this run the confirmed finding stays confirmed.
- **If the team disputes severity or category:** that is a human decision outside the gate. Record it with `qast run note "<who> decided <what> because <why>" --kind decision`; the gate result for this run stays BLOCK.
- **Never:** lower the severity, recategorize, or record REJECTED without new verification evidence.

## R-CONFIRMED-REVIEW

- **Cause:** a CONFIRMED finding at or above `review_at` that does not block.
- **Human question:** "Ship with confirmed defect <id> (<severity>, <category>, <title>): accept with a workaround, fix first, or defer?"

## R-UNVERIFIED-HIGH-IMPACT

- **Cause:** a finding at or above `unverified_review_at` that is SUSPECTED, REPRODUCED, NOT_REPRODUCED or INCONCLUSIVE.
- **Resolve:** independent verification through `qa-verification` (`qa-superteam:independent-verification-engineer`, never the reporter). CONFIRMED moves it to the confirmed rules; REJECTED needs the verifier's own evidence.
- **Human question:** "Release while high-severity claim <id> (<status>) is unverified?"
- **Never:** verify your own finding, or reject one without executing anything.

## R-MANDATORY-GROUP:<group>

| Reason in the output | Resolve |
|---|---|
| not executed | run the group: `qast exec ... --group <group> -- ...` |
| BLOCKED | install the tool (`qast doctor` hint) or record the gap as a limitation; a later execution with results supersedes a BLOCKED one |
| failing tests | triage each through `qa-bug-investigation`. Product defect → finding → verification. Test defect → info-severity `Test defect:` finding with evidence and a proposed fix; never edit the assertion to pass |
| errored tests | fix the environment or setup and evaluate in a new run; the ERROR stays in this run |
| inconclusive results | `qast reproduce --test <id> --times 3` to classify; flaky tests are reported, not retried until green |
| no passing result | the group ran but verified nothing (all skipped or deselected): fix the selection |
| skipped / not-run over the allowance | read the skip reasons; a skip that hides a known defect is a finding candidate |

- **Human question (skips):** "<n> tests in the mandatory suite were skipped (<ids>, reasons): accept as not relevant to this release?"
- **Never:** remove the group tag, raise `max_skipped_in_mandatory`, delete skip markers, or re-run until a green execution appears.

## R-PLANNED-MANDATORY-CASES

- **Cause:** a plan case in a `mandatory_if_planned` group has no passing latest result: never executed, proposed (no `test_ref`), skipped, blocked, errored, inconclusive, or failed.
- **Resolve:** execute the case through its `test_ref` with its groups. For this rule the latest execution of the case supersedes earlier ones. Proposed cases cannot pass: they stay as review items.
- **Human question:** "Planned <group> case <TC id> was not executed (<reason>): accept the release without it?"
- **Never:** remove cases from the plan or change their groups after the fact; plan history is kept and visible.

## R-UNTRIAGED-FAILURES

- **Cause:** FAILED or ERROR results (outside scanner and ai-eval executions) that no finding references by test identifier or execution id, and that are not a verifier's own execution recorded in a verification.
- **Resolve:** triage each listed result through `qa-bug-investigation`. Product defects become findings whose `test_identifiers` match the failing test, which links them.
- **For failures judged to be test or environment defects:** record each as a finding with `category: "other"`, `severity: "info"`, a title starting `Test defect:` or `Environment:`, the failing `test_identifiers` and evidence. That triages it without a product severity and never blocks. Never file a product defect you do not believe in.
- **Human question (if the classification is contested):** "<n> failures were classified as test or environment defects (<finding ids>, evidence): agree they are not product defects for this release?"

## R-FLAKY-CRITICAL

- **Cause:** INCONCLUSIVE results in a `critical` group (often a Playwright `flaky` result or an axe `incomplete`), or a finding whose recorded reproduction is intermittent.
- **Resolve:** classify with `qast reproduce`; find the cause of the flakiness (`qa-bug-investigation`); report it.
- **Human question:** "Critical journey <id> behaves intermittently: accept the risk that it fails for real users?"
- **Never:** add retries to the test, or re-run until green and report only the green run.

## R-AI-EVAL-PASS-RATE / R-AI-EVAL-INCONCLUSIVE

- **Cause:** the pooled pass rate over all ai-eval executions in the run is below `min_pass_rate`; or cases are INCONCLUSIVE (uncalibrated judge, disagreement across samples) or ERROR.
- **Resolve:** analyse failing cases (`qa-ai-systems`); calibrate the judge with human labels (`qast ai-eval calibrate`); evaluate the fixed system in a new run.
- **Human question:** "<n> AI eval cases are undecided: will a person review them before release?"
- **Never:** drop failing cases from the dataset, edit golden expectations, or present only the best of several executions (all are pooled).

## R-UNTESTED-HIGH-RISK

- **Cause:** high/critical plan cases without a PASSED or FAILED result, high/critical risks no plan case references, or high risks without any plan.
- **Resolve:** execute the cases; add cases for uncovered risks (`qa-test-design`); or let a human accept the residual risk.
- **Human question:** "Risk <id> (<area>, <level>) has no executed test: accept the residual risk?"
- **Never:** lower a risk level or case priority without new evidence and a written rationale.

## R-POSITIVE-EVIDENCE

- **Cause:** nothing else triggered, but no mandatory group passed and no planned mandatory case passed.
- **Resolve:** run the mandatory suite with its group tag; check `[groups] mandatory` in the policy.
- **Human question:** "No mandatory check passed in this run; release without positive evidence?"
