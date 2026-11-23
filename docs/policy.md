# Release policy and the deterministic gate

`qast gate` turns the evidence recorded in a QA run into one of three decisions:
**PASS**, **REVIEW_REQUIRED** or **BLOCK**. The decision is computed by
`evaluate(policy, inputs)` in `src/qa_superteam/policy.py`, a pure function: no model
is consulted, and the same policy file plus the same records always give the same
decision and the same `inputs_digest`.

## How the gate decides

- **Inputs** (all from the run directory): executions, findings with their *derived*
  status (`SUSPECTED`, `REPRODUCED`, `NOT_REPRODUCED`, `INCONCLUSIVE`, `CONFIRMED`,
  `REJECTED`), `plan.json`, `risks.json`, and evidence integrity (sha256 of every
  artifact). `requirements.json` is not an input; requirements and invariants reach the
  gate only through plan test cases.
- **Primary executions** are executions not created by `qast reproduce`. Reproduction
  attempts re-run single tests on purpose and are excluded from every rule except
  `R-FLAKY-CRITICAL`.
- **Group membership** comes only from `--group` tags given to `qast exec`. The
  `[groups]` table in `.qa-superteam/config.toml` is documentation for planning; the gate
  does not read it.
- Each rule yields an outcome. **Decision = the most severe triggered outcome**
  (BLOCK > REVIEW_REQUIRED > PASS).
- **PASS needs positive evidence.** If no rule triggers but no mandatory group passed
  and no planned mandatory case passed, `R-POSITIVE-EVIDENCE` makes the decision
  REVIEW_REQUIRED. Skipped, blocked or not-run checks are never treated as passed.
- The result is written to `decision.json` (replaced on every gate run) with the policy
  name, version, the policy file's sha256 and the `inputs_digest`. `qast report` recomputes
  the digest and flags the decision as stale if evidence changed after the gate ran.
- `qast gate --exit-code` exits `0` PASS, `10` REVIEW_REQUIRED, `20` BLOCK. Without the
  flag it exits 0 whenever a decision was computed; a policy error exits 1 and produces
  no decision.

## Selecting a policy

| Where | Effect |
|---|---|
| nothing configured | the plugin's `policies/default.toml` |
| `.qa-superteam/config.toml` → `[policy] path = "..."` | a relative path is resolved against the project root first, then against the plugin root, so `"policies/strict.toml"` works without copying the file |
| `qast gate --policy FILE` | overrides config for this evaluation; the path is resolved relative to the current directory (use `"${CLAUDE_PLUGIN_ROOT}/policies/strict.toml"` for the bundled strict policy) |

Bundled policies:

- `default.toml` — balanced: confirmed critical defects (high for security and
  data-integrity) block; uncertainty, missing evidence and errors need human review.
- `strict.toml` — for regulated or high-stakes releases (payments, health, identity):
  confirmed high defects block in every category (medium for security and
  data-integrity), and any uncertainty about a mandatory check blocks.

## Rules

Rules are evaluated in the order below. `[g]` stands for each group in
`[groups] mandatory`.

### R-EVIDENCE-EXISTS

- **Checks:** at least one primary execution exists in the run.
- **Outcome when triggered:** `[evidence] no_executions` (default REVIEW_REQUIRED, strict BLOCK).
- **Reason text:** "no test executions recorded" or the execution count.

### R-EVIDENCE-INTEGRITY

- **Checks:** every recorded artifact file exists and matches its sha256, and every
  execution and artifact referenced by a finding (or by the finding's latest
  verification) exists and is intact. `qast validate` shows the same problems in detail.
- **Outcome:** `[evidence] integrity_violation` (default REVIEW_REQUIRED, strict BLOCK).
- A CONFIRMED verification whose evidence fails integrity makes the finding
  INCONCLUSIVE, so it cannot block or pass on tampered evidence.

### R-CONFIRMED-BLOCKING

- **Checks:** findings whose derived status is `CONFIRMED` and whose severity is at or
  above the `block_at` threshold for the finding's category (falling back to the
  `default` key).
- **Outcome:** always **BLOCK** (not configurable; only the thresholds are).
- **Refs:** the blocking finding ids.
- There is no way to stop a confirmed finding at or above its threshold from blocking:
  the highest threshold is `critical`.

### R-CONFIRMED-REVIEW

- **Checks:** `CONFIRMED` findings that do not block but are at or above the `review_at`
  threshold for their category.
- **Outcome:** always **REVIEW_REQUIRED**. **Refs:** finding ids.

