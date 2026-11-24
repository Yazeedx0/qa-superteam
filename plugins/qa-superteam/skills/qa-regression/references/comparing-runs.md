# Comparing two runs per test identifier

The question is not "did the suite pass?" but "which tests changed status, and why?".
Compare result by result, using the identifiers the adapters recorded
(`tests/test_x.py::test_y[param]`, `<dataset>::<case id>`).

## Pick a comparable baseline

- `qast run list` sorts by id (timestamp first); runs started in the same second sort by random suffix, so read `run.json` (`created_at`, `mode`, `scope`, `base_ref`, `environment.git_head`) or `qast run status --run <id>` to choose.
- Comparable means: same suite command and paths, same adapter, ideally the base commit of the change (`environment.git_head`). A baseline that ran a subset makes every other test look "new".
- Note environment differences (interpreter and tool versions, `ci`, `git_dirty`) from each execution's `environment` block; a status change that lines up with an environment change is an environment lead, not a regression.

## Script (read-only, stdlib)

```bash
BASE_RUN=20261120-101500-regression-1a2b   # baseline run id (example)
HEAD_RUN=20261123-091200-regression-3c4d   # this run (example)
python3 - "$BASE_RUN" "$HEAD_RUN" <<'EOF'
import glob, json, sys

def statuses(run):
    """identifier -> status; primary executions only, in recording order."""
    execs = [json.load(open(p, encoding="utf-8")) for p in glob.glob(f".qa-superteam/runs/{run}/executions/*.json")]
    out = {}
    for ex in sorted(execs, key=lambda e: e["started_at"]):
        if ex.get("reproduction_of"):
            continue  # reproduction attempts are finding evidence, not suite results
        for r in ex["results"]:
            out.setdefault(r["identifier"], []).append(r["status"])
    return {k: (v[0] if len(set(v)) == 1 else "MIXED:" + "/".join(v)) for k, v in out.items()}

base, head = statuses(sys.argv[1]), statuses(sys.argv[2])
BAD = ("FAILED", "ERROR")
def label(b, h):
    if b is None: return "NEW TEST"
    if h is None: return "NOT RUN NOW"
    if h.startswith("MIXED") or h == "INCONCLUSIVE": return "UNSTABLE"
    if b == "PASSED" and h in BAD: return "NEW FAILURE"
    if b in BAD and h == "PASSED": return "NOW PASSING"
    if b in BAD and h in BAD: return "STILL FAILING"
    if b != h: return "CHANGED"
    return "same"
rows = [(label(base.get(t), head.get(t)), t, base.get(t, "-"), head.get(t, "-")) for t in sorted(set(base) | set(head))]
for row in sorted(rows, key=lambda r: (r[0] == "same", r[0], r[1])):
    print("{:<14} {}  {} -> {}".format(*row))
EOF
```

A test that ran in several executions of the same run with different outcomes shows as
`MIXED:...` - that is flakiness evidence by itself.

## Interpreting transitions

| Transition | Means | Next step |
|---|---|---|
| NEW FAILURE (PASSED -> FAILED/ERROR) | Regression candidate, or an environment change | `qa-bug-investigation`; check whether the diff touched the test or the code it exercises |
| NOW PASSING (FAILED/ERROR -> PASSED) | Fixed - or flaky | `qast reproduce --test <id> --times 3`; call it fixed only when every attempt passes (`not-reproduced`) and a change in the diff explains the fix |
| STILL FAILING | Known problem | Link the existing finding id; not a new regression, still a failure for the gate |
| NOT RUN NOW (status -> absent) | Coverage lost: test deleted, renamed, deselected, collection error, or the run used a narrower command | Find out which; a deleted or deselected test is reported, never treated as passing |
| NEW TEST (absent -> status) | Added or renamed test | Renamed tests pair with a NOT RUN NOW row; check the pair |
| UNSTABLE (MIXED or INCONCLUSIVE) | Nondeterminism in this run | Flaky handling: reproduce, report counts, propose quarantine to a human |
| CHANGED (e.g. PASSED -> SKIPPED) | Skip conditions changed | A newly skipped test is lost coverage; find the skip reason |

## Reporting

```
Comparison: <base run> (<git head>, <date>) -> <head run> (<git head>, <date>)
NEW FAILURE    3   tests/...::test_a (-> investigation F-...), ...
NOW PASSING    1   tests/...::test_b (re-run 3/3 passed: ex-..., fixed by <commit>)
STILL FAILING  2   tests/...::test_c (F-...), ...
NOT RUN NOW    1   tests/...::test_d (deleted in <commit>)
UNSTABLE       1   tests/...::test_e (2/5 failed; quarantine proposed, decision pending)
Environment:   python 3.12.3 -> 3.12.3; pytest 8.3 -> 9.0 (possible cause for ...)
```

Counts alone ("97 % passed") hide exactly the rows above; always list them.
