# k6 script template

This script was run through `qast exec k6` (smoke profile) against a local FastAPI wallet
API and its `scenarios` block validated with `k6 inspect`. Adapt endpoints, payloads and
thresholds to the system under test; keep the structure.

## Constraints qast enforces

- The base URL comes only from `__ENV.TARGET`; qast passes `-e TARGET=<--target>` after
  checking it against `permissions.authorized_targets`.
- **No absolute URL anywhere in the file**, comments included: qast scans the text and
  blocks scripts containing an `http(s)://` URL that is not authorized.
- `--profile smoke` adds `--vus 1 --iterations 5`, which **replaces** the script's
  `scenarios` and runs the `default` export. A script without `export default function`
  fails under smoke ("function 'default' not found in exports").
- `--profile load` uses the script's own `options` and needs `permissions.allow_load_testing = true`.
- Results: one PASSED/FAILED result per threshold expression and per check (k6 exit code 99,
  thresholds crossed, is parsed as FAILED results, not as a tool error).

## Template

Save as `<test_dir>/perf/<flow>.js` (for example `tests/qa/perf/transfers.js`).

```javascript
// Base URL comes only from __ENV.TARGET: qast passes the authorized --target.
// No absolute URLs anywhere in this file (qast refuses scripts that contain them).
import http from 'k6/http';
import { check, group, sleep } from 'k6';

const BASE = __ENV.TARGET;
if (!BASE) {
  throw new Error('TARGET is not set; run via: qast exec k6 --target <authorized url> -- <script>');
}
const JSON_HEADERS = { 'Content-Type': 'application/json' };

export const options = {
  // Used by the 'load' profile only. The 'smoke' profile overrides this with
  // --vus 1 --iterations 5, which runs the default function below.
  scenarios: {
    reads: {
      executor: 'ramping-vus',
      exec: 'readPath',
      startVUs: 0,
      stages: [
        { duration: '1m', target: 20 },  // ramp up
        { duration: '3m', target: 20 },  // steady state: the window you judge
        { duration: '30s', target: 0 },  // ramp down
      ],
      gracefulRampDown: '10s',
    },
    writes: {
      executor: 'constant-arrival-rate', // open model: load does not drop when the system slows
      exec: 'writePath',
      rate: 5,
      timeUnit: '1s',
      duration: '3m',
      startTime: '1m',
      preAllocatedVUs: 10,
      maxVUs: 50,
    },
  },
  // The summary qast stores reports these statistics; the default set has no p(99).
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)', 'p(99)'],
  thresholds: {
    http_req_failed: ['rate<0.01'],
    checks: ['rate>0.99'],
    'http_req_duration{name:GET /wallets/me}': ['p(95)<300', 'p(99)<800'],
    'http_req_duration{name:POST /transfers}': [
      { threshold: 'p(95)<500', abortOnFail: true, delayAbortEval: '30s' },
    ],
    dropped_iterations: ['count<1'], // arrival-rate could not be sustained
  },
};

function login(email, password) {
  http.post(`${BASE}/auth/register`, JSON.stringify({ email, password }), {
    headers: JSON_HEADERS, tags: { name: 'POST /auth/register' },
  });
  const res = http.post(`${BASE}/auth/login`, JSON.stringify({ email, password }), {
    headers: JSON_HEADERS, tags: { name: 'POST /auth/login' },
  });
  check(res, { 'login 200': (r) => r.status === 200 });
  return { Authorization: `Bearer ${res.json('token')}`, 'Content-Type': 'application/json' };
}

// setup() runs once; its return value is passed to every iteration.
export function setup() {
  const run = Date.now();
  const sender = login(`perf-sender-${run}@example.com`, 'perf-password-1');
  const recipient = login(`perf-recipient-${run}@example.com`, 'perf-password-2');
  http.post(`${BASE}/wallets/me/deposit`, JSON.stringify({ amount_cents: 1000000 }), {
    headers: sender, tags: { name: 'POST /wallets/me/deposit' },
  });
  const wallet = http.get(`${BASE}/wallets/me`, { headers: recipient, tags: { name: 'GET /wallets/me' } });
  return { sender, recipientWalletId: wallet.json('id') };
}

export function readPath(data) {
  group('read wallet', () => {
    const res = http.get(`${BASE}/wallets/me`, { headers: data.sender, tags: { name: 'GET /wallets/me' } });
    check(res, {
      'wallet 200': (r) => r.status === 200,
      'wallet has integer balance': (r) => Number.isInteger(r.json('balance_cents')),
    });
  });
  sleep(1); // think time: model a user, not a tight loop
}

export function writePath(data) {
  group('transfer', () => {
    const body = JSON.stringify({ to_wallet_id: data.recipientWalletId, amount_cents: 1 });
    const res = http.post(`${BASE}/transfers`, body, { headers: data.sender, tags: { name: 'POST /transfers' } });
    check(res, { 'transfer 201': (r) => r.status === 201 });
  });
}

// The smoke profile runs this: one pass over every path.
export default function (data) {
  readPath(data);
  writePath(data);
}
```

## Running

```
# local app on a disposable DB, started by you (example for a FastAPI app)
APP_DB="$(mktemp -d)/perf.db" python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8765 &
# wait for readiness with a deadline instead of a fixed sleep
python3 -c "import time,urllib.request as u
d=time.monotonic()+30
while True:
    try: u.urlopen('http://127.0.0.1:8765/healthz', timeout=1); break
    except OSError:
        if time.monotonic()>d: raise SystemExit('server not ready')
        time.sleep(0.2)"

qast exec k6 --group performance --target http://127.0.0.1:8765 -- tests/qa/perf/transfers.js
qast exec k6 --group performance --target http://127.0.0.1:8765 --profile load -- tests/qa/perf/transfers.js   # only with allow_load_testing
```

The env variable name (`APP_DB` above), module path and health route belong to the
project: take them from its README or app factory. Stop the server afterwards (`kill %1`
in the same shell, or by its PID).

## Adapting the template

- **Name every request** with `tags: { name: '<METHOD> <route template>' }`. URLs with ids
  otherwise create one metric series per id, and thresholds on `{name:...}` need the tag.
- **One threshold per user-facing operation** from the SLO, plus `http_req_failed` and
  `checks`. A latency threshold without an error-rate threshold passes when the server
  answers fast errors.
- **`check` does not fail the run by itself**; the `checks: ['rate>0.99']` threshold does.
- **`abortOnFail`** stops a load test early when the system is clearly failing (protects
  shared environments); `delayAbortEval` avoids aborting on warm-up noise.
- **Executors**: `ramping-vus`/`constant-vus` (closed model: N users who wait for responses),
  `constant-arrival-rate`/`ramping-arrival-rate` (open model: requests arrive regardless of
  response time; use it to test a throughput target). See [slo-thresholds.md](slo-thresholds.md).
- **Test data**: create it in `setup()`; unique emails per run (`Date.now()`) avoid conflicts
  with earlier runs. Never point a script at real accounts.
- **Per-VU state**: use `exec.vu.idInTest` from `import exec from 'k6/execution'` when each
  VU needs its own user, to avoid lock contention on one account that the real traffic would not have.
- **Payload files**: `open('./data.json')` in init context, relative to the script.

## Reading the result

`qast exec` prints one result per threshold (`threshold:<metric>:<expression>`) and per
check (`check:<group>::<name>`). The `k6-summary.json` evidence holds the observed values
(the `summaryTrendStats` per trend metric, `rate` for rates, `count` for counters). Evidence
text is redacted before storage; if the stored file does not parse as JSON, read it as text.
For a smoke run, report only that the checks passed: its percentiles describe five requests.
