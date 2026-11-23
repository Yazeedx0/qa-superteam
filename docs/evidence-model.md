# Evidence model

QA Superteam never states a result it did not observe. This document defines what each
recorded state means and where every number in a report comes from.

## Execution statuses

| Status | Meaning | Example |
|---|---|---|
| `PASSED` | The test ran and its oracle held | pytest call phase passed |
| `FAILED` | The test ran and the product violated the oracle | assertion error |
| `ERROR` | The test or tooling broke; nothing was learned about the product | fixture crash, collection error, timeout |
| `SKIPPED` | The test framework deliberately skipped it | `@pytest.mark.skip`, `xfail` |
| `BLOCKED` | It could not run | tool not installed, target not authorized, missing environment |
| `NOT_RUN` | Planned but never attempted, or nothing was collected | pytest exit code 5 |
| `INCONCLUSIVE` | It ran, but the outcome cannot be trusted | flaky retry, disagreeing samples, axe "incomplete", uncalibrated judge, exit code contradicting results |

The execution's overall status comes from its results *and* the process outcome
(`adapters/base.py: derive_status`):

- A timeout is always `ERROR`.
- Exit code 0 with no machine-readable results is `INCONCLUSIVE`.
- Results that all passed but a failing exit code is `INCONCLUSIVE`.
- An execution where every test was skipped is `SKIPPED`, not `PASSED`.

## Findings

A `DefectFinding` must have:

- reproduction steps;
- expected *and* actual behavior;
- references to the executions and artifacts that show it, which `qast finding add`
  refuses to accept if they do not exist.

Its status is derived, never edited (`findings.py: effective_status`):

```
SUSPECTED ──(failing execution linked)──▶ REPRODUCED ──(qast verify CONFIRMED)──▶ CONFIRMED
    │                                         │
    │                (qast reproduce)         ├─ intermittent ──▶ INCONCLUSIVE
    │                                         └─ all attempts pass ──▶ NOT_REPRODUCED
    └──(qast verify REJECTED)──▶ REJECTED        (qast verify INCONCLUSIVE ──▶ INCONCLUSIVE)
```

`CONFIRMED` requires every one of the following, checked by `qast verify` and re-checked
on every read:

1. The verifier is not the reporter.
2. The method is `independent-rerun` or `alternate-oracle`. `code-inspection` and `manual`
   can never confirm a defect.
3. An execution run by the verifier contains a `FAILED` result for the finding's tests, or
   for the verifier's own alternate-oracle tests.
4. All referenced evidence exists and its sha256 still matches.
5. Reproduction, when it was attempted, is consistent, not intermittent.

If evidence is later modified, a `CONFIRMED` finding degrades to `INCONCLUSIVE` with an
integrity warning.

Root-cause **hypotheses** are stored separately from facts. A hypothesis can be marked
`confirmed` only with evidence ids.

## Confidence and basis

Facts carry a **basis**: `observed` (read from a file or tool output), `inferred` (derived by
a documented heuristic) or `assumed`. **Confidence** is ordinal and never a percentage:

| Source | Basis / confidence |
|---|---|
| Declared in a manifest, config, CI file or spec | observed / high |
| Source-code pattern (import, decorator, call) | inferred / medium |
| File or directory name only | inferred / low |

Risk scores are `probability × impact` on documented 1–5 scales, with every factor's
rationale recorded ([risk-model.md](risk-model.md)).

## Numbers in reports

| Number | Source |
|---|---|
| Status counts | Recorded results of primary executions (reproduction attempts excluded) |
| Coverage % | Only from coverage tool output recorded as an artifact (coverage.py JSON, istanbul json-summary). Otherwise the report says no coverage was measured |
| AI eval pass rate | PASSED / (PASSED + FAILED) over decided cases; NOT_RUN and INCONCLUSIVE are listed separately |
| Token usage | From the system under test when reported; otherwise a whitespace-token estimate, labeled "estimated" |
| Judge agreement | Cohen's kappa against human labels (`qast ai-eval calibrate`) |
| Latency | Measured wall-clock time around the call under test or from the tool (k6) |

## Evidence integrity

- Every artifact is written under `artifacts/` with an `EvidenceArtifact` record holding
  its sha256 and size.
- Text artifacts are redacted *before* hashing, so the stored hash covers the stored bytes.
- `qast validate` re-validates every record against its schema and every artifact against
  its hash.
- The decision stores an `inputs_digest` over the evidence it used. The report flags the
  decision as stale if evidence changed afterwards.