### R-UNVERIFIED-HIGH-IMPACT

- **Checks:** findings with severity ≥ `[findings] unverified_review_at` whose derived
  status is `SUSPECTED`, `REPRODUCED`, `NOT_REPRODUCED` or `INCONCLUSIVE` (anything not
  yet confirmed or rejected by independent verification).
- **Outcome:** always **REVIEW_REQUIRED**. **Refs:** finding ids.
- An intermittent `qast reproduce` result makes a finding INCONCLUSIVE, which lands
  here.

### R-MANDATORY-GROUP:[g]

One rule per mandatory group. Evaluated over all primary executions tagged `[g]` in the
run; the first matching condition wins:

| Condition | Outcome key |
|---|---|
| no execution tagged `[g]` | `on_missing` |
| an execution is BLOCKED and the group produced no results | `on_missing` |
| any FAILED result | `on_fail` |
| any ERROR result, or an ERROR execution without results | `on_error` |
| any INCONCLUSIVE result, or an INCONCLUSIVE execution without results | `on_inconclusive` |
| no PASSED result at all | `on_missing` |
| SKIPPED + NOT_RUN + BLOCKED results > `max_skipped_in_mandatory` | `on_missing` |
| otherwise | satisfied; counts as positive evidence |

- **Every execution counts.** Executions are write-once, so a later passing run of the
  group does not erase an earlier FAILED, ERROR, INCONCLUSIVE or SKIPPED result in the
  same run. After the build or environment changes, start a new run
  (`qast run start`); a run describes one build. A BLOCKED execution with no results is
  ignored once another execution of the group produced results (e.g. after installing
  the missing tool).
- **Refs:** up to 20 failing / errored / inconclusive / skipped test identifiers.

### R-PLANNED-MANDATORY-CASES

Evaluated only when `plan.json` exists.

- **Checks:** every plan test case whose `groups` intersect
  `[groups] mandatory_if_planned`. For each, the latest status of its `test_ref` across
  primary executions: a result matches when its identifier equals the `test_ref` or
  starts with `test_ref` followed by `::`, `/` or `[`; within one execution the worst
  status wins (FAILED > ERROR > INCONCLUSIVE > BLOCKED > NOT_RUN > SKIPPED > PASSED);
  a later execution supersedes an earlier one.
- **Outcomes:** any case FAILED → `on_fail`. Otherwise, any case without `test_ref`,
  not executed, SKIPPED, NOT_RUN or BLOCKED → `on_missing`; only ERROR/INCONCLUSIVE
  cases → `on_error`. All passed → satisfied and counts as positive evidence.
- Proposed cases (`test_ref: null`) in these groups always count as missing.

### R-UNTRIAGED-FAILURES

- **Checks:** every FAILED or ERROR result in a primary execution, except executions of
  the candidate adapters (`bandit`, `pip-audit`, `npm-audit`, `semgrep`, `gitleaks`,
  `ai-eval`, which have their own triage and rules), must be explained by a recorded
  finding. A result counts as explained when a finding's `test_identifiers` match its
  identifier (in either direction: equal, or one is the other followed by `::`, `/` or
  `[`), or, for a finding without `test_identifiers`, when the finding's
  `execution_ids` include the execution.
- Any finding counts, whatever its derived status (a REJECTED claim still documents
  that the failure was looked at).
- **Outcome:** `[evidence] untriaged_failures` (default REVIEW_REQUIRED, strict BLOCK).
  **Refs:** up to 20 unexplained result identifiers.
- Purpose: a red test that nobody triaged cannot be waved through as noise. Failures
  outside mandatory groups are caught here too.

### R-FLAKY-CRITICAL

- **Checks:** INCONCLUSIVE results in any `[groups] critical` group, across *all*
  executions including reproductions; plus findings whose recorded
  `reproduction.classification` (the field written in the finding JSON) is
  `intermittent`.
- **Outcome:** always **REVIEW_REQUIRED**. Flaky results in critical journeys or
  contracts cannot be counted as passing evidence.

### R-AI-EVAL-PASS-RATE

Evaluated only when primary `ai-eval` executions produced results.

- **Checks:** pass rate = PASSED / (PASSED + FAILED) over all `ai-eval` results of all
  primary `ai-eval` executions in the run (pooled; you cannot pick the best run).
- **Outcome:** `[ai_eval] below_threshold` when the rate is below `min_pass_rate`, or when
  no case was decided. Not triggered when `min_pass_rate` is absent.

