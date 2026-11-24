# Minimization and isolation

A minimal reproduction makes a finding cheap to verify, fix and keep as a regression
test. Minimize the *inputs*, the *steps* and the *environment*, and record each variant
as an execution so the shrinking itself is evidence:
`qast exec <adapter> --label "min/<n>" -- <args>`. Budget: 10 variants.

## Variant log (keep it in the summary)

```
min/1  full original input                        FAILED  ex-...
min/2  memo removed                               FAILED  ex-...
min/3  amount 5000 -> 2500                        FAILED  ex-...
min/4  second user removed                        PASSED  ex-...   <- second user is needed
min/5  amount 2500 -> 101                         FAILED  ex-...
min/6  amount 100                                 PASSED  ex-...   <- boundary between 100 and 101
```

The last FAILED variant is the minimal reproduction; adjacent PASSED variants show which
parts are necessary. A variant that ERRORs (test broke) tells you nothing about the
product - fix the variant, do not count it.

## Input minimization (delta debugging)

1. **Halve.** Split the input (list items, JSON keys, text, steps) in two; keep a half that still fails. If neither half fails alone, the failure needs parts of both: try removing smaller chunks (quarters, then single elements).
2. **Simplify values.** Long strings -> shortest string that still fails; large numbers -> smallest; unicode -> ASCII if the failure persists (and say so if it does not - that is the finding).
3. **Find the boundary** by binary search on the one numeric or length dimension that matters: `lo` passes, `hi` fails, test `mid`, repeat until adjacent. Report both sides.
4. **Remove steps** one at a time from the start of the scenario (setup steps are often unnecessary) and from the middle.
5. **Remove environment**: default config, no optional services, single user, empty database plus the minimum data.

Stop at 10 variants even if more shrinking is possible; report the smallest failing
variant reached.

## Read-only isolation of the code path

- Stack trace and log lines of the failing execution (from its log artifact) - the first frame in project code is the starting point, not the conclusion.
- `git log -p --follow -- <file>`, `git log -S '<symbol or literal>'`, `git blame -L <start>,<end> -- <file>`: when and why the relevant lines changed.
- Compare with comparable code paths in the same product (the "Product" oracle): a sibling endpoint that performs the check the failing one skips is strong evidence for a hypothesis.
- Toggle a suspected condition **without editing application code**: different inputs, configuration or environment variables the app reads, a test double or monkeypatch inside your own probe. If the outcome flips when only that condition changes, record both executions and mark the hypothesis `confirmed: true` with their evidence ids.

## `git bisect run` (only when explicitly requested)

Bisect moves `HEAD`, so it never runs in the user's checkout. Only when the user (or the
delegation prompt) explicitly allows it, and only with a known good and a known bad
commit:

```bash
WT=.qa-superteam/runs/<run-id>/bisect          # git-ignored, disposable
git worktree add --detach "$WT" <bad-ref>
git -C "$WT" bisect start <bad-ref> <good-ref>
git -C "$WT" bisect run sh -c '<command that runs only the minimal test; exit 125 if it cannot run>'
git -C "$WT" bisect log                         # keep this text for the finding

# record the conclusion as evidence before cleaning up
git -C "$WT" checkout -q --detach refs/bisect/bad
qast exec pytest --cwd "$WT" --label "bisect/first-bad" -- <minimal test id>
git -C "$WT" checkout -q --detach 'refs/bisect/bad~1'
qast exec pytest --cwd "$WT" --label "bisect/parent" -- <minimal test id>

git -C "$WT" bisect reset
git worktree remove --force "$WT"
```

"Introduced by <commit>" is a confirmed hypothesis only with those two executions
(FAILED on the first bad commit, PASSED on its parent). A bisect over commits that do
not build or need migrations yields `125` skips - report the range, not a single commit.
Use the adapter the project uses; `pytest` above is an example.
