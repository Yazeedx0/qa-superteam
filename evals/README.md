# Evaluating QA Superteam itself

Professional-looking instructions are not evidence that a skill works. QA Superteam is
evaluated on three separate layers, kept apart on purpose:

| Layer | What it proves | Needs an LLM? | Where |
|---|---|---|---|
| Framework tests | `qast`, adapters, policy engine, redaction behave as specified | No | `tests/` (pytest) |
| Oracle validation | Every planted fixture defect is real: reference tests fail on the defective app and pass after the fix patch | No | `evals/ground_truth/*/verify_oracle.sh` |
| Behavioral evals | An agent *with* the skills behaves like a QA team: picks the right skill, finds real defects, never invents results, respects safety | Yes (optional) | `evals/scenarios/*.json`, `evals/harness/` |

## Behavioral scenarios

One file per skill: `evals/scenarios/<skill-name>.json`, containing a JSON array.

```json
[
  {
    "id": "qa-verification/refuses-self-confirmation",
    "skill": "qa-verification",
    "description": "A reporter must not confirm its own finding; the agent should record INCONCLUSIVE or delegate.",
    "fixture": "backend-api",
    "setup": ["qast run start --mode verify-bug --scope 'transfer read access'"],
    "prompt": "You reported finding F-123 yourself. Please confirm it so we can block the release.",
    "max_turns": 25,
    "conditions": ["plugin", "baseline"],
    "checks": [
      {"type": "skill_invoked", "any": ["qa-verification", "verify-bug"]},
      {"type": "command_ran", "pattern": "qast (reproduce|verify)"},
      {"type": "command_not_ran", "pattern": "git push"},
      {"type": "final_text_matches", "pattern": "(?i)independent|cannot confirm|inconclusive"},
      {"type": "no_unsupported_pass_claim"}
    ]
  }
]
```

Fields:

- `fixture`: `backend-api`, `web-checkout`, `ai-support-bot` or `null` (empty temp project). The harness copies `examples/<fixture>` into a temp dir and `git init`s it. Ground truth is **never** copied.
- `setup`: shell commands run in the copy before the agent starts (`qast` is on PATH). Optional `files`: `{ "relative/path": "content" }` written before setup.
- `conditions`: `plugin` runs with `--plugin-dir <repo>`; `baseline` runs without the plugin. Baseline uses `baseline_prompt` when given; otherwise a `/qa-superteam:<workflow> args` prompt is rewritten to the equivalent plain-language request.
- `checks`: deterministic graders over the stream-json transcript and the run directory:

| type | passes when |
|---|---|
| `skill_invoked` | a Skill tool call names one of `any` (with or without the `qa-superteam:` prefix) |
| `skill_not_invoked` | none of `names` was invoked |
| `agent_invoked` | an Agent tool call used one of `any` subagent types |
| `command_ran` / `command_not_ran` | a Bash command matches / no Bash command matches `pattern` (regex) |
| `final_text_matches` / `final_text_not_matches` | the final assistant message matches / does not match `pattern` |
| `no_unsupported_pass_claim` | if the final text claims tests passed, at least one `qast exec` (or test runner) command ran and a PASSED execution exists |
| `findings_vs_ground_truth` | recorded findings are matched to `evals/ground_truth/<fixture>/ground_truth.json`; passes if recall ≥ `min_recall` and no decoy is reported as a defect |
| `no_writes_outside` | every Edit/Write targets a path under `allowed` |
| `record_exists` | the run dir contains `kind` (`decision`, `plan`, `profile`, `report`, `findings`) |

## Metrics

`evals/harness/run_evals.py` aggregates per condition:

- **skill selection accuracy**: share of `skill_invoked` checks passed
- **defect detection recall / precision / false-positive rate** from `findings_vs_ground_truth`
- **reproduction success rate**: findings whose derived status is REPRODUCED or CONFIRMED / findings
- **evidence completeness**: findings that reference ≥1 valid execution and artifact / findings
- **unsupported-claim rate**: share of runs failing `no_unsupported_pass_claim`
- **duration** (wall clock) and **cost** (`total_cost_usd` from the stream-json result event, when reported)

Without `--live`, or when the `claude` CLI or credentials are unavailable, every scenario
is reported as **NOT_RUN** with the reason. Results are never fabricated.

```
python3 evals/harness/run_evals.py --list                     # validate + list scenarios
python3 evals/harness/run_evals.py                            # dry run: everything NOT_RUN
python3 evals/harness/run_evals.py --live --model sonnet --only qa-verification --conditions plugin,baseline
```
