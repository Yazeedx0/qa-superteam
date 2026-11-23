from playwright.sync_api import Page, expect


def test_invalid_email_shows_inline_error(page: Page):
    page.goto("/")
    page.get_by_label("Full name").fill("Sam Rivera")
    email = page.get_by_label("Email")
    email.fill("sam.example.com")
    page.get_by_role("button", name="Continue").click()

    error = page.locator("#email-error")
    expect(error).to_be_visible()
    expect(error).to_contain_text("valid email address")
    expect(email).to_have_attribute("aria-invalid", "true")
    expect(page.get_by_role("heading", name="Contact details")).to_be_visible()
