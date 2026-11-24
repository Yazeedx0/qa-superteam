# axe-core inside Playwright tests, keyboard and focus checks

`qast exec axe` scans pages as they load. Single-page apps hide most of their UI behind
interaction (later checkout steps, error states, dialogs, RTL views). Reach those states
with Playwright, inject axe-core, and write the raw results into `$QAST_ARTIFACT_DIR` so
they become hashed evidence linked to the test.

Rules for every snippet below:

- axe-core comes from the project (`node_modules/axe-core/axe.min.js`) or `QAST_AXE_PATH`.
  If it is missing the scan is **BLOCKED**: the helper skips the test with a reason that
  starts with `BLOCKED:` and the summary reports BLOCKED, never "no violations".
- Violations fail the test (the impacts listed in `FAIL_ON`, from the project's stated
  target; WCAG AA conformance means every impact). `incomplete` results never pass or
  fail: they are written to the JSON and reported as needing manual review (INCONCLUSIVE).
- Name result files after the node id so qast links them to the test.

## Python (pytest + sync Playwright)

```python
# tests/qa/a11y_helpers.py
import json
import os
import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AXE_PATH = Path(os.environ.get("QAST_AXE_PATH") or PROJECT_ROOT / "node_modules" / "axe-core" / "axe.min.js")
WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]
FAIL_ON = {"critical", "serious", "moderate", "minor"}  # narrow only if the project's target says so


def _artifact_name(nodeid: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", nodeid).strip("_")


def axe_scan(page, request, state: str, tags=WCAG_TAGS) -> dict:
    """Run axe on the current page state; save raw results as evidence; return them."""
    if not AXE_PATH.exists():
        pytest.skip(f"BLOCKED: axe-core not found at {AXE_PATH} (install axe-core in the project or set QAST_AXE_PATH)")
    page.add_script_tag(path=str(AXE_PATH))
    results = page.evaluate(
        """async (tags) => await axe.run(document, {
               runOnly: {type: 'tag', values: tags},
               resultTypes: ['violations', 'incomplete'],
           })""",
        tags,
    )
    summary = {
        "state": state,
        "url": page.url,
        "viewport": page.viewport_size,
        "axe_version": results["testEngine"]["version"],
        "tags": tags,
        "violations": results["violations"],
        "incomplete": results["incomplete"],
    }
    out = os.environ.get("QAST_ARTIFACT_DIR")
    if out:
        path = Path(out) / f"{_artifact_name(request.node.nodeid)}-axe-{state}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def blocking_violations(summary: dict) -> list[str]:
    return [
        f"{v['id']} [{v['impact']}] {v['help']}: " + ", ".join(" ".join(n["target"]) for n in v["nodes"][:5])
        for v in summary["violations"]
        if v["impact"] in FAIL_ON
    ]
```

```python
# tests/qa/test_qa_a11y_states.py
import pytest
from playwright.sync_api import Page, expect

from a11y_helpers import axe_scan, blocking_violations


def go_to_review_step(page: Page):
    page.goto("/")
    page.get_by_label("Full name").fill("Noor Haddad")
    page.get_by_label("Email").fill("noor@example.com")
    page.get_by_role("button", name="Continue").click()
    page.get_by_label("Postal code").fill("10115")
    page.get_by_role("button", name="Continue").click()
    expect(page.get_by_role("heading", name="Review your booking")).to_be_visible()


def test_details_error_state(page: Page, request):
    page.goto("/")
    page.get_by_role("button", name="Continue").click()  # submit empty form
    expect(page.get_by_label("Email")).to_have_attribute("aria-invalid", "true")
    summary = axe_scan(page, request, "details-errors")
    assert not blocking_violations(summary), blocking_violations(summary)


def test_review_step(page: Page, request):
    go_to_review_step(page)
    summary = axe_scan(page, request, "review")
    assert not blocking_violations(summary), blocking_violations(summary)


@pytest.mark.parametrize("width", [375])
def test_details_step_rtl_mobile(page: Page, request, width):
    page.set_viewport_size({"width": width, "height": 812})
    page.goto("/?lang=ar")
    expect(page.locator("html")).to_have_attribute("lang", "ar")
    summary = axe_scan(page, request, f"details-rtl-{width}")
    assert not blocking_violations(summary), blocking_violations(summary)
```

The test file imports the helper as a top-level module (`from a11y_helpers import ...`),
which works with pytest's default `rootdir`-based import mode when `tests/qa/` has no
`__init__.py`. If the project uses packages for tests, use a relative import instead.

Run: `qast exec pytest --group accessibility --label qa-a11y-states -- tests/qa/test_qa_a11y_states.py`

## TypeScript (Playwright Test)

