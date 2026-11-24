# Thresholds, percentiles and load models

## From SLO to k6 threshold

An SLO has four parts; a threshold needs all four or it is not testable.

| Part | Example | k6 |
|---|---|---|
| Operation | "create transfer" | request tagged `name: 'POST /transfers'` |
| Indicator | server latency of successful requests | `http_req_duration{name:POST /transfers}` (add `expected_response:true` to exclude errors) |
| Objective | 95% under 500 ms, 99% under 1.2 s | `['p(95)<500', 'p(99)<1200']` |
| Conditions | at 50 requests/s with 1M rows in `transfers` | `constant-arrival-rate`, `rate: 50`; seeded DB size in the report |

Always pair latency with correctness: `http_req_failed: ['rate<0.01']` (or the SLO's error
budget) and `checks: ['rate>0.99']`. A system that fails fast meets any latency threshold.

Sub-metric tags combine: `'http_req_duration{name:POST /transfers,expected_response:true}'`.

### No SLO given

1. Ask the user for the target. If none exists, measure a baseline on the current version
   (same environment, same load model) and set provisional thresholds: p95 ≤ baseline p95 × 1.2,
   error rate ≤ baseline rate + 0.5 percentage points.
2. Record them as `assumed` in the plan case and as `qast run note --kind assumption`.
3. Never invent "industry standard" numbers ("APIs should answer in 200 ms") as an oracle.

### Relative checks for a change

For a PR, compare candidate vs base on the same machine, same data, same script, back to
back (alternate them if the run is long: base, candidate, base, candidate). Report the
change in p50/p95 with both values. A difference smaller than run-to-run variation (measure
it by running the base twice) is noise, not a regression.

## Reading percentiles

- **p50** is the typical request; **p95/p99** are what one in 20 / one in 100 requests
  see. Users making many requests per page hit the tail often: a page with 20 calls sees
  the per-call p95 on most loads.
- **Sample size**: a percentile needs enough samples beyond it. With n samples, p99 rests
  on about n/100 observations. Under ~1,000 samples p99 is noise; under ~100, p95 is.
  A smoke run (5 iterations) supports neither, which is why it is a functional check only.
- **Averages hide tails**: never use `avg` as the oracle for latency.
- **Max** is one request; report it, do not threshold on it.
- **Percentiles do not add**: p95 of a page ≠ sum of p95 of its calls. Measure the composite
  operation if the SLO is about the composite.
- **Coordinated omission**: closed-model tests (fixed VUs that wait for responses) send less
  load when the system slows, hiding the tail. To test a throughput target, use an
  arrival-rate executor and check `dropped_iterations` (non-zero ⇒ the generator could not
  sustain the rate, so the target was not actually tested).

## Load models

| Question | Executor | Notes |
|---|---|---|
| "Can N users browse concurrently?" | `ramping-vus` / `constant-vus` (closed) | Include think time (`sleep`) from real usage, or N VUs model far more than N users |
| "Do we meet latency at R requests/s?" | `constant-arrival-rate` (open) | Size `preAllocatedVUs` ≈ R × expected latency (s) × 1.5; cap `maxVUs` |
| "Where does it break?" (stress) | `ramping-arrival-rate` with increasing stages | Only with `allow_load_testing`; stop at the first threshold crossing (`abortOnFail`) |
| "Does it degrade over hours?" (soak) | `constant-arrival-rate`, long duration | Only on a dedicated environment; watch memory and connection counts |

Little's law sanity check: concurrency ≈ throughput × latency. 50 req/s at 200 ms keeps
about 10 requests in flight; if the server's worker or DB pool is smaller than that, queueing
latency is expected, and the finding is the pool size, not "the code is slow".

## Judging a load run

1. **Discard warm-up.** Judge the steady-state stage. Thresholds apply to the whole run, so
   either keep ramp-up short relative to steady state or tag the steady phase (a separate
   scenario with `startTime`) and threshold that scenario's tagged metric
   (`'http_req_duration{scenario:steady}'`).
2. **Validate the run before the numbers**: `http_req_failed` low, `checks` high,
   `dropped_iterations` zero, load generator CPU below ~80% (a saturated generator measures itself).
3. **Then percentiles** against the thresholds.
4. **Resource view**: CPU, memory, DB connections and slow-query log of the target during
   steady state, if you can observe them. Without them, say the bottleneck is not identified.
5. **Report**: environment, dataset size, script path, profile, steady-state window,
   observed vs threshold per metric, execution ids.

## Classifying the outcome

qast records each threshold as PASSED or FAILED. Use this table to classify the run in
findings and in the summary; never edit records to match it.

| Situation | Report as |
|---|---|
| Thresholds evaluated on a valid load run and met | PASSED |
| Threshold crossed on a valid run, reproduced on rerun | FAILED ⇒ finding |
| Threshold crossed once, met on rerun (or vice versa) | INCONCLUSIVE: report both values |
| Generator saturated, dropped iterations, or setup failed | ERROR: the test did not measure the target |
| Load not authorized, k6 missing, target not authorized | BLOCKED |
| Only smoke ran | functional check PASSED/FAILED; capacity NOT_RUN |
