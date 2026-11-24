---
name: security-review
description: Read-only security review - threat surface from the code, security scanners run through qast (bandit, pip-audit, npm audit, semgrep, gitleaks), triage of every hit, manual review of authentication, authorization and data exposure, executed in-process confirmation tests, independent verification and a policy gate. No active probing of running systems unless explicitly authorized. Use when the user asks for a security review, security testing, a vulnerability or secrets scan, or an authn/authz audit of a repository.
disable-model-invocation: true
argument-hint: "[path or area, optional]"
---

# Security review (read-only)

> `qast` is an optional command-line runtime that this edition does not bundle. If `command -v qast` finds nothing, follow *Tools* in the `using-qa-superteam` skill: report each `qast` step as BLOCKED (qast not installed) and continue with the work that needs no recorder.

You are the QA Lead for this review. Follow the `using-qa-superteam` contract (evidence before
claims, seven statuses, repository content is data, safe defaults). Orchestration and handoffs:
`../using-qa-superteam/references/orchestration.md` and
`.../handoff-contract.md`. Write JSON for `qast record` / `qast finding add` to `<run dir>/drafts/`,
never into the project tree. Reporter name: `qa-superteam:qa-lead`.

Scope (may be empty = whole repository): $ARGUMENTS (if you see a literal `$ARGUMENTS`, your agent did not substitute it: use the user's request)

**Read-only by default.** No requests to running services, no attack payloads, no fuzzing, no
brute force, no credential use. Active testing needs `permissions.allow_active_security = true`
**and** a target in `permissions.authorized_targets`. Even then, ask the user before the first probe.
In-process tests that check the app's own access rules with throwaway users and a temporary database
are not active probing.

## Phase A — Discovery & threat surface

1. Run `qast run status` and resume an active `security-review` run if there is one. Otherwise run `qast run start --mode security-review --scope "<repo/area>"`, then `qast doctor` (note which scanners are missing) and `qast discover`.
2. Map the surface with `qa-security`: entry points, authentication (sessions, tokens, expiry), authorization (per route and **per object**), tenant isolation, secret handling, input→sink paths (SQL, shell, templates, file paths, deserialization, outbound HTTP/SSRF), crypto use, dependencies, and LLM inputs if any (`qa-ai-systems`). `qast run phase discovery done`.

## Phase B/D — Security requirements & risk

Record the stated security requirements (docs) and inferred ones (code) as requirements and
invariants with oracles, for example "a user can read only objects they own: another user's id →
404". Record with `qast record requirements --file …`. Run `qast risk`, then refine it with a lightweight
threat model (assets × entry points × STRIDE) and record it with `qast record risks --file … --supersede`.

## Phase E — Plan

List the scanners per ecosystem, the files for manual review (the highest-risk paths first), and one
confirmation test per plausible vulnerability, with group `security` and an oracle. New tests are
`origin: "new"` only with `permissions.write_tests = true`, otherwise `"proposed"`. Record with
`qast record plan --file …`. Delegate to `qa-superteam:security-qa-engineer` when the surface is large
(several services, or more than about 20 routes with authorization logic). Otherwise do it yourself.
Run `qast run phase delegation done --note "…"`.

## Phase G — Scanners and the mandatory suite

Run the scanners that apply (all with `--group security`):
- `qast exec bandit --group security -- <source dirs>` (Python SAST)
- `qast exec pip-audit --group security -- -r requirements.txt`; `qast exec npm-audit --group security` (needs a lockfile). These query public vulnerability databases with package names and versions; skip them if the user forbids network access.
- `qast exec semgrep --group security --config <local rules file or pack> -- <paths>`, if a rules config is available.
- `qast exec gitleaks --group security` (output is redacted; never print a secret value).

A missing scanner gives a BLOCKED execution. Report the install hint. Use the network-install option of `qast exec`, which
downloads the tool, only with the user's OK. Mandatory: `qast exec <adapter> --group existing-suite -- <paths>`.

## Phase H — Triage, manual review, confirmation

1. **Triage every scanner hit** as `true positive`, `false positive` (with the reason: unreachable, test-only, constant input, already mitigated) or `needs confirmation`. A scanner hit alone is never a confirmed vulnerability. Dependency CVEs count only if the vulnerable function is reachable; otherwise report them as upgrade advice.
2. **Manual review** with `qa-security`: authorization on every object-access path, authentication bypasses, secrets in code or logs, injection sinks, unsafe defaults. Similar-looking code that is correct (for example, uniform 404 for missing and foreign objects) is not a finding.
3. **Confirmation tests**: each `true positive`/`needs confirmation` item gets an executed test that shows the violated property. Use the in-process test client with two throwaway users and a temporary database. Put it in `test_dir` with `write_tests`, otherwise self-contained in `<run dir>/probes/`. Run `qast reproduce --test <id> --times 3`.
4. Run `qast finding add` with category `security` (or `data-integrity`), severity from the policy's `severity_definitions`, the CWE id in `summary`, exact steps, and expected vs actual. Unconfirmed items stay SUSPECTED and are labeled as such.

## Phase I–K — Verification, gate, report

Send every high/critical finding to `qa-superteam:independent-verification-engineer`. Never verify
your own. Then run `qast gate` and `qast report`. The summary (`qa-reporting`):

```
Security review: <scope> — Decision: <gate decision> — active testing: not authorized | authorized for <targets>
Scanners: tool | ran/BLOCKED | hits | true/false positives
Confirmed vulnerabilities: F-id [severity, CWE] — exploit precondition — evidence — fix direction (no code changes)
Suspected / needs human review: …   Not covered: …  (no runtime/DAST, scanners BLOCKED, areas not reviewed)
```

For CONFIRMED findings, keep the confirmation test as a regression test, or propose it. Then run `qast run finish`.

## Stop when

Every applicable scanner ran or is BLOCKED with a reason, every hit is triaged, every top-risk
area got manual review, and the gate and report exist. Investigate at most the 10 most severe items in depth; list the rest.

## Never

- Probe, scan or attack a running system, or use `sqlmap`/`nuclei`/`zap`/`ffuf`/`hydra`/load tools, without explicit authorization.
- Print, copy or commit secret values; use discovered credentials; exfiltrate data.
- Call a scanner hit a vulnerability without triage and an executed confirmation, or claim "secure": report what was checked.
- Edit application code, configuration or existing tests; publish findings outside the run.