```ts
// tests/qa/a11y.qa.spec.ts
import { expect, test, type Page, type TestInfo } from '@playwright/test';
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

// qast runs Playwright from the project root; no require/import.meta needed (CJS and ESM).
const AXE_PATH = process.env.QAST_AXE_PATH ?? join(process.cwd(), 'node_modules', 'axe-core', 'axe.min.js');
const WCAG_TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'];
const FAIL_ON = new Set(['critical', 'serious', 'moderate', 'minor']);

async function axeScan(page: Page, testInfo: TestInfo, state: string) {
  test.skip(!existsSync(AXE_PATH), 'BLOCKED: axe-core not found (install axe-core in the project or set QAST_AXE_PATH)');
  await page.addScriptTag({ content: readFileSync(AXE_PATH, 'utf8') });
  const results = await page.evaluate(async (tags) =>
    // @ts-expect-error axe is injected at runtime
    await window.axe.run(document, { runOnly: { type: 'tag', values: tags }, resultTypes: ['violations', 'incomplete'] }),
  WCAG_TAGS);
  const payload = JSON.stringify({ state, url: page.url(), viewport: page.viewportSize(), tags: WCAG_TAGS,
    violations: results.violations, incomplete: results.incomplete }, null, 2);
  await testInfo.attach(`axe-${state}`, { body: payload, contentType: 'application/json' });
  if (process.env.QAST_ARTIFACT_DIR) {
    writeFileSync(join(process.env.QAST_ARTIFACT_DIR, `${testInfo.titlePath.join('-').replace(/[^A-Za-z0-9_.-]+/g, '_')}-axe-${state}.json`), payload);
  }
  return results as { violations: { id: string; impact: string; help: string }[] };
}

test('review step has no WCAG A/AA violations', async ({ page }, testInfo) => {
  await page.goto('/');
  await page.getByLabel('Full name').fill('Noor Haddad');
  await page.getByLabel('Email').fill('noor@example.com');
  await page.getByRole('button', { name: 'Continue' }).click();
  await page.getByLabel('Postal code').fill('10115');
  await page.getByRole('button', { name: 'Continue' }).click();
  await expect(page.getByRole('heading', { name: 'Review your booking' })).toBeVisible();
  const results = await axeScan(page, testInfo, 'review');
  const blocking = results.violations.filter((v) => FAIL_ON.has(v.impact)).map((v) => `${v.id} [${v.impact}]`);
  expect(blocking).toEqual([]);
});
```

Resolving axe from `process.cwd()` works in CommonJS and ESM projects alike (mixing
`require` and `import.meta` in a spec breaks Playwright's loader). `@axe-core/playwright`
is equivalent if the project already depends on it.

## Keyboard operation and focus

```python
# tests/qa/test_qa_keyboard.py
from playwright.sync_api import Page, expect

ACTIVE = """() => {
  const e = document.activeElement;
  if (!e || e === document.body) return null;
  return e.getAttribute('data-testid') || e.id || e.tagName.toLowerCase();
}"""
FOCUS_STYLE = """el => { const s = getComputedStyle(el);
  return [s.outlineStyle, s.outlineWidth, s.outlineColor, s.boxShadow, s.borderColor, s.backgroundColor].join('|'); }"""


def tab_order(page: Page, presses: int) -> list:
    order = []
    for _ in range(presses):
        page.keyboard.press("Tab")
        order.append(page.evaluate(ACTIVE))
    return order


def test_details_step_is_operable_by_keyboard(page: Page):
    page.goto("/")
    order = tab_order(page, 6)
    # Oracle: logical order = visual order of the form; adjust to the page under test.
    assert order.index("full-name") < order.index("email") < order.index("details-continue"), order

    page.get_by_label("Full name").focus()
    page.keyboard.type("Noor Haddad")
    page.keyboard.press("Tab")
    page.keyboard.type("noor@example.com")
    page.keyboard.press("Enter")
    # Requirement-dependent: focus moves to the new step's heading.
    expect(page.get_by_role("heading", name="Address")).to_be_focused()


def test_primary_action_has_a_visible_focus_indicator(page: Page):
    page.goto("/")
    button = page.get_by_role("button", name="Continue")
    unfocused = button.evaluate(FOCUS_STYLE)
    for _ in range(20):
        page.keyboard.press("Tab")
        if button.evaluate("el => el === document.activeElement"):
            break
    else:
        raise AssertionError("Continue never received keyboard focus")
    assert button.evaluate(FOCUS_STYLE) != unfocused, "no style change on keyboard focus"
```

- A changed style is necessary, not sufficient: whether the indicator is *visible enough*
  (contrast ≥ 3:1, not obscured by sticky headers, WCAG 2.4.11) stays a manual check.
- Keyboard trap check: from inside a widget/dialog, Tab and Shift+Tab must eventually
  reach elements outside it (or Escape must close a modal and return focus to the
  opener).
- Use real key presses (`page.keyboard.press`), not `.focus()`, when the oracle is
  keyboard reachability.

## Automatable approximations of manual checks

```python
REFLOW_OVERFLOW = "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
TEXT_SPACING_CSS = (
    "* { line-height: 1.5 !important; letter-spacing: 0.12em !important; word-spacing: 0.16em !important; }"
    " p { margin-bottom: 2em !important; }"
)
CLIPPED = """() => [...document.querySelectorAll('body *')].filter(e => {
  const s = getComputedStyle(e);
  const hides = [s.overflow, s.overflowX, s.overflowY].includes('hidden');
  return hides && e.innerText && e.innerText.trim() &&
         (e.scrollWidth > e.clientWidth + 1 || e.scrollHeight > e.clientHeight + 1);
}).map(e => e.tagName.toLowerCase() + (e.id ? '#' + e.id : ''))"""


def test_reflow_at_320_css_px(page):              # approximates WCAG 1.4.10 (400 % zoom)
    page.set_viewport_size({"width": 320, "height": 256})
    page.goto("/")
    assert page.evaluate(REFLOW_OVERFLOW) <= 0


def test_text_spacing_does_not_clip(page):        # approximates WCAG 1.4.12
    page.goto("/")
    page.add_style_tag(content=TEXT_SPACING_CSS)
    assert page.evaluate(CLIPPED) == []
```

These are evidence for or against a criterion, not conformance. A pass here still leaves
the manual check open (see `manual-checklist.md`); a failure is a real finding after you
confirm the clipped/overflowing element in the screenshot.
