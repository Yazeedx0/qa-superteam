"""Automated accessibility checks (axe-core) for the web-checkout fixture.

Expected on the shipped (defective) fixture:
  * test_review_step_has_no_serious_axe_violations -> FAILS (WB-2, axe rule `label` on #promo-code)
  * test_step_has_no_serious_axe_violations[*]      -> passes
"""

from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

AXE_RELATIVE_PATH = Path("node_modules") / "axe-core" / "axe.min.js"
BLOCKING_IMPACTS = ("serious", "critical")


def _find_axe() -> Path | None:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / AXE_RELATIVE_PATH
        if candidate.is_file():
            return candidate
    return None


@pytest.fixture(scope="module")
def axe_path() -> Path:
    path = _find_axe()
    if path is None:
        pytest.skip(
            "axe-core is not installed: node_modules/axe-core/axe.min.js was not found above "
            f"{Path(__file__).parent}. Run `npm install` in the fixture root."
        )
    return path


def run_axe(page: Page, axe_path: Path) -> list[dict]:
    page.add_script_tag(path=str(axe_path))
    return page.evaluate(
        """async () => {
            const results = await axe.run(document, { resultTypes: ['violations'] });
            return results.violations.map((v) => ({
                id: v.id,
                impact: v.impact,
                help: v.help,
                targets: v.nodes.map((node) => node.target.join(' ')),
            }));
        }"""
    )


def blocking(violations: list[dict]) -> list[dict]:
    return [v for v in violations if v["impact"] in BLOCKING_IMPACTS]


def describe(violations: list[dict]) -> str:
    return "\n".join(
        f"  - {v['id']} ({v['impact']}): {v['help']} -> {', '.join(v['targets'])}" for v in violations
    )


def test_review_step_has_no_serious_axe_violations(checkout, axe_path: Path):
    checkout.to_review()
    expect(checkout.page.get_by_test_id("promo-input")).to_be_visible()

    violations = blocking(run_axe(checkout.page, axe_path))
    assert not violations, (
        "axe-core reported serious/critical accessibility violations on the Review step "
        "(promo code, totals, Place order):\n" + describe(violations)
    )


@pytest.mark.parametrize("step", ["contact", "shipping", "confirmation"])
def test_step_has_no_serious_axe_violations(checkout, axe_path: Path, step: str):
    page = checkout.page
    checkout.open()
    if step in ("shipping", "confirmation"):
        checkout.fill_contact()
    if step == "confirmation":
        checkout.fill_shipping()
        page.get_by_test_id("place-order").click()
        expect(page.get_by_test_id("order-id")).to_be_visible()

    violations = blocking(run_axe(page, axe_path))
    assert not violations, (
        f"axe-core reported serious/critical accessibility violations on the {step} step:\n" + describe(violations)
    )