### R-AI-EVAL-INCONCLUSIVE

Evaluated with the previous rule.

- **Checks:** `ai-eval` results that are INCONCLUSIVE (uncalibrated judge, disagreement
  across `--samples`) or ERROR.
- **Outcome:** `[ai_eval] inconclusive`.
- A BLOCKED `ai-eval` execution produces no results, so neither AI rule is evaluated;
  it appears in the report's limitations. See the customization notes below if AI evals
  must run for a release.

### R-UNTESTED-HIGH-RISK

- **Collects:** (a) plan test cases with priority `high` or `critical` whose latest
  status is not PASSED or FAILED (including proposed cases without `test_ref`);
  (b) risks in `risks.json` with level `high` or `critical` that no plan test case
  references in `risk_ids`; (c) if high/critical risks exist but no plan is recorded,
  one item saying so.
- **Triggered when** the number of items exceeds `[coverage] max_untested_high_risk`.
- **Outcome:** `[coverage] untested_high_risk` (default REVIEW_REQUIRED, strict BLOCK).
- A FAILED case counts as tested here: the failure is handled by the finding rules.

### R-POSITIVE-EVIDENCE

- **Appended only** when every other rule left the decision at PASS but no mandatory
  group was satisfied and no planned mandatory case passed.
- **Outcome:** always **REVIEW_REQUIRED**. Fix by running the mandatory suite
  (`qast exec <adapter> --group existing-suite -- ...`) or by configuring
  `[groups] mandatory`.

## Policy keys

Unknown **sections** are rejected. Unknown **keys** inside a known section are ignored
silently, so a typo (`on_fails`) leaves the default in force — check the gate output.
Decision values: `PASS`, `REVIEW_REQUIRED` (alias `REVIEW`), `BLOCK`. Severities:
`info` < `low` < `medium` < `high` < `critical`. Finding categories usable as keys in
`block_at` / `review_at`: `default`, `functional`, `security`, `data-integrity`,
`performance`, `reliability`, `accessibility`, `contract`, `ai-quality`, `usability`,
`other`.

| Key | Type | If absent | default.toml | strict.toml | Used by |
|---|---|---|---|---|---|
| `[policy] name` | string | file stem | `default` | `strict` | decision record |
| `[policy] version` | string | `"0"` | `1.0.0` | `1.0.0` | decision record |
| `[policy] description` | string | — | text | text | documentation only |
| `[severity_definitions] <severity>` | string | — | definitions | definitions | humans and agents assigning severity; not evaluated |
| `[findings] block_at` | table category → severity | `{default="critical"}` | `{default="critical", security="high", data-integrity="high"}` | `{default="high", security="medium", data-integrity="medium"}` | R-CONFIRMED-BLOCKING |
| `[findings] review_at` | table category → severity | `{default="high"}` | `{default="high", accessibility="high"}` | `{default="medium"}` | R-CONFIRMED-REVIEW |
| `[findings] unverified_review_at` | severity | `high` | `high` | `medium` | R-UNVERIFIED-HIGH-IMPACT |
| `[groups] mandatory` | list of groups | `[]` | `["existing-suite"]` | `["existing-suite"]` | R-MANDATORY-GROUP |
| `[groups] mandatory_if_planned` | list of groups | `[]` | `critical-journeys, contract, regression` | + `security, accessibility` | R-PLANNED-MANDATORY-CASES |
| `[groups] critical` | list of groups | `[]` | `critical-journeys, contract` | + `security` | R-FLAKY-CRITICAL |
| `[groups] on_fail` | decision | `BLOCK` | `BLOCK` | `BLOCK` | mandatory groups, planned cases |
| `[groups] on_missing` | decision | `REVIEW_REQUIRED` | `REVIEW_REQUIRED` | `BLOCK` | not executed, BLOCKED, no pass, too many skips |
| `[groups] on_error` | decision | `REVIEW_REQUIRED` | `REVIEW_REQUIRED` | `BLOCK` | ERROR results; planned cases with ERROR/INCONCLUSIVE |
| `[groups] on_inconclusive` | decision | `REVIEW_REQUIRED` | `REVIEW_REQUIRED` | `BLOCK` | INCONCLUSIVE results in mandatory groups |
| `[groups] max_skipped_in_mandatory` | integer | `0` | `0` | `0` | SKIPPED/NOT_RUN/BLOCKED results allowed per mandatory group |
| `[ai_eval] min_pass_rate` | float 0..1 | rule disabled | `0.9` | `0.97` | R-AI-EVAL-PASS-RATE |
| `[ai_eval] below_threshold` | decision | `BLOCK` | `BLOCK` | `BLOCK` | R-AI-EVAL-PASS-RATE |
| `[ai_eval] inconclusive` | decision | `REVIEW_REQUIRED` | `REVIEW_REQUIRED` | `BLOCK` | R-AI-EVAL-INCONCLUSIVE |
| `[coverage] untested_high_risk` | decision | `REVIEW_REQUIRED` | `REVIEW_REQUIRED` | `BLOCK` | R-UNTESTED-HIGH-RISK |
| `[coverage] max_untested_high_risk` | integer | `0` | `0` | `0` | R-UNTESTED-HIGH-RISK |
| `[evidence] no_executions` | decision | `REVIEW_REQUIRED` | `REVIEW_REQUIRED` | `BLOCK` | R-EVIDENCE-EXISTS |
| `[evidence] integrity_violation` | decision | `REVIEW_REQUIRED` | `REVIEW_REQUIRED` | `BLOCK` | R-EVIDENCE-INTEGRITY |
| `[evidence] untriaged_failures` | decision | `REVIEW_REQUIRED` | `REVIEW_REQUIRED` | `BLOCK` | R-UNTRIAGED-FAILURES |

