# Playwright for Python (pytest) patterns

Sync API, Playwright 1.4x+, pytest 8+. Reuse the project's fixtures first: if
`tests/conftest.py` already provides a server, `browser`, `page` and a failure-screenshot
hook, new files in `tests/qa/` inherit them and you add only what is missing. Projects
using the `pytest-playwright` plugin already have `page`, `context`, `browser` and
`--base-url`; do not redefine those fixtures.

## Fixtures (only when the project has none)

```python
# tests/qa/conftest.py
import os
import re
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def base_url():
    """Start the app on a free local port; poll readiness with a deadline."""
    port = _free_port()
    # Replace with the project's own start command (from README / package.json scripts).
    cmd = [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", str(ROOT / "public")]
    proc = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 20
    while True:
        try:
            with urllib.request.urlopen(url + "/", timeout=1):
                break
        except OSError:
            if proc.poll() is not None or time.monotonic() > deadline:
                proc.kill()
                pytest.fail(f"app did not start on {url} within 20 s (exit code {proc.poll()})")
            time.sleep(0.1)
    yield url
    proc.terminate()
    proc.wait(timeout=10)


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


def _artifact_name(nodeid: str) -> str:
    # qast links an artifact to a test when the file name contains the node id
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", nodeid).strip("_")


@pytest.fixture
def context(browser, base_url, request):
    ctx = browser.new_context(base_url=base_url, viewport={"width": 1280, "height": 800}, locale="en-US")
    ctx.tracing.start(screenshots=True, snapshots=True)
    yield ctx
    report = getattr(request.node, "rep_call", None)
    out = os.environ.get("QAST_ARTIFACT_DIR")
    if out and report is not None and report.failed:
        ctx.tracing.stop(path=str(Path(out) / f"{_artifact_name(request.node.nodeid)}-trace.zip"))
    else:
        ctx.tracing.stop()
    ctx.close()


@pytest.fixture
def page(context):
    return context.new_page()


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item, call):
    report = yield
    setattr(item, f"rep_{report.when}", report)  # read by the context fixture
    out = os.environ.get("QAST_ARTIFACT_DIR")
    page = item.funcargs.get("page")
    if out and report.failed and report.when == "call" and page is not None and not page.is_closed():
        try:
            page.screenshot(path=str(Path(out) / f"{_artifact_name(item.nodeid)}.png"), full_page=True)
        except Exception as exc:  # never mask the real failure
            report.sections.append(("screenshot", f"could not capture: {exc}"))
    return report
```

- If the app has a Python factory (`make_server(port=0)` returning server and URL), start
  it in a daemon thread instead of a subprocess.
- Reuse an already running dev server only if its URL is in
  `permissions.authorized_targets` and the user pointed you at it; otherwise start your own.
- Open traces with Playwright's trace viewer (`show-trace <file>`, or trace.playwright.dev); mention
  the evidence id, not a local path, in findings.

## Journey with validation-error recovery

```python
# tests/qa/test_qa_recovery.py
import re

from playwright.sync_api import Page, expect


def test_details_step_recovers_from_invalid_email_in_same_session(page: Page):
    page.goto("/")
    page.get_by_label("Full name").fill("Noor Haddad")
    email = page.get_by_label("Email")
    email.fill("noor.example.com")
    page.get_by_role("button", name="Continue").click()

    # 1. The error is shown, announced and linked to the field; the step does not advance.
    expect(email).to_have_attribute("aria-invalid", "true")
    error = page.locator("#" + email.get_attribute("aria-describedby").split()[0])
    expect(error).to_be_visible()
    expect(error).to_have_attribute("role", "alert")
    expect(page.get_by_role("heading", name="Your details")).to_be_visible()

    # 2. Correct the value: the error clears, entered data is kept.
    email.fill("noor@example.com")
    page.get_by_role("button", name="Continue").click()
    expect(email).not_to_have_attribute("aria-invalid", "true")
    expect(page.get_by_role("heading", name="Address")).to_be_visible()

    # 3. The journey completes in the same page session (no reload, no navigation away).
    page.get_by_label("Postal code").fill("10115")
    page.get_by_role("button", name="Continue").click()
    page.get_by_role("button", name="Confirm booking").click()
    expect(page.get_by_text(re.compile(r"BK-\d+"))).to_be_visible()
```

