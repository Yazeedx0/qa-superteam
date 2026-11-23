"""Reference journeys for the web-checkout fixture (see docs/USER_JOURNEYS.md).

Expected on the shipped (defective) fixture:
  * test_recover_from_postal_code_error_and_complete_checkout  -> FAILS (WB-1)
  * test_promo_apply_then_remove_restores_total                -> FAILS (WB-3)
  * everything else                                            -> passes
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import Page, expect

ORDER_ID = re.compile(r"^ORD-\d+$")


def test_recover_from_postal_code_error_and_complete_checkout(checkout):
    page = checkout.page
    checkout.open().fill_contact()

    postal = page.get_by_test_id("postal-code")
    continue_button = page.get_by_test_id("shipping-continue")
    postal_error = page.locator("#postal-code-error")

    postal.fill("123")
    continue_button.click()
    expect(postal_error, "an invalid US ZIP code should show an inline error").to_contain_text("5-digit")
    expect(page.locator("#shipping-form"), "an invalid postal code must not advance the checkout").to_be_visible()

    postal.fill("94107")
    expect(postal_error, "correcting the postal code should clear the inline error").to_be_hidden()
    expect(
        continue_button,
        "after correcting the postal code to a valid value (94107) the Shipping 'Continue' button is still "
        "disabled, so the user cannot finish checkout without reloading the page",
    ).to_be_enabled(timeout=3_000)

    continue_button.click()
    expect(page.locator("#review"), "a corrected postal code should advance to Review").to_be_visible()
    page.get_by_test_id("place-order").click()
    expect(page.get_by_test_id("order-id"), "checkout should complete with an order id").to_have_text(ORDER_ID)


def test_promo_apply_then_remove_restores_total(checkout):
    page = checkout.page
    checkout.to_review(country="US", postal="94107")

    total = page.get_by_test_id("total")
    expect(page.get_by_test_id("subtotal")).to_have_text("$80.00")
    expect(page.get_by_test_id("shipping-cost")).to_have_text("$5.00")
    expect(total, "total before any promo should be subtotal + shipping").to_have_text("$85.00")

    page.get_by_test_id("promo-input").fill("SAVE10")
    page.get_by_test_id("promo-apply").click()
    expect(page.get_by_test_id("promo-badge")).to_contain_text("SAVE10")
    expect(page.get_by_test_id("discount"), "SAVE10 should take 10% off the $80.00 subtotal").to_have_text("-$8.00")
    expect(total, "total with SAVE10 applied").to_have_text("$77.00")

    page.get_by_test_id("promo-remove").click()
    expect(page.get_by_test_id("promo-badge"), "the applied-code badge should disappear").to_be_hidden()
    expect(page.get_by_test_id("promo-input"), "the promo field should be cleared").to_have_value("")
    expect(page.get_by_test_id("discount"), "the discount line should disappear").to_be_hidden()
    expect(
        total,
        "after removing SAVE10 the total must return to $85.00 (subtotal $80.00 + shipping $5.00) "
        "but it still includes the $8.00 discount",
    ).to_have_text("$85.00")


def test_arabic_locale_renders_right_to_left(checkout):
    page = checkout.page
    checkout.open("/?lang=ar")

    html = page.locator("html")
    expect(html, "?lang=ar must set dir=rtl on <html>").to_have_attribute("dir", "rtl")
    expect(html, "?lang=ar must set lang=ar on <html>").to_have_attribute("lang", "ar")
    expect(page.get_by_label("الاسم الكامل"), "Full name field should have an Arabic label").to_be_visible()
    expect(page.get_by_role("button", name="متابعة"), "Continue button should be translated").to_be_visible()
    direction = page.locator("#contact-form").evaluate("el => getComputedStyle(el).direction")
    assert direction == "rtl", f"form content should lay out right-to-left, computed direction was {direction!r}"

    checkout.fill_contact().fill_shipping(country="SA", postal="12345")
    expect(page.locator("#review h2")).to_have_text("راجع طلبك")
    expect(page.get_by_test_id("summary-shipping")).to_contain_text("المملكة العربية السعودية")


def _horizontal_overflow(page: Page) -> dict:
    return page.evaluate(
        """() => {
            const doc = document.documentElement;
            const width = doc.clientWidth;
            const offenders = [...document.querySelectorAll('body *')]
              .filter((el) => {
                const box = el.getBoundingClientRect();
                return box.width > 0 && (box.right > width + 1 || box.left < -1);
              })
              .slice(0, 5)
              .map((el) => el.tagName.toLowerCase() + (el.id ? '#' + el.id : ''));
            return { scrollWidth: doc.scrollWidth, clientWidth: width, offenders };
        }"""
    )


def _assert_fits(page: Page, where: str) -> None:
    metrics = _horizontal_overflow(page)
    assert metrics["scrollWidth"] <= metrics["clientWidth"], (
        f"horizontal scrolling at 375px on the {where}: scrollWidth={metrics['scrollWidth']} "
        f"> clientWidth={metrics['clientWidth']}; overflowing elements: {metrics['offenders']}"
    )


@pytest.mark.parametrize("query", ["/", "/?lang=ar"], ids=["en", "ar"])
def test_mobile_375_has_no_horizontal_overflow(new_page, make_checkout, query: str):
    page = new_page(viewport={"width": 375, "height": 812})
    flow = make_checkout(page).open(query)
    _assert_fits(page, "contact step")

    page.get_by_test_id("full-name").fill("Alexandria Konstantinopoulou-Whitfield")
    page.get_by_test_id("email").fill("not-an-email")
    page.get_by_test_id("contact-continue").click()
    expect(page.locator("#email-error")).to_be_visible()
    _assert_fits(page, "contact step with an inline error")

    flow.fill_contact(name="Alexandria Konstantinopoulou-Whitfield",
                      email="alexandria.konstantinopoulou@example-company.com")
    _assert_fits(page, "shipping step")

    flow.fill_shipping(country="SA", postal="12345")
    page.get_by_test_id("promo-input").fill("SAVE10")
    page.get_by_test_id("promo-apply").click()
    expect(page.get_by_test_id("promo-badge")).to_be_visible()
    _assert_fits(page, "review step with a promo applied")

    page.get_by_test_id("place-order").click()
    expect(page.get_by_test_id("order-id")).to_have_text(ORDER_ID)
    _assert_fits(page, "confirmation view")


@pytest.mark.parametrize("failure", ["network-error", "http-500"])
def test_place_order_failure_shows_banner_and_retry_succeeds(checkout, failure: str):
    page = checkout.page
    checkout.to_review()

    def fail(route):
        if failure == "network-error":
            route.abort("failed")
        else:
            route.fulfill(status=500, content_type="application/json", body='{"error": "unavailable"}')

    page.route("**/api/orders", fail)
    page.get_by_test_id("place-order").click()

    banner = page.get_by_test_id("order-error")
    expect(banner, f"a {failure} while placing the order should show an error banner").to_be_visible()
    expect(banner).to_contain_text("We couldn't place your order. Please try again.")
    expect(page.locator("#review"), "the user should stay on Review after a failed order").to_be_visible()
    expect(page.get_by_test_id("order-id")).to_be_hidden()

    page.unroute("**/api/orders")
    page.get_by_role("button", name="Retry").click()
    expect(page.get_by_test_id("order-id"), "Retry should place the order once the API recovers").to_have_text(ORDER_ID)
    expect(banner).to_be_hidden()
