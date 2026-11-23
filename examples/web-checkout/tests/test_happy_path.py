import re

from playwright.sync_api import Page, expect


def fill_contact(page: Page, name: str = "Dana Whitfield", email: str = "dana@example.com") -> None:
    page.get_by_label("Full name").fill(name)
    page.get_by_label("Email").fill(email)
    page.get_by_role("button", name="Continue").click()


def test_cart_lists_items_with_prices(page: Page):
    page.goto("/")

    cart = page.get_by_test_id("cart")
    expect(cart).to_contain_text("Everyday Canvas Tote")
    expect(cart).to_contain_text("$48.00")
    expect(cart).to_contain_text("Ceramic Pour-Over Set")
    expect(cart).to_contain_text("$32.00")
    expect(page.get_by_test_id("subtotal")).to_have_text("$80.00")


def test_checkout_with_valid_details_shows_confirmation(page: Page):
    page.goto("/")
    fill_contact(page)

    expect(page.get_by_role("heading", name="Shipping")).to_be_visible()
    page.get_by_label("Country").select_option("US")
    page.get_by_label("Postal code").fill("94107")
    page.get_by_role("button", name="Continue").click()

    expect(page.get_by_role("heading", name="Review your order")).to_be_visible()
    expect(page.get_by_test_id("summary-contact")).to_contain_text("Dana Whitfield")
    expect(page.get_by_test_id("summary-contact")).to_contain_text("dana@example.com")
    expect(page.get_by_test_id("summary-shipping")).to_contain_text("94107")
    expect(page.get_by_test_id("shipping-cost")).to_have_text("$5.00")
    expect(page.get_by_test_id("total")).to_have_text("$85.00")

    page.get_by_role("button", name="Place order").click()

    expect(page.get_by_role("heading", name="Your order is confirmed")).to_be_visible()
    expect(page.get_by_test_id("order-id")).to_have_text(re.compile(r"^ORD-\d+$"))
    expect(page.get_by_test_id("confirm-email")).to_have_text("dana@example.com")


def test_canadian_address_uses_canadian_shipping_rate(page: Page):
    page.goto("/")
    fill_contact(page, name="Luc Tremblay", email="luc@example.ca")

    page.get_by_label("Country").select_option("CA")
    page.get_by_label("Postal code").fill("k1a0b1")
    page.get_by_role("button", name="Continue").click()

    expect(page.get_by_test_id("summary-shipping")).to_contain_text("Canada")
    expect(page.get_by_test_id("summary-shipping")).to_contain_text("K1A 0B1")
    expect(page.get_by_test_id("shipping-cost")).to_have_text("$12.00")
    expect(page.get_by_test_id("total")).to_have_text("$92.00")
