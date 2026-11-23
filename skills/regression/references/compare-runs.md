# Comparing a regression run with its baseline run

`qast` has no compare command. This read-only script diffs the per-test results that two runs
recorded. It reads only `executions/*.json` in the two run directories, skips `qast reproduce`
re-runs, and keeps the latest status for each test identifier (later executions supersede earlier ones).

Run directories are `<output dir>/runs/<run id>`. The output dir is `.qa-superteam` unless
`[output] dir` in `.qa-superteam/config.toml` says otherwise. `qast run start` prints the current one.

```bash
python3 -I - "<baseline run dir>" "<current run dir>" <<'EOF'
import json, sys
from pathlib import Path

base_dir, cur_dir = Path(sys.argv[1]), Path(sys.argv[2])

def results(run_dir):
    out = {}
    execs = sorted((run_dir / "executions").glob("*.json"), key=lambda p: (p.stat().st_mtime, p.name))
    for p in execs:
        ex = json.loads(p.read_text(encoding="utf-8"))
        if ex.get("reproduction_of"):
            continue
        for r in ex.get("results", []):
            out[r["identifier"]] = (r["status"], ex["id"])
    return out

base, cur = results(base_dir), results(cur_dir)
BAD = {"FAILED", "ERROR"}
rows = []
for tid in sorted(set(base) | set(cur)):
    b, c = base.get(tid, (None, None))[0], cur.get(tid, (None, None))[0]
    if c is None:
        cls = "NOT_RUN_NOW"
    elif b is None:
        cls = "NEW_TEST_FAILING" if c in BAD else "NEW_TEST"
    elif c in BAD and b == "PASSED":
        cls = "NEW_FAILURE"
    elif c in BAD and b in BAD:
        cls = "KNOWN_FAILURE"
    elif c == "PASSED" and b in BAD:
        cls = "FIXED"
    elif "INCONCLUSIVE" in (b, c):
        cls = "FLAKY"
    elif b != c:
        cls = "CHANGED"
    else:
        continue
    rows.append((cls, tid, b, c, cur.get(tid, (None, None))[1]))
order = ["NEW_FAILURE", "NEW_TEST_FAILING", "FLAKY", "CHANGED", "KNOWN_FAILURE", "NOT_RUN_NOW", "FIXED", "NEW_TEST"]
for cls, tid, b, c, ex in sorted(rows, key=lambda r: (order.index(r[0]), r[1])):
    print(f"{cls:<17} {tid}  {b} -> {c}  {ex or ''}")
same = len(set(base) & set(cur)) - sum(1 for r in rows if r[1] in base and r[1] in cur)
print(f"unchanged: {same} · baseline tests: {len(base)} · current tests: {len(cur)}")
EOF
```

## Reading the output

| Class | Meaning | Next step |
|---|---|---|
| `NEW_FAILURE` | passed in the baseline, FAILED/ERROR now | regression candidate: `qast reproduce`, then investigate |
| `NEW_TEST_FAILING` | not in the baseline, failing now | new test or renamed test: check before calling it a regression |
| `FLAKY` | INCONCLUSIVE in either run | not a regression claim; flaky-test report |
| `CHANGED` | other transitions (for example PASSED → SKIPPED) | a newly skipped test is a coverage loss: report it |
| `KNOWN_FAILURE` | failing in both runs | link the earlier finding; investigate only if the failure message changed |
| `NOT_RUN_NOW` | in the baseline, absent now | selection gap or deleted test: say which |
| `FIXED` | failing before, PASSED now | report it; the earlier finding stays as recorded |
| `NEW_TEST` | new and passing | informational |

The comparison is only meaningful if both runs executed comparable selections. Say so when the
baseline ran a different test set, interpreter or tool version. Executions record `environment`
(`git_head`, tool versions).
