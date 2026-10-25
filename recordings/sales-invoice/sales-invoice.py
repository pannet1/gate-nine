import re
from playwright.sync_api import Playwright, sync_playwright, expect


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False, slow_mo=3000)
    context = browser.new_context(storage_state="../auth.json")
    page = context.new_page()
    page.goto("https://rachis.co.in/accounting/sales-invoices/")
    page.get_by_test_id("action-new").click()

    # Customer: type to search, then click the option to bind it.
    # ArrowDown+Enter does not select — the value stays unbound.
    customer = page.get_by_placeholder("Search customer…")
    customer.click()
    customer.fill("arun")
    page.get_by_role("option", name="Arun Exports").click()

    # Line item: same shape. Binding the item fills Rate from the item record.
    item = page.get_by_placeholder("Search item…")
    item.click()
    item.fill("coconut")
    page.get_by_role("option", name=re.compile(r"^\s*Coconut\b")).click()

    # Qty is the second input in the line row; Rate is already 100.00.
    row = page.locator("table tbody tr").first
    row.locator("input").nth(1).fill("2")
    row.locator("input").nth(1).press("Tab")

    # Screenshot after the customer and line are bound, not before — the form
    # is what this case exists to prove.
    page.wait_for_timeout(3000)
    page.screenshot(path="screenshot.png")

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
