import re
from playwright.sync_api import Playwright, sync_playwright, expect


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context(storage_state="auth.json")
    page = context.new_page()
    page.goto("https://rachis.co.in/accounting/sales-invoices/new/")
    page.get_by_role("group").filter(has_text="Customer*Invoice date*Due").get_by_label("Open options").click()
    page.get_by_role("button", name="Close options").click()
    page.get_by_text("NotesNotesTerms & conditionsTerms & conditionsSubtotal0.00Total0.00").click()
    page.close()

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