Notes:

- **Thresholds fall back to `default`.** If you write `block_at = { security = "high" }`
  without a `default` key, confirmed findings in every other category never block. Always
  include `default`.
- **Setting an outcome key to `PASS`** makes that rule advisory: it still appears as
  triggered in the output but cannot change the decision. This is visible in the policy
  file and its sha256. An advisory outcome on a mandatory group does not count as
  positive evidence, so `R-POSITIVE-EVIDENCE` can still require review.
- **The sha256 covers the raw file**, comments included, so every decision names the
  exact policy text it was computed with.

## Customizing

Policy is a team decision made before evaluation, not during it. Agents may draft a
policy change when asked, but never change the policy that is evaluating the current
run to get a different outcome.

**1. Use the strict policy for a release.**

```toml
# .qa-superteam/config.toml
[policy]
path = "policies/strict.toml"     # resolved in the project, then in the plugin
```

**2. Keep a project policy in the repository.** Copy `policies/default.toml` to e.g.
`qa/release-policy.toml`, change `name`/`version`, edit, and point `[policy] path` at
it. Review policy changes like code: the decision records the file's sha256.

**3. A payments service where confirmed high defects always block.**

```toml
[findings]
block_at = { default = "high", security = "medium", data-integrity = "medium" }
review_at = { default = "medium" }
unverified_review_at = "medium"
```

**4. Make browser journeys mandatory on every run**, not only when planned:

```toml
[groups]
mandatory = ["existing-suite", "critical-journeys"]
```

Every run must then include `qast exec playwright --group critical-journeys ...` (or the
project's e2e adapter); a run without it gets `on_missing`.

**5. AI systems.** `[ai_eval] min_pass_rate` applies only when `ai-eval` results exist.
Adding `ai-eval` to `mandatory` forces the evals to run, but then the group rules apply
to every case, so a single FAILED case triggers `on_fail` regardless of the pass rate.
Choose deliberately: keep `ai-eval` out of `mandatory` and treat a missing AI eval as a
process failure, or make it mandatory and accept zero tolerance.

```toml
[ai_eval]
min_pass_rate = 0.95
below_threshold = "BLOCK"
inconclusive = "REVIEW_REQUIRED"
```

**6. A documented, accepted skip.** `max_skipped_in_mandatory = 1` lets one SKIPPED,
NOT_RUN or BLOCKED result per mandatory group through. It applies to every mandatory
group and every future skip, so prefer fixing or removing the skipped test with team
sign-off.

**7. CI.**

```bash
qast gate --exit-code          # 0 PASS, 10 REVIEW_REQUIRED, 20 BLOCK
```

Map 10 to a required manual approval step rather than to success.

**8. Advisory rollout.** While a team adopts the gate, `untested_high_risk = "PASS"`
and `untriaged_failures = "PASS"` turn those rules into warnings. `R-CONFIRMED-BLOCKING`,
`R-CONFIRMED-REVIEW`, `R-UNVERIFIED-HIGH-IMPACT`, `R-FLAKY-CRITICAL` and
`R-POSITIVE-EVIDENCE` have fixed outcomes and stay in force.
