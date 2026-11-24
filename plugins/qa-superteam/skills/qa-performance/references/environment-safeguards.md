# Environment safeguards checklist

Complete this before any `--profile load` run. Every "no" is a stop: record it with
`qast run note --kind limitation` and run smoke only (or nothing, for the first block).

## Authorization (all required)

- [ ] The target URL is in `permissions.authorized_targets` (qast enforces this; do not edit the list yourself).
- [ ] `permissions.allow_load_testing = true` (qast enforces this too).
- [ ] The target is not production and does not share infrastructure with production
      (database, cache, queue, third-party accounts, rate-limit quotas). A staging API that
      writes to the production payment sandbox account is not isolated.
- [ ] The hostname does not look like production (`prod`, `live`, `www`, `api.<company>.<tld>`
      without an environment marker). If it does, the user has confirmed in this session
      that it is non-production.
- [ ] Whoever owns the environment knows a load test is running, for any environment you did not start yourself.

## Blast radius

- [ ] Third-party calls made by the target (payments, email, SMS, LLM APIs) are stubbed,
      sandboxed or explicitly approved: load on the target becomes load and cost on them.
- [ ] The script creates its own users and data; it never logs in as real accounts.
- [ ] Data created by the test is disposable (temp database, environment reset) or the
      cleanup is agreed with the owner.
- [ ] Duration and peak rate are bounded in the script (`stages`, `duration`, `maxVUs`)
      and `abortOnFail` is set on the primary threshold.
- [ ] Rate limits and WAF rules in front of the target are known: a 429 storm measures the
      gateway, not the service.

## Measurement validity

- [ ] Load generator and target do not share a CPU budget, or the overlap is stated in the report.
- [ ] The dataset size matches the question (an empty DB makes every query fast).
- [ ] The app runs in its production mode: no debug, no auto-reload, production worker count.
- [ ] Caches are in the state the question needs (cold-start vs warm), stated in the report.
- [ ] Nothing else is load-testing the same environment at the same time.
- [ ] You know how to observe the target during the run (CPU, memory, DB connections), or
      the report says the bottleneck cannot be identified.

## Local runs you start yourself

A local app on `127.0.0.1` with a temporary database satisfies the authorization and
blast-radius blocks once `allow_load_testing = true`, as long as its outbound integrations
are stubbed. It does not satisfy production-capacity questions: results describe this
machine. Say so in every number you report.

## After the run

- [ ] Stop the processes you started (server, workers).
- [ ] Remove temporary databases you created outside the run directory.
- [ ] Note the exact window of the run (start/end time) in the summary so owners can
      correlate it with their monitoring.
