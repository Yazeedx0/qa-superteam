# Regression selection algorithm

Selection orders the work and directs attention; the mandatory existing suite still runs
in full. Every selected test carries the reason it was selected, so the report can show
why it ran and a reviewer can spot what selection missed.

## 1. Change-based (`qast impact`)

```bash
qast impact --base <ref>                 # merge-base(<ref>, HEAD) vs working tree, incl. untracked files
qast impact --base <ref> --head <ref2>   # committed range only
qast impact --base <ref> --no-worktree   # ignore uncommitted changes
```

`impact.json` holds, per changed file: status, lines, kind (source/test/config/docs),
risk signals (money, auth, data model, crypto, AI, API surface, UI, build, dependency).
Tests are selected by three heuristics, each recorded as the reason:

| Reason | Fires when |
|---|---|
| `changed test` | the test file itself changed |
| `name match: <file>` | the test file stem equals or contains the changed module stem |
| `import reference: <file>` | the test file mentions the changed module's import path |

`changed_source_without_related_tests` lists changed source files no heuristic covered -
a coverage gap to report, and a reason to widen.

### Widening rules (apply in order, note each as a reason)

1. **Callers**: for each changed public function, class or route, search the test tree for its name (`grep -rn "<symbol>" <test dirs>`); add those tests ("caller of <symbol>").
2. **Risk signals**: a changed file with money, auth, data-model or crypto signals -> add the whole component's tests (directory or package), not only name matches.
3. **Config, dependency, build, schema or migration changes** -> the full suite is the selection; there is no meaningful subset.
4. **Shared code** (utilities, base classes, fixtures, `conftest.py`) -> everything that imports it; usually the full suite.
5. **Deleted files** -> tests that import them must now fail or be updated; select them to see which.
6. **Generated, docs-only or comment-only diffs** -> selection may be empty; the existing suite still runs.

The heuristics do not trace dynamic imports, dependency injection, reflection, HTTP calls
between services or front-end bundles. Say so when the change touches such seams.

## 2. History-based (earlier runs)

Failing results in earlier runs (FAILED, ERROR, INCONCLUSIVE), most frequent first:

```bash
python3 - <<'EOF'
import glob, json, os
from collections import defaultdict
seen = defaultdict(list)
for p in glob.glob(".qa-superteam/runs/*/executions/*.json"):
    ex = json.load(open(p, encoding="utf-8"))
    for r in ex["results"]:
        if r["status"] in ("FAILED", "ERROR", "INCONCLUSIVE"):
            seen[r["identifier"]].append((ex["started_at"], ex["run_id"], r["status"]))
for ident, hits in sorted(seen.items(), key=lambda kv: -len(kv[1])):
    path = ident.split("::")[0]
    if path.startswith(".qa-superteam/") or not os.path.exists(path):
        continue  # old probes and deleted tests are not regression candidates
    last = max(hits)
    print(f"{len(hits)}x {ident}  last: {last[1]} {last[2]}")
EOF
```

Findings of earlier runs, with their derived status, test identifiers and regression tests:

```bash
for r in $(qast run list); do qast finding list --run "$r" --json; done
```

(`qast run list` prints `no runs` when there are none.) Select: tests that failed in any
of the last 5 runs and still exist; tests named in findings whose status is CONFIRMED,
REPRODUCED or INCONCLUSIVE. Exclude the current run. Identifiers under `.qa-superteam/`
are old probes, not tests.

## 3. Defect-based

For every CONFIRMED finding in earlier runs: its `regression_test` if set, else its
`test_identifiers`. Also any test whose name or docstring carries a finding id
(`grep -rln "F-[0-9a-f]\{8\}" <test dirs>`). These tests are cheap and protect against
the most expensive kind of regression: a fixed bug coming back.

## 4. Merge and order

1. Union of all sources; one row per test with every reason that selected it.
2. Order: changed tests and defect tests -> change-selected (highest risk signal first) -> history (most frequent failures first).
3. Run them as one or a few executions with `--group regression` and a `--label` naming the source (`regression/change`, `regression/history`, `regression/defects`).
4. Then the full existing suite with `--group existing-suite`.

## 5. Plan cases (when the run feeds `qast gate`)

```json
{
  "id": "TC-R-03",
  "title": "Regression: invoice total rounding (history: failed in 2 of last 5 runs)",
  "level": "api",
  "technique": "regression",
  "oracle": "Existing assertions of the test; requirement section cited in the test",
  "origin": "existing",
  "test_ref": "tests/test_invoices.py::test_total_rounds_half_up",
  "groups": ["regression"],
  "priority": "medium",
  "risk_ids": []
}
```

Planned `regression` cases are mandatory for the gate: each must execute and pass. Plan
only tests expected to pass. Red tests for still-open defects stay attached to their
findings and run unplanned with `--group regression`.

## What selection must never do

- Replace the full existing suite.
- Drop a test because it is slow, flaky or "unrelated" - flaky handling is a human quarantine decision.
- Count a selected test that did not execute (BLOCKED, NOT_RUN, deselected) as covered.
