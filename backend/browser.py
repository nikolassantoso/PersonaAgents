import os

from collections.abc import Iterator
from contextlib import contextmanager
from urllib.parse import urlencode

from playwright.sync_api import Page, sync_playwright
from steel import Steel
from steel.types import Session

@contextmanager
def open_persona_browser(url: str) -> Iterator[tuple[Session, Page]]:
    api_key = os.environ.get("STEEL_API_KEY")
    if not api_key:
        raise ValueError("STEEL_API_KEY environment variable is not set")

    with Steel(steel_api_key=api_key) as client:
        session = client.sessions.create()
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
                    page.goto(url, wait_until="domcontentloaded", timeout=60_000)

                    yield session, page
                finally:
                    browser.close()
        finally:
            client.sessions.release(session.id)