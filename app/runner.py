from pathlib import Path

from playwright.async_api import async_playwright

from .config import Settings
from .events import append_event


async def open_login_page(
    settings: Settings,
    run_dir: Path,
    *,
    test_id: str = "manual-login",
) -> Path:
    """Open Rachis and fill login fields, stopping before any business action.

    The exact login selectors must be confirmed against the tenant UI before
    this function is used in a voucher test. It deliberately does not submit
    a voucher or mark a test result.
    """
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=settings.headless)
        page = await browser.new_page()
        await page.goto(settings.rachis_base_url, wait_until="domcontentloaded")
        append_event(settings.event_log_path, test_id=test_id, action="open_url", details={"url": settings.rachis_base_url})

        # These selectors are intentionally conservative placeholders until a
        # human confirms the live tenant's form fields.
        if settings.rachis_username and await page.locator("input[type=email], input[name=username]").count():
            await page.locator("input[type=email], input[name=username]").first.fill(settings.rachis_username)
        if settings.rachis_password and await page.locator("input[type=password], input[name=password]").count():
            await page.locator("input[type=password], input[name=password]").first.fill(settings.rachis_password)

        screenshot = run_dir / "login" / "screenshot.png"
        screenshot.parent.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=str(screenshot), full_page=True)
        append_event(settings.event_log_path, test_id=test_id, action="capture_screenshot", details={"path": str(screenshot)})
        await browser.close()
        return screenshot