Recovery variants worth a case each: an error on one field fixed while another field
is still empty; an error caused by a dependent field (change country after entering a
postal code that was valid for the previous one); an error after navigating Back; the
same journey in every supported locale. The oracle is the requirement's wording (does the
message clear on input or on the next submit?), not whatever the app does now.

## Network failures, server errors, slow responses and double submit

```python
# tests/qa/test_qa_network.py
import re

from playwright.sync_api import Page, Route, expect


def reach_review_step(page: Page):
    page.goto("/")
    page.get_by_label("Full name").fill("Noor Haddad")
    page.get_by_label("Email").fill("noor@example.com")
    page.get_by_role("button", name="Continue").click()
    page.get_by_label("Postal code").fill("10115")
    page.get_by_role("button", name="Continue").click()
    expect(page.get_by_role("heading", name="Review your booking")).to_be_visible()


def test_server_error_keeps_data_and_retry_resubmits_the_same_booking(page: Page):
    bodies = []

    def fail_once(route: Route):
        bodies.append(route.request.post_data_json)
        if len(bodies) == 1:
            route.fulfill(status=503, content_type="application/json", body='{"error": "unavailable"}')
        else:
            route.continue_()

    page.route("**/api/bookings", fail_once)
    reach_review_step(page)
    page.get_by_role("button", name="Confirm booking").click()
    expect(page.get_by_role("button", name="Retry")).to_be_visible()
    expect(page.get_by_role("heading", name="Review your booking")).to_be_visible()

    page.get_by_role("button", name="Retry").click()
    expect(page.get_by_text(re.compile(r"BK-\d+"))).to_be_visible()
    assert len(bodies) == 2
    assert bodies[0] == bodies[1]  # the retry resubmits exactly what was shown


def test_connection_failure_is_reported_not_swallowed(page: Page):
    page.route("**/api/bookings", lambda route: route.abort("internetdisconnected"))
    reach_review_step(page)
    page.get_by_role("button", name="Confirm booking").click()
    expect(page.get_by_role("button", name="Retry")).to_be_visible()


def test_double_click_while_pending_sends_one_booking(page: Page):
    held: list[Route] = []
    page.route("**/api/bookings", lambda route: held.append(route))  # hold requests open
    reach_review_step(page)
    with page.expect_request("**/api/bookings"):
        page.get_by_role("button", name="Confirm booking").dblclick()
    # One animation frame lets any second click handler fire; no fixed sleep.
    page.evaluate("() => new Promise(requestAnimationFrame)")
    for route in held:
        route.continue_()
    expect(page.get_by_text(re.compile(r"BK-\d+"))).to_be_visible()
    assert len(held) == 1, f"{len(held)} booking requests were sent for one confirmation"
```

- `route.abort(...)` error codes: `failed`, `internetdisconnected`, `timedout`,
  `connectionrefused`.
- Hold-then-release (`held.append(route)`, later `route.continue_()`) tests loading
  states and double submits without sleeps.
- Prefer `page.expect_response("**/api/bookings")` when the oracle is the request itself.

## Responsive (375 px) and overflow

```python
# tests/qa/test_qa_mobile.py
from playwright.sync_api import Page, expect

LONG_NAME = "Maximiliana Alexandrovna Konstantinopoulou-Wetherby-Featherstonehaugh"


def horizontal_overflow(page: Page) -> int:
    return page.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")


def test_no_horizontal_scroll_at_375px_with_long_input(page: Page):
    page.set_viewport_size({"width": 375, "height": 812})
    page.goto("/")
    page.get_by_label("Full name").fill(LONG_NAME)
    page.get_by_label("Email").fill("maximiliana.konstantinopoulou@long-subdomain.example.com")
    page.get_by_role("button", name="Continue").click()
    expect(page.get_by_role("heading", name="Address")).to_be_visible()
    assert horizontal_overflow(page) <= 0
    box = page.get_by_role("button", name="Continue").bounding_box()
    assert box is not None and box["x"] >= 0 and box["x"] + box["width"] <= 375
```

Check every step and every error state, not just the first screen. For device emulation
(touch, DPR, user agent): `browser.new_context(**playwright.devices["iPhone 13"], base_url=...)`
with the `playwright` object from `sync_playwright()`.

## Right-to-left

