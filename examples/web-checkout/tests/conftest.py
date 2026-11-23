"""Shared fixtures for the checkout end-to-end suite.

* ``live_server``: the app + order API on a free port (one per session).
* ``browser``: a headless Chromium instance (one per session). If the Chromium
  build pinned by the installed Playwright package is missing, the newest
  Chromium already present in the Playwright browser cache is used instead
  (override with ``CHROMIUM_EXECUTABLE``).
* ``page``: a fresh browser context/page per test, with ``base_url`` set so
  tests can call ``page.goto("/")``.

If ``QAST_ARTIFACT_DIR`` is set, a full-page screenshot is written there for
every failing test as ``<sanitized node id>.png``.
"""

from __future__ import annotations

import os
import re
import threading
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from serve import make_server


@pytest.fixture(scope="session")
def live_server():
    server, base_url = make_server(port=0)
    thread = threading.Thread(target=server.serve_forever, name="checkout-server", daemon=True)
    thread.start()
    yield base_url
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def _cached_chromium() -> str | None:
    """Newest Chromium in the Playwright browser cache (headless shell preferred)."""
    root = Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or Path.home() / ".cache" / "ms-playwright")

    def revision(path: Path) -> int:
        return int(re.sub(r"\D", "", path.relative_to(root).parts[0]) or 0)

    patterns = (
        "chromium_headless_shell-*/chrome-headless-shell-*/chrome-headless-shell",
        "chromium-*/chrome-*/chrome",
    )
    for pattern in patterns:
        found = [path for path in root.glob(pattern) if os.access(path, os.X_OK)]
        if found:
            return str(max(found, key=revision))
    return None


def launch_chromium(playwright):
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
        browser = launch_chromium(playwright)
        yield browser
        browser.close()


@pytest.fixture
def page(browser, live_server):
    context = browser.new_context(base_url=live_server, viewport={"width": 1280, "height": 900})
    page = context.new_page()
    yield page
    context.close()


def _artifact_name(nodeid: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", nodeid).strip("_") or "test"


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item, call):
    report = yield
    artifact_dir = os.environ.get("QAST_ARTIFACT_DIR")
    already_captured = any(name == "screenshot" for name, _ in report.sections)
    if artifact_dir and report.failed and report.when in ("setup", "call") and not already_captured:
        page = item.funcargs.get("page")
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
