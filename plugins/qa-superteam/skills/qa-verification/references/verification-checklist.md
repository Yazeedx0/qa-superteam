# Verification checklist

Work through it in order; each line is answered with evidence, not belief. Stop at the
first line that decides the verdict, but finish the evidence audit before recording
anything.

## A. Independence

- [ ] `reported_by` (from `qast finding show <id>`) differs from your verifier identity.
- [ ] You did not write the finding's test, run its original executions, or record it in this session.
- [ ] Your `--verifier` value is your real identity, not a name picked to differ.

Any "no" -> do not verify; hand over and report "awaiting independent verification".

## B. The claim

- [ ] Restate the claim in one line: action, state, expected, actual.
- [ ] Open the cited requirement yourself and quote the sentence that defines the expected result.
- [ ] Expected follows from the quote (not only from "obviously" or from current behaviour elsewhere).
- [ ] The section is in scope for this release (not "planned", not "out of scope").
- [ ] The severity matches a clause of the policy's `[severity_definitions]`; note disagreement in the rationale.

## C. The reporter's evidence

- [ ] `qast validate` reports no integrity problem for the finding's artifacts.
- [ ] Every `execution_ids` entry exists and at least one contains a FAILED result for a `test_identifiers` entry.
- [ ] The failure message shows the claimed actual value, not a different failure (an ERROR, a setup crash, an unrelated assertion).
- [ ] The test's expectation matches the quoted requirement (units, rounding, inclusive/exclusive bounds, which user, which state).
- [ ] The test setup is realistic: correct user and permissions, data a real user could produce, no dependence on test order, wall clock or unseeded randomness.
- [ ] Derived status and basis from `qast finding show` are consistent with what you found (e.g. an intermittent reproduction already makes it INCONCLUSIVE).

Problems in C are not a verdict yet - they tell you what your own execution must check.

## D. Your own evidence

- [ ] Independent re-run: `qast reproduce --test <id> --times 3` -> classification and counts noted.
- [ ] Alternate oracle (always when there is no linked test; preferably for critical findings): a different test of the same property, run with `qast exec <adapter> --label "verify/<F-id>/<oracle>" -- <test>`, outcome noted.
- [ ] Your executions ran in-process or against an authorized target, with data you created.
- [ ] Environment of your executions compared with the reporter's (`environment` block) when outcomes differ.

## E. Recording

- [ ] Verdict chosen with the decision table; reason class named for INCONCLUSIVE.
- [ ] `--execution` lists every execution you ran for this verdict; `--test` lists your alternate-oracle test ids.
- [ ] Rationale written with the template below.
- [ ] Exit code 3 handled: genuine omission corrected, or INCONCLUSIVE recorded with the failed gate; nothing bypassed.
- [ ] `qast finding show <id>` afterwards shows the derived status you expect.

## Rationale template

```
Claim: <one line>.
Requirement: <id/section> "<quoted sentence>".
Reporter evidence: <ex ids>; <what it shows; problems found in the audit>.
My evidence: <method>: <ex ids> -> <counts, e.g. 3/3 FAILED with 'assert "Doe" == "Doe, Jane"'>; <alternate oracle: test id -> result>.
Verdict: <CONFIRMED|REJECTED|INCONCLUSIVE> because <reason; for INCONCLUSIVE the reason class>.
Notes: <severity disagreement, environment differences, what would make it conclusive>.
```

Quote with shell-safe quoting (the rationale is one argument), and redact secrets.

## Example commands

```bash
qast finding show F-1a2b3c4d
qast validate
qast reproduce --test tests/test_export.py::test_names_with_commas --times 3
qast verify F-1a2b3c4d --verdict CONFIRMED --method independent-rerun \
  --verifier qa-superteam:independent-verification-engineer \
  --execution ex-0a1b2c3d4e5f --execution ex-1b2c3d4e5f6a --execution ex-2c3d4e5f6a7b \
  --rationale "Claim: ... Requirement: EXPORT-2 '...'. My evidence: independent-rerun ex-0a1b..., ex-1b2c..., ex-2c3d... -> 3/3 FAILED ... Verdict: CONFIRMED because ..."

# a gate refused CONFIRMED and the gap cannot be closed legitimately:
qast verify F-1a2b3c4d --verdict INCONCLUSIVE --method independent-rerun \
  --verifier qa-superteam:independent-verification-engineer \
  --execution ex-0a1b2c3d4e5f --execution ex-1b2c3d4e5f6a --execution ex-2c3d4e5f6a7b \
  --rationale "Reason class: flaky 1/3. Gate 'reproduction stable' refused CONFIRMED. ..."
```
