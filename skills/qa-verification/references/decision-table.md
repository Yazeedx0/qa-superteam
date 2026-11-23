# Decision table: evidence pattern -> verdict

Find the first row that matches what *you* observed in *your* executions. The verdict
column is what `qast verify` should record; the method column is the `--method` value.
"Own" always means executions the verifier ran in this verification.

## CONFIRMED (all machine gates must pass)

| Evidence pattern | Verdict | Method |
|---|---|---|
| Own re-run of the finding's test FAILED in every attempt (`consistent`), failure message matches the claimed actual, assertion encodes the quoted requirement, evidence intact | CONFIRMED | `independent-rerun` |
| Own alternate-oracle test of the same property FAILED (and repeats the same way), requirement supports the expected value | CONFIRMED | `alternate-oracle` (pass `--test <your id>`) |
| Both of the above | CONFIRMED | `independent-rerun` (mention the alternate oracle and pass both execution ids) |

## REJECTED (the claim is wrong, shown by evidence or by the requirement text)

| Evidence pattern | Verdict | Method |
|---|---|---|
| The requirement says something else than the finding's "expected" (misread requirement); quote both | REJECTED | `manual` |
| The behaviour is explicitly out of scope or planned for later in the requirements | REJECTED (say "not a defect against current requirements"; suggest a risk note if it matters) | `manual` |
| The failing test's own expectation contradicts the requirement (test bug), and your corrected-oracle test PASSES | REJECTED (test defect; propose the test fix) | `alternate-oracle` |
| Own re-runs and an alternate oracle PASS under the same inputs, steps and environment as reported, and the original failure is explained (e.g. stale data, wrong fixture) | REJECTED | `independent-rerun` |
| A scanner hit that your executable check shows unreachable or harmless (e.g. the flagged input is never user-controlled - shown by a test), quoted with the reasoning | REJECTED | `alternate-oracle` |

Rejecting needs the same standard as confirming: your own passing executions of the
claimed scenario, or a documentary contradiction in the requirement. Code reading alone
neither confirms nor rejects.

## INCONCLUSIVE (record the reason class first in the rationale)

| Evidence pattern | Reason class | Method |
|---|---|---|
| Claim rests on code reading only and you could not build an executable check (missing tool, no entry point, needs data you may not create) | blocked: <what is missing> | `code-inspection` or `manual` |
| Scanner-only finding without a demonstration either way | unsupported: scanner-only | `manual` |
| Own reproduction `intermittent` (any mix of FAILED and PASSED) | flaky: <failures>/<attempts> | `independent-rerun` |
| Own runs PASS but the reporter's FAILED, and environments differ in a way that may matter (versions, timezone, data, CI) | environment-dependent: <difference> | `independent-rerun` |
| Your execution is BLOCKED or ERROR (tool missing, setup broken, target not authorized) | blocked: <reason, install hint> | `independent-rerun` |
| Requirement is silent or ambiguous about the expected result | ambiguous requirement: <section> (raise with the product owner) | `manual` |
| A gate refused CONFIRMED and the gap cannot be legitimately closed | gate: <check name> - <detail> | the method you used |
| You lack independence and no other verifier is available | Do not record a verdict; report "awaiting independent verification" | - |

## Edge cases

- **Defect real, severity wrong**: verdict is about existence - CONFIRMED - and the rationale says which severity definition actually matches. The lead decides about re-filing.
- **Defect real, but a different one than claimed** (e.g. the claim says "the export drops the last row", your run shows every row present but one column shifted): REJECTED for this claim; report the new observation to the lead for investigation. Do not stretch a finding to fit different evidence.
- **Finding has no `test_identifiers`**: pass `--test <your test id>` so the failing-evidence gate matches only the relevant result, not any unrelated failure in your execution.
- **Earlier verification exists**: a new verdict supersedes it in the derived status; explain in the rationale what new evidence justifies it.
- **Pressure to confirm** ("we need it confirmed to block the release"): urgency changes nothing. Under the default policy an unverified high/critical finding already makes the gate require review; that is the correct outcome while evidence is missing.
