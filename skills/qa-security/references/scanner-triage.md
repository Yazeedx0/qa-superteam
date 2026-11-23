# Scanner triage guide

`qast exec bandit|semgrep|pip-audit|npm-audit|gitleaks` records every scanner hit as a
FAILED result so it is traceable. That FAILED status means "the scanner reported
something", never "the product is defective". Triage turns each candidate into one of:

| Outcome | Meaning | What you record |
|---|---|---|
| **True positive, proven** | An executed test demonstrates the property | `qast finding add` with the proof test's execution, plus the scan execution as context |
| **True positive, needs proof** | Reachable and plausible; proof test designed but not yet run | Plan case (`origin: "new"` or `"proposed"`); finding only once the test FAILED |
| **Hardening** | Real weakness with no attacker path today (dead code, admin-only script) | `qast run note --kind decision` with the reason; severity `info` if reported at all |
| **False positive** | The flagged pattern is safe in context | `qast run note --kind decision "<rule id> in <path>: false positive because <reason>"`, one note per class, not per line |
| **Needs info** | Cannot decide without the owner (deployment, config) | `qast run note --kind limitation` and list it as not verified |

Read the rule's documentation and the code around the hit before deciding. Count outcomes
for the summary: candidates → proven / needs proof / hardening / false positive / needs info.

## Three questions for every candidate

1. **Source**: can an attacker control the input that reaches this line (request data,
   headers, files, retrieved documents, queue messages)? Constants and config are not attacker input.
2. **Path**: is the code reachable in a shipped path (route, job, CLI used in production)?
   Tests, fixtures, migrations, dev scripts usually are not.
3. **Mitigation**: is it neutralized before or after (parameter binding, allowlist,
   framework escaping, a validator, network isolation)? A mitigation counts only if you can
   point to it, ideally with a test.

Yes / yes / no ⇒ true positive candidate: write the proof test.

## Per-scanner criteria

### bandit (Python SAST)

| Rule | Usually true positive when | Usually false positive when |
|---|---|---|
| B608 SQL string building | f-string/`%`/`+` builds SQL with request data | Only table/column names from a fixed allowlist, or values bound via `?`/`%s` parameters |
| B602/B605 shell, B603/B607 subprocess | `shell=True` with interpolated input; executable from input | Fixed argv list, no shell, constants only |
| B301/B403 pickle, B506 yaml.load | Deserializes request, file-upload or cache data from outside | Trusted local files written by the same process |
| B105/B106/B107 hard-coded password | A real credential in shipped code | Test fixtures, placeholder defaults that fail closed, the word "password" as a field name |
| B101 assert | `assert` used for authorization or validation in shipped code (removed under `-O`) | Inside tests |
| B311 random | Tokens, reset codes, session ids from `random` | Jitter, sampling, test data |
| B501 `verify=False`, B113 no timeout | Shipped HTTP clients | Local test harnesses (still note B113 for `qa-reliability`) |

Bandit's `confidence` is about the pattern match, not exploitability; triage high-severity
low-confidence hits too.

### semgrep

Taint-mode rules (source → sink) deserve a proof test; pattern-only rules need the three
questions. Note the ruleset (`--config`) in the summary so the coverage claim is honest:
"no findings from `p/python`" says nothing about rules that were not run.

### pip-audit / npm-audit (dependencies, A06:2021)

- **Runtime vs dev**: a vulnerable test runner or linter is not shipped (npm: check whether
  the package is only in `devDependencies`; follow the `via` chain).
- **Reachability**: does the project call the vulnerable function or enable the vulnerable
  feature? Read the advisory's affected API. "Imported somewhere" is not reachable.
- **Fix availability**: `fix versions: none` still needs reporting if reachable; recommend mitigation.
- **Environment**: pip-audit audits what you point it at. Without `-r <requirements file>` it
  audits the interpreter it runs in; say which one in the summary.
- A reachable vulnerable dependency is a finding even without an exploit test when an
  executed test shows the vulnerable code path is exercised; otherwise record it as needs
  proof with the advisory id, and do not claim exploitability.

### gitleaks (secrets, A02/A07:2021)

- Evidence is stored with `--redact` and qast redaction; keep it that way. Refer to a
  secret only as `<RuleID> at <file>:<line> (commit <short sha>)`.
- **True positive**: a credential with a real-looking format in a tracked file or in history,
  for a system that exists (cloud keys, API tokens, private keys, connection strings with passwords).
- **False positive**: documented example keys, obviously fake test values, hashes,
  public keys, high-entropy ids that are not credentials. Say why without quoting the value.
- **History matters**: a secret removed from HEAD but present in history is still exposed.
  Rotation is the fix; deleting the line is not.
- Never test whether a found credential works. Validity checks against a live service are
  unauthorized use.

## Severity: CVSS-lite

Score each factor, add the points, map to the policy severity. Then sanity-check against
the policy definitions in `policies/default.toml` (security findings at `high` or above
block a release once confirmed).

| Factor | 0 | 1 | 2 |
|---|---|---|---|
| Attack vector | local / physical | adjacent or internal network | internet-facing |
| Privileges required | admin | any authenticated user | none |
| User interaction | victim must act (click, open) | | none |
| Confidentiality impact | none | limited data, own tenant | other users' or tenants' data, credentials |
| Integrity impact | none | own data | others' data, money, permissions |
| Availability impact | none | degraded | outage |
| Scope | stays in component | | crosses tenant or trust boundary |

| Points | Severity |
|---|---|
| ≥ 9 | critical |
| 6-8 | high |
| 4-5 | medium |
| 2-3 | low |
| ≤ 1 | info |

Overrides: authentication bypass or reading another user's financial or personal data is at
least `high`; a working leaked production credential is `critical`; missing hardening
headers with no demonstrated impact is at most `low`. Write the factor values into the
finding summary ("internet-facing, any authenticated user, no interaction, other users'
data: 2+1+2+2 = 7 ⇒ high") so the severity can be reviewed.
