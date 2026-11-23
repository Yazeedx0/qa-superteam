# Behavioral eval results

`python3 evals/harness/run_evals.py` writes one directory per invocation here
(`<timestamp>/summary.json` plus one stream-json transcript per scenario and condition).
These directories are git-ignored: transcripts can contain environment details.

Curated, sanitized summaries of live runs that are referenced from the docs are committed
under `evals/reports/`.
