from playwright.sync_api import expect


def test_add_check_and_delete(app_page):
    box = app_page.get_by_role("textbox", name="New todo")
    for text in ["Buy milk", "Feed cat"]:
        box.fill(text)
        box.press("Enter")
    expect(app_page.get_by_text("2 of 2 left")).to_be_visible()

    app_page.get_by_role("checkbox", name="Buy milk").check()
    expect(app_page.get_by_text("1 of 2 left")).to_be_visible()

    app_page.get_by_role("button", name="Delete Buy milk").click()
    expect(app_page.get_by_role("checkbox")).to_have_count(1)
