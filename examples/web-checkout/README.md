# Web Checkout

A small three-step checkout for a fixed two-item cart. Plain HTML/CSS/vanilla JS (no build step), served by a
stdlib Python server that also exposes a tiny order API.

```
Contact  ->  Shipping  ->  Review  ->  Confirmation
```

- **Contact**: full name and email (both required, email format checked).
- **Shipping**: country (United States, Canada, Saudi Arabia) and postal code, validated per country.
  Shipping is $5.00 (US), $12.00 (CA) or $20.00 (SA).
- **Review**: contact and shipping summary, promo code (`SAVE10` = 10% off the subtotal), totals and
  **Place order**. If the order request fails, an error banner with **Retry** is shown.
- **Confirmation**: order number (`ORD-<n>`) and the receipt email.

The checkout draft is saved to `localStorage`, so reloading the page resumes on the same step with the
entered data. Add `?lang=ar` for the Arabic (right-to-left) interface.

| Country | Postal code format | Example   |
|---------|--------------------|-----------|
| US      | 5 digits           | `94107`   |
| CA      | `A1A 1A1`          | `K1A 0B1` |
| SA      | 5 digits           | `12345`   |

## Setup

```bash
python3 -m pip install -r requirements.txt
python3 -m playwright install chromium   # browser for the end-to-end tests
npm install                              # dev tooling (axe-core for accessibility checks)
```

## Run

```bash
python3 serve.py --port 8000            # add --verbose to log requests
# open http://127.0.0.1:8000/  or  http://127.0.0.1:8000/?lang=ar
```

### API

| Method | Path          | Response                                                                 |
|--------|---------------|--------------------------------------------------------------------------|
| POST   | `/api/orders` | `201 {"order_id": "ORD-1001"}`; `400` for invalid JSON or a body missing `contact`, `shipping` or `items` |
| GET    | `/healthz`    | `200 {"status": "ok"}`                                                   |

`serve.make_server(port=0)` returns `(server, base_url)` without starting it, which is how the tests run the
app on a free port.

## Tests

End-to-end tests use pytest and Playwright (headless Chromium):

```bash
python3 -m pytest -q
```

- `tests/test_happy_path.py`: cart contents, full checkout, Canadian address and rate.
- `tests/test_navigation.py`: Back keeps entered data; reload restores the draft and step.
- `tests/test_validation.py`: inline email error.

Set `QAST_ARTIFACT_DIR=/some/dir` to save a full-page screenshot of every failing test as
`<sanitized node id>.png`. If the Chromium build pinned by your Playwright version is not installed, the tests
fall back to the newest Chromium in the Playwright browser cache; set `CHROMIUM_EXECUTABLE` to choose one
explicitly.

## Layout

```
serve.py              static server + order API
public/index.html     markup for every step
public/app.js         checkout logic (validation, draft persistence, totals, order submission)
public/i18n.js        English and Arabic strings
public/styles.css     responsive styles (single column below 820px)
tests/                Playwright end-to-end suite
docs/USER_JOURNEYS.md critical journeys and acceptance criteria
```
