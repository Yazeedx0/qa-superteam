# Flakiness triage

A test is flaky when the same code and the same test give different results. Flakiness
is a finding about *something* - the test, the product, or the environment - and the
job is to find out which, with evidence. Until then the honest status is INCONCLUSIVE.

## What the numbers can and cannot tell you

With a true failure rate `p`, `n` attempts all pass with probability `(1-p)^n` and all
fail with probability `p^n`:

| failure rate p | 3 attempts all pass | 5 attempts all pass | 3 attempts all fail |
|---|---|---|---|
| 0.5 | 13 % | 3 % | 13 % |
| 0.2 | 51 % | 33 % | 1 % |
| 0.1 | 73 % | 59 % | 0.1 % |

So: `not-reproduced` after a few attempts does not prove stability, and `consistent`
after 3/3 can still be a coin flip. When flakiness is suspected, use `--times 5` (the
default cap) and look for the *mechanism* below - a mechanism shown by an execution is
stronger evidence than any count. Never keep re-running to get a preferred result:
all attempts stay in the record and an intermittent classification cannot be undone.

## Triage order

1. **Read the failure messages of the failing attempts.** Different messages in different attempts (timeout once, assertion once) point to timing; the same assertion with different values points to data/randomness.
2. **Run in isolation vs. in context** (order dependence).
3. **Search the test and the code under test** for the sources in the table.
4. **Make it deterministic** by controlling the suspected source; deterministic failure under control + pass without it = mechanism demonstrated.
5. **Decide test-side vs product-side**, then record.

## Sources and how to prove them

| Source | Signals in code | Proof by execution |
|---|---|---|
| Order dependence (victim/polluter) | Module globals, class attributes, caches (`lru_cache`), singletons, env vars set without restore, DB not reset between tests | `qast exec pytest -- <victim>` alone passes, `-- <polluter> <victim>` fails. Find the polluter by halving the list of tests that ran before the victim (`<first half> <victim>`, then quarter...). "Brittle" variant: fails alone, passes after a state-setter. |
| Time | `datetime.now()`, `time.time()`, dates in fixtures, expiry logic, `sleep`, timezone conversions, "today" in test data | Run with `TZ=UTC` and with `TZ=Pacific/Kiritimati` (different calendar date); run near a boundary if the code accepts an injected clock; freeze time if the project already uses a freezing library. |
| Randomness | `random`, `uuid4`, `secrets`, Faker without seed, `set`/`dict` iteration in assertions, hash-based ordering | Seed the RNG and show the outcome is fixed per seed and differs across seeds (wrapper below). For hash ordering: `PYTHONHASHSEED=0` vs `=1`. |
| Shared state / resources | Fixed temp file names, fixed ports, shared DB or cache server, files written into the repo, parallel workers | Run twice back-to-back; run with a fresh temp dir; check for leftover files after a run; compare serial vs parallel runs. |
| Async waits / races | `sleep`-based waits, polling with short timeouts, missing `await`, UI assertions without auto-waiting, threads without joins | Failure message is a timeout or a "not yet" value; adding latency (Playwright `page.route` delay, a slower fake) raises the failure rate; a barrier or event that forces the bad interleaving makes it fail every time. |
| Environment | External network calls, real clocks of remote services, tool/version differences, low disk/memory | Compare the `environment` blocks of passing and failing executions; failure correlates with the environment, not the test order or seed. |

### Seeded run wrapper (randomness)

Put this in `.qa-superteam/runs/<run-id>/probes/seeded.py` (not in the project):

```python
"""Run pytest with the global RNG seeded: same seed -> same outcome shows randomness drives the result."""
import random
import sys

import pytest

random.seed(int(sys.argv[1]))
sys.exit(pytest.main(["-p", "no:cacheprovider", "-p", "no:randomly", *sys.argv[2:]]))
```

```bash
P=.qa-superteam/runs/<run-id>/probes/seeded.py
qast exec command --label "seed-1" -- python3 $P 1 -q <test id>
qast exec command --label "seed-1" -- python3 $P 1 -q <test id>   # same seed: same result?
qast exec command --label "seed-2" -- python3 $P 2 -q <test id>   # other seed: other result?
```

Use the project interpreter if it is not `python3`. If a seed that fails and a seed that
passes are each stable on repeat, the randomness hypothesis is confirmed by those
execution ids.

## Test-side or product-side?

| The nondeterminism lives in... | Classification | Record |
|---|---|---|
| The test (unseeded test data, sleep-based waits, test-order coupling, fixed ports in fixtures) | Test defect (flaky test) | `qast finding add` with `category: "other"`, `severity: "info"`, title `Test defect: <test> is flaky (<mechanism>)`, the execution ids and a proposed fix (seed, explicit wait, isolated fixture). Quarantine is a human decision - see `qa-regression`. |
| The product (race between requests, time-zone bug, unordered results that users see, cache shared across users) | Product defect candidate | Finding with the reproduction ids; derived status INCONCLUSIVE until a deterministic reproduction (forced interleaving, fixed clock, fixed seed) fails consistently - then reproduce that test and hand to `qa-verification`. |
| The environment (external service, CI resource limits) | Environment | Limitation note; which environment property, what would make the test hermetic. |
| Unknown after the budget | Inconclusive | Finding (if product impact is plausible) or limitation; state the counts, the sources ruled out with their evidence, and the ones not checked. |

Order dependence is a product defect, not a test defect, when the leaked state is state
real users would share (e.g. a module-level cache that leaks one tenant's data to the
next request).

## Wording

Report "intermittent: 2/5 attempts failed (ex-..., ex-...)", "flaky test - cause:
unseeded `random` in the test, shown by seeded runs ex-.../ex-...". Do not write
"confirmed defect", "probably fine" or "passes now" about intermittent behaviour.
