from playwright.sync_api import expect


def test_increments(app_page):  # briochette.testing fixture: launches the built app, connects
    app_page.get_by_role("button", name="Increment").click()
    expect(app_page.get_by_text("Count: 1")).to_be_visible()
