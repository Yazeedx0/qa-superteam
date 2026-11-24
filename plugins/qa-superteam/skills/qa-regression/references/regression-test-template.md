# Regression test for a confirmed finding

A regression test is the durable part of a defect: it fails while the defect exists,
passes once it is fixed, and fails again if the defect returns. Write one only with
`permissions.write_tests = true`, only under `permissions.test_dir`, in the project's
existing framework. Otherwise put the same content in the summary as a proposal (path,
code, oracle).

## Template (pytest; adapt to the project's runner)

```python
# <test_dir>/test_regression_<area>.py
"""Regression tests for confirmed QA findings. Each test names its finding id."""
import csv
import io

from reports.export import to_csv  # the project's real entry point, same as the failing test used


def test_f_1a2b3c4d_csv_export_keeps_commas_in_one_column():
    """F-1a2b3c4d (run <run id>): a name containing a comma must stay in one CSV column.

    Requirement: EXPORT-2 "fields containing commas, quotes or newlines are quoted (RFC 4180)".
    Oracle: parsing the export with the csv module returns the original name.
    Fails while F-1a2b3c4d is open; passes after the fix. The expected value comes from
    the requirement, never from the current output.
    """
    rows = [{"name": "Doe, Jane", "total": 5}]

    parsed = list(csv.reader(io.StringIO(to_csv(rows))))

    assert parsed[1][0] == "Doe, Jane", "F-1a2b3c4d: comma split the name column"
```

## Rules

| Rule | Why |
|---|---|
| Name and docstring carry the finding id, requirement and oracle | History-based selection finds it (`grep F-<id>`); a future reader knows what not to "simplify". |
| Assert the **required** behaviour, from the requirement source | A test that asserts today's buggy output is a golden master of the bug. |
| One finding, one behaviour, minimal input from the investigation | It fails for exactly one reason; the failure message points at the defect. |
| Lowest layer that shows the defect; add one test at the user-facing boundary (API/UI) only if the defect was seen there and the lower test would miss wiring | Fast, stable, and still catches the real symptom. |
| Deterministic: seeded randomness, injected or fixed clock, own temp data, no `sleep`, no network | A flaky regression test is worse than none. |
| Independent: own data and fixtures (project fixtures from `conftest.py` are fine if `test_dir` is inside their scope) | Runs alone, in any order. |
| No new dependencies, no new framework | Uses what the project already has. |
| No `skip`/`xfail` markers | A red test is the honest state. Marking it expected-to-fail until the fix lands is a team (quarantine) decision. |

## Proving red now

```bash
qast exec pytest --group regression --label "regression/F-1a2b3c4d" -- <test_dir>/test_regression_<area>.py::test_f_1a2b3c4d_csv_export_keeps_commas_in_one_column
qast reproduce --test <test_dir>/test_regression_<area>.py::test_f_1a2b3c4d_csv_export_keeps_commas_in_one_column --times 3
```

| Result | Meaning | Action |
|---|---|---|
| FAILED, message matches the finding's actual, reproduction `consistent` | Correct regression test | Report "red now in ex-...; expected green after the fix". |
| ERROR (import error, fixture error, typo) | The test is broken, not red | Fix the test; it does not count yet. |
| PASSED | The test does not capture the defect (or the defect is gone) | Rework the input/oracle from the finding; if it still passes, tell `qa-verification` the defect may not reproduce. |
| `intermittent` | Nondeterministic test or product race | Make it deterministic before keeping it (`qa-bug-investigation` flakiness triage). |

This test was added in this run, so keep it out of the `existing-suite` execution
(pytest `--ignore=<file>`): its red result belongs to the finding, not to a new suite
failure. Once the team commits it, it becomes part of the existing suite.

## Linking test and finding

Findings are write-once. If the finding is recorded after the test exists, set its
`regression_test` field to the test identifier. Otherwise report the mapping in the
summary: `F-1a2b3c4d -> <test id> (red in ex-...)`.

## Never

- Edit or loosen an existing assertion, tolerance or snapshot to make anything pass.
- Delete, rename or move existing tests.
- Write the test so it passes against the current (defective) behaviour.
- Mark the test skipped or expected-to-fail on your own decision.
