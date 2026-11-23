from playwright.sync_api import Page, expect


def test_back_preserves_entered_fields(page: Page):
    page.goto("/")
    page.get_by_label("Full name").fill("Omar Haddad")
    page.get_by_label("Email").fill("omar@example.com")
    page.get_by_role("button", name="Continue").click()

    page.get_by_label("Country").select_option("SA")
    page.get_by_label("Postal code").fill("12345")
    page.get_by_role("button", name="Back").click()

    expect(page.get_by_label("Full name")).to_have_value("Omar Haddad")
    expect(page.get_by_label("Email")).to_have_value("omar@example.com")

    page.get_by_role("button", name="Continue").click()
    expect(page.get_by_label("Country")).to_have_value("SA")
    expect(page.get_by_label("Postal code")).to_have_value("12345")


def test_reload_restores_draft_and_step(page: Page):
    page.goto("/")
    page.get_by_label("Full name").fill("Mei Chen")
    page.get_by_label("Email").fill("mei@example.com")
    page.get_by_role("button", name="Continue").click()
    page.get_by_label("Country").select_option("CA")
    page.get_by_label("Postal code").fill("M5V 2T6")

    page.reload()
    expect(page.get_by_role("heading", name="Shipping")).to_be_visible()
    expect(page.get_by_label("Country")).to_have_value("CA")
    expect(page.get_by_label("Postal code")).to_have_value("M5V 2T6")

    page.get_by_role("button", name="Continue").click()
    expect(page.get_by_role("heading", name="Review your order")).to_be_visible()

    page.reload()
    expect(page.get_by_role("heading", name="Review your order")).to_be_visible()
    expect(page.get_by_test_id("summary-contact")).to_contain_text("Mei Chen")
    expect(page.get_by_test_id("summary-shipping")).to_contain_text("M5V 2T6")