```python
# tests/qa/test_qa_rtl.py
from playwright.sync_api import Page, expect

ENGLISH_UI_STRINGS = ["Continue", "Back", "Full name", "Email", "Booking summary"]


def edges(locator) -> tuple[float, float]:
    b = locator.bounding_box()
    assert b is not None, f"{locator} is not rendered"
    return b["x"], b["x"] + b["width"]


def test_arabic_view_is_rtl_mirrored_and_translated(page: Page):
    page.goto("/?lang=ar")
    html = page.locator("html")
    expect(html).to_have_attribute("dir", "rtl")
    expect(html).to_have_attribute("lang", "ar")

    # Locale-independent selectors: test ids, not English label text.
    name = page.get_by_test_id("full-name")
    label = page.locator("label[for='full-name']")
    assert name.evaluate("el => getComputedStyle(el).direction") == "rtl"
    assert abs(edges(label)[1] - edges(name)[1]) <= 2, "label does not start at the field's right edge"

    leftovers = [s for s in ENGLISH_UI_STRINGS if s in page.locator("body").inner_text()]
    assert not leftovers, f"untranslated UI strings in the RTL view: {leftovers}"

    name.fill("سارة الأحمد")
    page.get_by_test_id("email").fill("sara@example.com")
    page.get_by_test_id("details-continue").click()
    actions = page.locator("form:visible .actions button")
    expect(actions).to_have_count(2)
    xs = actions.evaluate_all("els => els.map(e => e.getBoundingClientRect().x)")
    # Mirrored row: the first action in DOM order is the right-most one.
    assert xs == sorted(xs, reverse=True), f"action order not mirrored: x positions {xs}"
```

When the requirement names an edge ("actions align to the right"), assert that edge
too; the checks above only prove mirroring. Also check: bidirectional content (emails,
order numbers, prices) does not scramble
(`dir="auto"`, `<bdi>`), numbers and currency formatted per locale as specified, icons
with direction (arrows, chevrons) mirrored, every error message translated.

## Browser state and persistence

```python
# tests/qa/test_qa_persistence.py
from playwright.sync_api import BrowserContext, Page, expect


def storage(page: Page) -> dict:
    return page.evaluate("() => Object.fromEntries(Object.entries(window.localStorage))")


def test_draft_survives_reload_and_a_new_tab(page: Page, context: BrowserContext):
    page.goto("/")
    page.get_by_label("Full name").fill("Lena Weber")
    page.get_by_label("Email").fill("lena@example.com")
    page.get_by_role("button", name="Continue").click()
    expect(page.get_by_role("heading", name="Address")).to_be_visible()
    assert storage(page), "no draft persisted"

    page.reload()
    expect(page.get_by_role("heading", name="Address")).to_be_visible()

    second = context.new_page()  # same profile, "returning later"
    second.goto("/")
    expect(second.get_by_role("heading", name="Address")).to_be_visible()


def test_corrupted_draft_does_not_break_the_app(page: Page):
    page.goto("/")
    keys = list(storage(page)) or ["booking-draft"]
    page.add_init_script(
        "for (const k of %s) { window.localStorage.setItem(k, '{not json'); }" % keys
    )
    errors = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    page.reload()
    expect(page.get_by_role("button", name="Continue")).to_be_visible()
    assert errors == []
```

Discover the real storage keys first (fill a step, read `storage(page)`), then cover:
reload on each step, resume never skips an incomplete step, data cleared after
completion, stale schema/corrupted values, two tabs editing the same draft.

## Console and page errors as a free oracle

```python
import pytest


@pytest.fixture
def js_errors(page):
    errors = []
    page.on("pageerror", lambda exc: errors.append(f"pageerror: {exc}"))
    page.on("console", lambda msg: errors.append(f"console.error: {msg.text}") if msg.type == "error" else None)
    yield errors


def test_happy_path_has_no_js_errors(page, js_errors):
    page.goto("/")
    # ... drive the journey ...
    assert js_errors == []
```

Expected `console.error` from deliberately failed requests (503 tests) are noise there;
apply this fixture to journeys without injected failures.

## Running and reproducing

```bash
qast exec pytest --group critical-journeys --label qa-frontend-journeys -- tests/qa/test_qa_recovery.py tests/qa/test_qa_network.py
qast reproduce --test "tests/qa/test_qa_network.py::test_slow_request_cannot_be_submitted_twice" --times 3
```

Screenshots and traces written to `$QAST_ARTIFACT_DIR` are hashed and linked to the
failing test automatically (file name contains the node id).
