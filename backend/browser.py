import os

from collections.abc import Iterator
from contextlib import contextmanager
from urllib.parse import urlencode

from playwright.sync_api import Error as PlaywrightError, Page, sync_playwright
from steel import Steel
from steel.types import Session

from page_access import PageAccessMonitor

@contextmanager
def open_persona_browser(url: str) -> Iterator[tuple[Session, Page, PageAccessMonitor]]:
    api_key = os.environ.get("STEEL_API_KEY")
    if not api_key:
        raise ValueError("STEEL_API_KEY environment variable is not set")

    solve_setting = os.environ.get("STEEL_SOLVE_CAPTCHA", "true").strip().lower()
    if solve_setting not in ("true", "false"):
        raise ValueError("STEEL_SOLVE_CAPTCHA must be true or false.")
    solve_captcha = solve_setting == "true"

    with Steel(steel_api_key=api_key) as client:
        session = client.sessions.create(solve_captcha=solve_captcha)
        try:
            separator = "&" if "?" in session.websocket_url else "?"
            connection_url = (
                f"{session.websocket_url}{separator}"
                f"{urlencode({'apiKey': api_key})}"
            )

            with sync_playwright() as playwright:
                browser = playwright.chromium.connect_over_cdp(connection_url)
                try: 
                    context = browser.contexts[0]
                    page = context.pages[0] if context.pages else context.new_page()
                    # Disable SDK retries so status polling stays within our wait budget.
                    captcha_client = client.with_options(max_retries=0)
                    access = PageAccessMonitor.from_environment(
                        page,
                        (lambda timeout: captcha_client.sessions.captchas.status(session.id, timeout=timeout))
                        if solve_captcha else None,
                    )
                    try:
                        try:
                            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
                        except PlaywrightError as exc:
                            access.navigation_failed(exc)
                        yield session, page, access
                    finally:
                        access.close()
                finally:
                    browser.close()
        finally:
            client.sessions.release(session.id)
