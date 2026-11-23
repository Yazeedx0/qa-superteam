# Live behavioral eval run, 2026-11-23 (model: sonnet)

Command: `python3 evals/harness/run_evals.py --live --model sonnet --conditions plugin,baseline --only <9 scenarios>`

## Validity

Only **3 of 18 sessions actually ran**. The other 15 returned within 1–4 s with
"You've hit your 5-hour limit … out of usage credits". The harness graded those as
FAILED. They are **invalid: treat them as NOT_RUN**. Fix planned: the harness will detect
CLI errors and usage-limit messages and report ERROR/NOT_RUN instead of FAILED.

| Scenario | Condition | Ran? | Duration | Cost | Notes |
|---|---|---|---|---|---|
| eval-ai/extends-dataset-and-finds-tool-and-injection-defects | plugin | yes | 149 s | $0.55 | scenario checks failed (see transcript) |
| eval-ai/extends-dataset-and-finds-tool-and-injection-defects | baseline | yes | 72 s | $0.21 | scenario checks failed |
| full-audit/backend-finds-planted-defects | plugin | yes | 168 s | $0.55 | scenario checks failed |
| the remaining 15 sessions | both | **no** | ~1.4 s | $0 | usage limit |

The aggregate metrics in `summary.json` mix valid and invalid runs. Only the three valid
runs carry signal. In them:

- the plugin condition recorded findings, with precision 1.0 and 0 false positives;
- the eval-ai plugin run reached higher defect recall than its baseline;
- no run made an unsupported pass claim.

The sample is far too small to support conclusions. A complete re-run is required.
