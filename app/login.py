"""Sign in, then hand the session to the recordings as auth.json.

Login is not a case. It is the door every case walks through, so it runs
before each one and writes the fresh session where the recordings already
look for it: ``recordings/auth.json``.

A case folder is ``recordings/<case>/``, so from there ``../auth.json`` is
this file. ``test-cases/auth.json`` is a convenience link to the same place.
Nothing is committed — the gitignore pattern for auth.json covers all of them.

The browser stays visible. Seeing the sign-in happen is the whole point, and
a session that silently failed to establish would surface much later as a
confusing failure inside an unrelated voucher case.
"""

import base64
import json
import time
from pathlib import Path
from typing import Any

from .config import settings

# The marketing site is served at the base URL, so the login route has to be
# reached explicitly — landing on the base URL is not evidence of being inside.
LOGIN_ROUTE = "/login/"

DEFAULT_RECORDINGS_DIR = Path("recordings")
AUTH_FILENAME = "auth.json"


def _decode_jwt(token: str) -> dict[str, Any] | None:
    """Read a JWT's claims without verifying the signature.

    Verification is the server's job. All this needs is the expiry, which the
    server has already signed — and if that expiry has passed, no request is
    going anywhere.

    A JWT is header.payload.signature; only the middle segment is read, and it
    is base64url without padding.
    """
    parts = token.split(".")
    if len(parts) < 2:
        return None
    payload = parts[1]
    payload += "=" * (-len(payload) % 4)
    try:
        claims = json.loads(base64.urlsafe_b64decode(payload))
    except (ValueError, TypeError):
        return None
    return claims if isinstance(claims, dict) else None


def auth_path(recordings_dir: Path | str = DEFAULT_RECORDINGS_DIR) -> Path:
    """Where the one system-wide session is written."""
    return Path(recordings_dir) / AUTH_FILENAME


def session_status(
    recordings_dir: Path | str = DEFAULT_RECORDINGS_DIR,
) -> dict[str, Any]:
    """Is the saved session still usable? Read-only, no browser.

    The tenant is single-active-session: every sign-in revokes every earlier
    one, and the access token lives about ten minutes. A case running on a
    dead session bounces to /login/ and screenshots the sign-in form — then
    exits 0 and reports itself as passed. Checking here is what stops that
    being reported as a green run.
    """
    path = auth_path(recordings_dir)
    if not path.is_file():
        return {"ok": False, "reason": f"no session at {path} — sign in has not run"}

    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {"ok": False, "reason": f"{path} is unreadable: {exc}"}

    token = next(
        (c.get("value", "") for c in state.get("cookies", []) if c.get("name") == "at"),
        "",
    )
    if not token:
        return {"ok": False, "reason": f"{path} carries no access token"}

    claims = _decode_jwt(token)
    if claims is None:
        return {"ok": False, "reason": "access token is malformed"}

    expires = claims.get("exp")
    if not isinstance(expires, (int, float)):
        return {"ok": False, "reason": "access token has no expiry"}

    remaining = expires - time.time()
    if remaining <= 0:
        return {"ok": False, "reason": "access token expired"}
    return {"ok": True, "seconds_left": round(remaining)}


def sign_in_and_save(
    recordings_dir: Path | str = DEFAULT_RECORDINGS_DIR,
) -> dict[str, Any]:
    """Open a visible browser, sign in from .env, save the session.

    Returns a flat dict the loop can branch on. Never raises: a failed sign-in
    is reported, not crashing, because it must not take the terminal down
    before the human has read why.
    """
    if not settings.username or not settings.password:
        return {
            "action": "auth",
            "ok": False,
            "detail": "no credentials in .env — set USERNAME and PASSWORD",
        }

    from playwright.sync_api import sync_playwright

    destination = auth_path(recordings_dir)
    destination.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False, slow_mo=settings.slow_mo_ms)
        try:
            context = browser.new_context()
            page = context.new_page()
            page.goto(settings.base_url.rstrip("/") + LOGIN_ROUTE, wait_until="domcontentloaded")

            email = page.locator("input[type=email]")
            password = page.locator("input[type=password]")
            # Wait rather than sample: the form may still be rendering after
            # goto, and a snapshot here reads a missing form as a login failure.
            email.first.wait_for(state="visible", timeout=15000)
            password.first.wait_for(state="visible", timeout=15000)

            email.first.fill(settings.username)
            password.first.fill(settings.password)

            submit = page.get_by_role("button", name="Sign in")
            try:
                submit.first.wait_for(state="visible", timeout=5000)
                submit.first.click()
            except Exception:  # noqa: BLE001 - no button is fine, Enter submits
                password.first.press("Enter")

            # Wait for the POST to settle rather than sleeping on a guess.
            page.wait_for_url(lambda url: "login" not in url, timeout=15000)

            context.storage_state(path=str(destination))
            where = page.url
        except Exception as exc:  # noqa: BLE001 - a refused sign-in is a report
            return {
                "action": "auth",
                "ok": False,
                "detail": f"{type(exc).__name__}: {exc}",
            }
        finally:
            browser.close()

    return {
        "action": "auth",
        "ok": True,
        "saved": str(destination),
        "url": where,
        "detail": "signed in",
    }


if __name__ == "__main__":
    # `uv run python -m app.login` — sign in and stop.
    #
    # The access token lives about ten minutes and the tenant is
    # single-active-session, so a session saved long before a recording is
    # already dead by the time codegen opens the page. Signing in immediately
    # before recording is what keeps --load-storage from dropping you on the
    # login form mid-flow.
    print(json.dumps(sign_in_and_save(), indent=2))
