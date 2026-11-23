"""Self-contained fixtures for the web-checkout reference (oracle) tests.

These tests are copied into ``<fixture root>/tests/qa/`` by ``verify_oracle.sh``
but do not rely on the project's own ``tests/conftest.py``: the server, browser
and page fixtures and the screenshot-on-failure hook are duplicated here.
"""

from __future__ import annotations

import os
import re
import sys
import threading
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect, sync_playwright


def _find_fixture_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "serve.py").is_file() and (parent / "public" / "index.html").is_file():
            return parent
    raise RuntimeError("could not locate the web-checkout fixture root (serve.py) above " + __file__)


FIXTURE_ROOT = _find_fixture_root()
if str(FIXTURE_ROOT) not in sys.path:
    sys.path.insert(0, str(FIXTURE_ROOT))

from serve import make_server  # noqa: E402

expect.set_options(timeout=5_000)


# --------------------------------------------------------------- server/browser


@pytest.fixture(scope="session")
def live_server():
    server, base_url = make_server(port=0)
    thread = threading.Thread(target=server.serve_forever, name="checkout-oracle-server", daemon=True)
    thread.start()
    yield base_url
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def _cached_chromium() -> str | None:
    root = Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or Path.home() / ".cache" / "ms-playwright")

    def revision(path: Path) -> int:
        return int(re.sub(r"\D", "", path.relative_to(root).parts[0]) or 0)

    for pattern in (
        "chromium_headless_shell-*/chrome-headless-shell-*/chrome-headless-shell",
        "chromium-*/chrome-*/chrome",
    ):
        found = [path for path in root.glob(pattern) if os.access(path, os.X_OK)]
        if found:
            return str(max(found, key=revision))
    return None


def _launch_chromium(playwright):
    explicit = os.environ.get("CHROMIUM_EXECUTABLE")
    if explicit:
        return playwright.chromium.launch(headless=True, executable_path=explicit)
    try:
        return playwright.chromium.launch(headless=True)
    except Exception as exc:
        fallback = _cached_chromium()
        if "Executable doesn't exist" not in str(exc) or fallback is None:
            raise
        return playwright.chromium.launch(headless=True, executable_path=fallback)


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as playwright:
        browser = _launch_chromium(playwright)
        yield browser
        browser.close()


@pytest.fixture
def new_page(browser, live_server):
    """Factory: ``new_page(viewport=..., locale=...)`` -> Page in a fresh context."""
    contexts = []

    def factory(**context_options) -> Page:
        context_options.setdefault("viewport", {"width": 1280, "height": 900})
        context = browser.new_context(base_url=live_server, **context_options)
        contexts.append(context)
        created = context.new_page()
        factory.pages.append(created)
        return created

    factory.pages = []
    yield factory
    for context in contexts:
        context.close()


@pytest.fixture
def page(new_page) -> Page:
    return new_page()


# ------------------------------------------------------------------ journeys


class Checkout:
    """Drives the checkout through stable data-testid selectors (language-agnostic)."""

    def __init__(self, page: Page):
        self.page = page

    def open(self, query: str = "/") -> "Checkout":
        self.page.goto(query)
        expect(self.page.locator("#contact-form")).to_be_visible()
        return self

    def fill_contact(self, name: str = "Priya Natarajan", email: str = "priya@example.com") -> "Checkout":
        self.page.get_by_test_id("full-name").fill(name)
        self.page.get_by_test_id("email").fill(email)
        self.page.get_by_test_id("contact-continue").click()
        expect(self.page.locator("#shipping-form"), "contact step should advance to shipping").to_be_visible()
        return self

    def fill_shipping(self, country: str = "US", postal: str = "94107") -> "Checkout":
        self.page.get_by_test_id("country").select_option(country)
        self.page.get_by_test_id("postal-code").fill(postal)
        self.page.get_by_test_id("shipping-continue").click()
        expect(self.page.locator("#review"), "shipping step should advance to review").to_be_visible()
        return self

    def to_review(self, country: str = "US", postal: str = "94107") -> "Checkout":
        return self.open().fill_contact().fill_shipping(country, postal)


@pytest.fixture
def make_checkout():
    """Factory: ``make_checkout(page)`` -> Checkout driver for a page from ``new_page``."""
    return Checkout


@pytest.fixture
def checkout(page) -> Checkout:
    return Checkout(page)


# ------------------------------------------------------ screenshot on failure


def _artifact_name(nodeid: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", nodeid).strip("_") or "test"


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item, call):
    report = yield
    artifact_dir = os.environ.get("QAST_ARTIFACT_DIR")
    already_captured = any(name == "screenshot" for name, _ in report.sections)
    if artifact_dir and report.failed and report.when in ("setup", "call") and not already_captured:
        page = item.funcargs.get("page")
        factory = item.funcargs.get("new_page")
        if page is None and factory is not None and factory.pages:
            page = factory.pages[-1]
        if page is not None and not page.is_closed():
            target = Path(artifact_dir)
            target.mkdir(parents=True, exist_ok=True)
            path = target / f"{_artifact_name(item.nodeid)}.png"
            try:
                page.screenshot(path=str(path), full_page=True)
                report.sections.append(("screenshot", str(path)))
            except Exception as exc:  # never mask the real failure
                report.sections.append(("screenshot", f"could not capture: {exc}"))
    return report
