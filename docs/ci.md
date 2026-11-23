# CI/CD integration

There are two separate concerns:

1. **This repository's CI** validates the framework itself
   ([`.github/workflows/ci.yml`](../.github/workflows/ci.yml)): schemas, plugin structure,
   unit and integration tests with real tools, fixture oracles, and sample reports
   generated from real runs, published as artifacts. It needs no LLM.
2. **Running QA Superteam on your project in CI.** Markdown skills do not run themselves.
   You need either a Claude Code runtime (agentic review) or plain `qast` commands
   (deterministic gating). They combine well.

## A. Deterministic gate (no LLM, no credentials)

Run your existing suites through `qast` so you get normalized evidence, a policy decision
and a report on every PR:

```yaml
- uses: actions/checkout@v4
- uses: actions/setup-python@v5
  with: { python-version: "3.12" }
- run: pip install -r requirements.txt pytest
- run: git clone --depth 1 https://github.com/Yazeedx0/qa-superteam /tmp/qa-superteam
- name: QA gate
  run: |
    export PATH=/tmp/qa-superteam/bin:$PATH
    qast run start --mode release-check --scope "CI ${GITHUB_SHA::8}"
    qast exec pytest --group existing-suite -- tests
    qast gate --exit-code; status=$?
    qast report
    exit $status            # 0 PASS, 10 REVIEW_REQUIRED, 20 BLOCK
- uses: actions/upload-artifact@v4
  if: always()
  with: { name: qa-report, path: .qa-superteam/runs/ }
```

To let REVIEW_REQUIRED pass the job but annotate the PR, map exit code 10 to a warning in
your script.

## B. Agentic PR review (Claude Code in CI)

[`docs/examples/qa-pr-review.yml`](examples/qa-pr-review.yml) installs Claude Code, adds
this plugin from its marketplace, runs `/qa-superteam:review-pr origin/<base>` headless
with a tool allowlist, then enforces the gate with `qast gate --exit-code` and uploads the
report. It requires an `ANTHROPIC_API_KEY` secret. Treat the run as you would any
automation with shell access: run it in an ephemeral runner, and do not expose deployment
credentials to that job.

Notes:

- Use a tool allowlist (`--allowedTools`) rather than `--dangerously-skip-permissions`.
- Keep `.qa-superteam/config.toml` in the repo so CI and local runs share permissions and
  policy.
- Post the report summary as a PR comment yourself (for example with `gh pr comment
  --body-file`). The skills never post comments unless asked.

## Behavioral evals in CI

[`.github/workflows/behavioral-evals.yml`](../.github/workflows/behavioral-evals.yml) is
`workflow_dispatch`-only. With the `ANTHROPIC_API_KEY` secret set, it runs
`evals/harness/run_evals.py --live --bare` for selected skills and uploads the metrics.
Without the secret, it runs the harness in dry mode and every scenario is reported as
`NOT_RUN`.
