from playwright.sync_api import expect


def test_long_list_and_progress(app_page):
    expect(app_page.get_by_text("Job 0", exact=True)).to_be_visible()
    app_page.get_by_text("Job 2", exact=True).click()
    expect(app_page.get_by_text("Chose Job 2")).to_be_visible()

    app_page.get_by_role("button", name="More").click()
    expect(app_page.get_by_text("50% uploaded")).to_be_visible()
    app_page.keyboard.press("Escape")
    expect(app_page.get_by_text("40% uploaded")).to_be_visible()


def test_copy_paste_through_the_system_clipboard(app_page):
    app_page.get_by_role("button", name="Copy").click()
    app_page.get_by_role("button", name="Paste").click()
    expect(app_page.get_by_text("Pasted: 40% uploaded")).to_be_visible()
