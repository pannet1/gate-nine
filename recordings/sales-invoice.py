import re
from playwright.sync_api import Playwright, sync_playwright, expect


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context(storage_state="recordings/auth.json")
    page = context.new_page()
    page.goto("https://rachis.co.in/accounting/sales-invoices/")
    page.get_by_test_id("action-new").click()
    page.get_by_role("textbox", name="Customer").click()
    page.get_by_role("button", name="Close options").click()
    page.get_by_role("textbox", name="Customer").click()
    page.get_by_role("textbox", name="Customer").fill("Arim Exports")
    page.get_by_role("textbox", name="Customer").press("Tab")
    page.get_by_role("textbox", name="Invoice date").press("Tab")
    page.get_by_role("textbox", name="Due date").press("Shift+Tab")
    page.get_by_role("textbox", name="Invoice date").fill("23")
    page.get_by_role("button", name="Open calendar").first.click()
    page.get_by_role("gridcell", name="23/10/").click()
    page.get_by_role("button", name="Open calendar").nth(1).click()
    page.get_by_role("gridcell", name="23/10/").click()
    page.get_by_role("textbox", name="Item").click()
    page.get_by_role("textbox", name="Item").fill("cocunt")
    page.get_by_role("textbox", name="Item").press("Tab")
    page.get_by_role("textbox", name="Item").click()
    page.get_by_role("textbox", name="Item").press("Tab")
    page.get_by_role("textbox", name="Quantity").fill("2")
    page.get_by_role("textbox", name="Quantity").press("Tab")
    page.get_by_role("textbox", name="Rate").press("Tab")
    page.get_by_role("button", name="Post").click()
    page.get_by_role("group").filter(has_text="Customer*Customer is").get_by_label("Open options").click()
    page.get_by_role("textbox", name="Customer").fill("ar")
    page.get_by_text("Customer*").click()
    page.get_by_role("button", name="Save draft").click()
    page.get_by_role("button", name="Post").click()
    page.get_by_text("← Back to Sales InvoicesSales Invoice—NewSave draftPostPlease fix the").click()
    page.get_by_text("← Back to Sales InvoicesSales Invoice—NewSave draftPostPlease fix the").click()
    page.get_by_role("button", name="Post").click()

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
