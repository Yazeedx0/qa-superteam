# Design decisions

Short records of the choices that shape QA Superteam, with the alternatives rejected.

## 1. Skills-first, with a deterministic core
Methodology lives in skills; anything that must be reliable lives in `qast`. An LLM that
"decides" whether tests passed or whether a release is safe is exactly the failure mode
this project exists to prevent. *Rejected:* a large orchestration backend or SaaS (heavy,
opaque, unnecessary); prompt-only frameworks (unverifiable claims).

## 2. Stdlib-only Python core
`qast` runs on any Python ≥ 3.11 with no packages, so installing the plugin never touches
the project's environment and the version works identically in CI. Consequences: models
are dataclasses with a ~250-line serializer/validator/JSON-Schema generator (`serde.py`)
instead of pydantic; configuration and policies are TOML (`tomllib`) rather than YAML.
The optional LLM judge lazily imports the official `anthropic` SDK and is NOT_RUN without it.

## 3. Write-once records, derived status
Specialists must not overwrite each other. Rather than locking, records are immutable and
status is computed from them (finding status from reproductions/verifications; "stale
decision" from digests). This also makes the audit trail complete by construction.

## 4. Verification gates in code
"Independent verification" is enforced by `qast verify`: different verifier, execution-
based method, the verifier's own failing execution, intact evidence, non-flaky
reproduction. Prose rules alone were judged too easy to rationalize around.

## 5. Seven statuses, conservative derivation
Collapsing outcomes into pass/fail hides the cases that matter most (blocked environments,
skipped mandatory checks, flaky results). Exit-code/result disagreement is INCONCLUSIVE.

## 6. Adapters wrap mature tools
pytest, Playwright, Vitest/Jest, k6, axe-core and the scanners already do their jobs well.
Adapters only run them safely and parse their machine-readable output. The one helper we
ship for pytest (`pytest_reporter.py`) exists because JUnit XML loses node ids and the
setup-vs-call distinction needed to separate ERROR from FAILED.

## 7. Main thread as QA Lead; specialists cannot delegate
Claude Code lets subagents spawn subagents. Only `qa-lead` gets the Agent tool, so
delegation is one level deep and cannot recurse. Specialists communicate through the run
store and a fixed HANDOFF block, not through conversation.

## 8. Guard hook that only asks
A plugin hook that silently blocks or allows would fight the user's own permission model.
The hook adds a prompt with a reason during QA runs and is inert otherwise.

## 9. Ground truth outside the fixtures
`examples/*` contain only what a real project would have. Answer keys, reference tests and
fix patches live in `evals/ground_truth/` and are never copied into eval sandboxes. Each
fixture has an oracle script proving every planted defect is real (fails before the fix
patch, passes after).

## 10. Attribution
The skill-library architecture is inspired by obra/superpowers (MIT): composable skills
with sharp activation criteria, small SKILL.md plus `references/`, subagent delegation,
and "evidence before claims". Adaptations: superpowers tests skills with pressure
scenarios; QA Superteam turns that into a scenario JSON format with deterministic graders,
baseline-vs-plugin conditions and ground-truth defect matching. Superpowers' skill-size
check (SKILL.md under ~20 KB because of compaction truncation) is mirrored in
`scripts/validate_plugin.py`. No Superpowers text or code is copied.
