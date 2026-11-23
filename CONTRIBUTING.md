# Contributing

Thanks for helping make AI-assisted QA trustworthy. Contributions are judged by one
question: *does this make QA results more correct, more evidenced, or safer?*

## Ground rules
- **Evidence over prose.** If a rule can be enforced in `qast`, enforce it in code and test it.
- **No fabricated results** anywhere: docs, sample reports and eval outputs must come from real runs.
  If something could not be run, say so (NOT_RUN / BLOCKED) instead of filling it in.
- **Stdlib-only core.** `src/qa_superteam` must not gain runtime dependencies.
- **Wrap tools, don't rebuild them.** Adapters parse machine-readable output of existing tools.

## Setup
```bash
python3 -m pip install -e ".[dev]"
(cd tests/integration/node_project && npm ci)    # optional: node runner integration tests
(cd examples/web-checkout && npm ci)             # optional: axe-core for browser fixtures
python3 -m playwright install chromium           # optional: browser tests
```

## Before opening a PR
```bash
python3 -m pytest tests/unit -q
python3 -m pytest tests/integration -q -rs     # skips are listed with reasons
python3 scripts/gen_schemas.py --check
python3 scripts/sync_skill_runtime.py --check   # run without --check after changing src/, policies/, docs/policy.md or docs/risk-model.md
python3 scripts/validate_plugin.py
ruff check src scripts evals/harness tests hooks
claude plugin validate . --strict               # if Claude Code is installed
```

## Changing skills
Follow [docs/skill-authoring.md](docs/skill-authoring.md). Add or update scenarios in
`evals/scenarios/<skill>.json`. If you have credentials, run a before/after comparison:
`python3 evals/harness/run_evals.py --live --only <skill> --conditions plugin,baseline` and
include the metrics in the PR.

## Changing fixtures
Planted defects must stay realistic and undocumented inside `examples/`. Update
`evals/ground_truth/<fixture>/` (ground_truth.json, reference tests, fix patches) and make
`verify_oracle.sh` pass.

## Versioning and releases
SemVer. Breaking changes to skill names, `qast` commands/flags, record schemas, policy keys
or exit codes require a major version bump (minor while < 1.0) and a CHANGELOG entry.
Keep `version` identical in `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`,
`.codex-plugin/plugin.json`, `.cursor-plugin/plugin.json`, `gemini-extension.json`, `pyproject.toml`
and `src/qa_superteam/__init__.py` (CI checks this).
