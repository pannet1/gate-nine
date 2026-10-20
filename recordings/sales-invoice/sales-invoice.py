import re
from playwright.sync_api import Playwright, sync_playwright, expect


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False, slow_mo=3000)
    context = browser.new_context(storage_state="../auth.json")
    page = context.new_page()
    page.goto("https://rachis.co.in/login/")
    page.wait_for_timeout(3000)
    page.screenshot(path="screenshot.png")
    page.close()

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
