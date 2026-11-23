# Measuring coverage with real tools

A coverage number is a measurement. It exists only when a coverage tool produced it
inside a recorded `qast exec` execution. QA Superteam never estimates, extrapolates or
"eyeballs" coverage.

## How qast picks coverage up

`qast exec` gives the tool process three environment variables:

| Variable | Meaning |
|---|---|
| `QAST_ARTIFACT_DIR` | Files written here are hashed, stored as evidence and linked to the execution |
| `QAST_WORK_DIR` | Scratch directory for this execution; deleted afterwards |
| `QAST_RUN_ID` | Active run id |

`qast report` turns an artifact into a "measured" metric when its file name contains
`coverage`, ends in `.json`, and is either coverage.py JSON (`totals.percent_covered`) or
an istanbul `json-summary` (`total.lines.pct`).

`qast exec` runs argv lists, never a shell. `$QAST_ARTIFACT_DIR` typed on your command
line is expanded by *your* shell, where it is empty. Put the path where the tool itself
expands it: a coverage.py config file (coverage.py substitutes `${VAR}` in config
values) or an explicit `sh -c '...'` executed by the `command` adapter.

## Python: pytest-cov present (preferred, keeps per-test results)

Write `.qa-superteam/coveragerc` (inside the git-ignored output directory, so the project
tree is untouched):

```ini
[run]
branch = True
# Keep the .coverage data file out of the project tree.
data_file = ${QAST_WORK_DIR?}/.coverage
# The package(s) under test, as import names or paths; copy `source`/`omit`
# from the project's own [tool.coverage] / .coveragerc if it has one.
source = mypackage

[json]
# The trailing ? makes coverage fail loudly if run outside qast.
output = ${QAST_ARTIFACT_DIR?}/coverage.json

[report]
show_missing = True
skip_covered = True
```

Run:

```bash
qast exec pytest --group existing-suite --label unit-coverage -- \
  --cov --cov-config=.qa-superteam/coveragerc \
  --cov-report=json --cov-report=term-missing tests
```

- `--cov` with no value uses `source` from the rc file.
- `--cov-report=json` with no destination writes to the rc file's `[json] output`.
- `--cov-config` replaces the project's coverage configuration for this run; carry over
  its `omit` patterns so the numbers are comparable with the team's own.
- If the project's pytest `addopts` already contains `--cov` options, check the
  recorded command line: duplicated options can send reports elsewhere.

## Python: coverage.py present, pytest-cov missing

Two executions; the data file must outlive the first one, so keep it under
`.qa-superteam/`:

```ini
# .qa-superteam/coveragerc
[run]
branch = True
data_file = .qa-superteam/coverage-data/.coverage
source = mypackage

[json]
output = ${QAST_ARTIFACT_DIR?}/coverage.json
```

```bash
mkdir -p .qa-superteam/coverage-data .qa-superteam/tmp
qast exec junit --group existing-suite --label unit-coverage-run \
  --report .qa-superteam/tmp/junit.xml -- \
  python3 -m coverage run --rcfile=.qa-superteam/coveragerc -m pytest \
  -p no:cacheprovider --junitxml=.qa-superteam/tmp/junit.xml tests
qast exec command --label coverage-json -- \
  python3 -m coverage json --rcfile=.qa-superteam/coveragerc
qast exec command --label coverage-report -- \
  python3 -m coverage report --rcfile=.qa-superteam/coveragerc --show-missing
```

Use the project interpreter (`.venv/bin/python` if it exists) instead of `python3`.
Results of the first execution come from JUnit XML, so test identifiers look like
`tests.test_x::test_y` rather than pytest node ids.

## JavaScript: vitest

Needs `@vitest/coverage-v8` (or `-istanbul`) already installed; otherwise coverage is
BLOCKED, never estimated.

```bash
qast exec vitest --group existing-suite --label unit-coverage -- \
  --coverage.enabled --coverage.provider=v8 \
  --coverage.reporter=json-summary --coverage.reporter=text \
  --coverage.reportsDirectory=.qa-superteam/coverage-js
qast exec command --label coverage-evidence -- \
  sh -c 'cp .qa-superteam/coverage-js/coverage-summary.json "$QAST_ARTIFACT_DIR/coverage-summary.json"'
```

## JavaScript: jest

```bash
qast exec jest --group existing-suite --label unit-coverage -- \
  --coverage --coverageReporters=json-summary --coverageReporters=text \
  --coverageDirectory=.qa-superteam/coverage-js
qast exec command --label coverage-evidence -- \
  sh -c 'cp .qa-superteam/coverage-js/coverage-summary.json "$QAST_ARTIFACT_DIR/coverage-summary.json"'
```

The copy step is recorded (command, exit code, hashed file), so the provenance of the
number stays visible in the report.

## Go

```bash
mkdir -p .qa-superteam/tmp
# per-test results, if gotestsum is installed:
qast exec junit --group existing-suite --label go-test-cover \
  --report .qa-superteam/tmp/go-junit.xml -- \
  gotestsum --junitfile .qa-superteam/tmp/go-junit.xml -- \
  -covermode=atomic -coverprofile=.qa-superteam/tmp/cover.out ./...
# without gotestsum: qast exec command --label "go test" -- go test -covermode=atomic -coverprofile=.qa-superteam/tmp/cover.out ./...
qast exec command --label go-cover-func -- go tool cover -func=.qa-superteam/tmp/cover.out
```

qast does not parse Go profiles into a metric; quote the `total:` line from the
`go-cover-func` log and cite its evidence id.

## Quoting a number truthfully

1. Run `qast report` and read "Coverage & traceability". If a metric is listed, quote it
   with the tool and evidence id.
2. If the report says no coverage was recorded although a `coverage*.json` artifact is in
   the evidence list, the stored file did not parse. Do not patch the artifact (evidence
   is write-once). Quote the `TOTAL` line from the recorded execution log (the
   `term-missing` / `text` reporter output), cite that log's evidence id, and add
   `qast run note --kind limitation "coverage JSON not parseable by qast report; figure quoted from the tool's log ev-..."`.
3. Say what the number is. coverage.py with `branch = True` reports a combined
   statement+branch percentage; istanbul `lines.pct` is lines only.
4. Never round up, never average across tools, never present a per-file number as the
   project figure.

## Reading coverage for gaps (not for a score)

- Start from the units chosen by risk. For each, list missing lines and partial branches
  (`term-missing` shows `12->15` for a branch never taken).
- Translate each gap into a behaviour: "branch `amount > limit` never false", "the
  `except ValueError` path never runs". Ask whether a user-visible failure hides there.
- Covered is not tested: a line executed by a test that asserts nothing about its effect
  is a gap. Combine with `mutation-thinking.md`.
- High coverage next to serious defects is normal: boundary (`>` vs `>=`), rounding
  direction and case-normalisation bugs live on lines that every happy-path test executes.
