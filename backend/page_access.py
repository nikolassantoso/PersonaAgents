"""Conservative, per-page access checks. Unknown never means proven usable."""

import math
import os
import re
import time
from collections.abc import Callable, Sequence
from typing import Any
from urllib.parse import urldefrag

from playwright.sync_api import Error as PlaywrightError, Page, Request, Response

from models import PageAccessCheck

CaptchaStatusReader = Callable[[float], Sequence[Any]]
ACTIVE_CAPTCHA_STATUSES = {"detected", "solving", "validating"}
FAILED_CAPTCHA_STATUSES = {"failed_to_detect", "failed_to_solve", "validation_failed"}


def positive_setting(name: str, default: float) -> float:
    value = float(os.environ.get(name, default))
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a positive, finite number.")
    return value


def document_url(url: str) -> str:
    return urldefrag(url)[0]


def field(item: Any, name: str, default: Any = None) -> Any:
    """Steel uses models for page states and dictionaries for task payloads."""
    if isinstance(item, dict):
        camel_name = re.sub(r"_([a-z])", lambda match: match[1].upper(), name)
        return item.get(name, item.get(camel_name, default))
    return getattr(item, name, default)


def classify_page(snapshot: dict, status: int | None, challenged: bool) -> PageAccessCheck:
    report = PageAccessCheck(url=snapshot["url"], title=snapshot["title"], http_status=status)
    text = " ".join(snapshot["text"].lower().split())
    headings = [" ".join(h.lower().split()).rstrip(".! ") for h in snapshot["headings"]]
    title = " ".join(snapshot["title"].lower().split()).rstrip(".! ")
    block_headings = {"sorry, you have been blocked", "access denied", "request blocked", "you have been blocked"}
    block_heading = bool(headings and headings[0] in block_headings) or title in block_headings
    # A permissions/login page or an article about Cloudflare is not a firewall block.
    block_evidence = any(marker in text for marker in (
        "cloudflare ray id", "your ip has been blocked", "your ip address has been blocked",
        "automated requests", "request blocked by the security", "security service to protect itself",
    ))
    if block_heading and block_evidence:
        report.state = "blocked"
        report.failure_reason = "website_blocked"
        report.evidence.append("An access-denied heading is accompanied by firewall or automated-request denial text.")
        return report

    challenge_headings = {"just a moment", "verify you are human", "checking your browser", "security verification"}
    challenge_heading = title in challenge_headings or any(h in challenge_headings for h in headings[:2])
    if challenged or (challenge_heading and snapshot["challenge_marker"]):
        report.state = "challenge"
        report.evidence.append(
            "The main document response has cf-mitigated: challenge."
            if challenged else "A verification heading and challenge-page markup are visible."
        )
    elif status is not None and status >= 400:
        report.state = "http_error"
        report.evidence.append(f"The main document returned HTTP {status}; this alone does not prove an automation block.")
    if snapshot["captcha_widget"]:
        report.evidence.append("A CAPTCHA widget is present; its presence alone does not establish an access block.")
    if not text:
        report.evidence.append("The document has no visible text yet; it may still be loading.")
    return report


class PageAccessMonitor:
    def __init__(
        self, page: Page, captcha_status: CaptchaStatusReader | None = None,
        *, wait_timeout: float = 60, poll_interval: float = 2,
    ):
        if not math.isfinite(wait_timeout) or wait_timeout < 0:
            raise ValueError("wait_timeout must be finite and nonnegative.")
        if not math.isfinite(poll_interval) or poll_interval <= 0:
            raise ValueError("poll_interval must be positive and finite.")
        self.page = page
        self.captcha_status = captcha_status
        self.wait_timeout = wait_timeout
        self.poll_interval = poll_interval
        self._request: Request | None = None
        self._response_url = ""
        self._http_status: int | None = None
        self._challenged = False
        self._navigation_error: str | None = None
        self._crashed = False
        self._document_started = time.time() * 1000
        self._steel_page_id: str | None = None
        self._listeners = {
            "request": self._on_request, "response": self._on_response,
            "requestfailed": self._on_request_failed, "crash": self._on_crash,
        }
        for event, handler in self._listeners.items():
            page.on(event, handler) # type: ignore

    @classmethod
    def from_environment(cls, page: Page, captcha_status: CaptchaStatusReader | None = None):
        return cls(
            page, captcha_status,
            wait_timeout=positive_setting("CAPTCHA_WAIT_TIMEOUT_SECONDS", 60),
            poll_interval=positive_setting("CAPTCHA_POLL_INTERVAL_SECONDS", 2),
        )

    def close(self) -> None:
        for event, handler in self._listeners.items():
            self.page.remove_listener(event, handler)

    def _on_crash(self, *_args) -> None:
        self._crashed = True

    def _on_request(self, request: Request) -> None:
        if request.is_navigation_request() and request.frame == self.page.main_frame:
            self._request = request
            self._response_url = ""
            self._http_status = None
            self._challenged = False
            self._navigation_error = None
            self._document_started = time.time() * 1000

    def _on_response(self, response: Response) -> None:
        if response.request == self._request:
            self._response_url = response.url
            self._http_status = response.status
            self._challenged = response.headers.get("cf-mitigated") == "challenge"
            self._navigation_error = None

    def _on_request_failed(self, request: Request) -> None:
        if request == self._request:
            # Record browser error codes, never arbitrary exception text containing credentials.
            self._navigation_error = request.failure or "Main document request failed."

    def navigation_failed(self, exc: Exception) -> None:
        self._navigation_error = f"Navigation did not complete ({type(exc).__name__})."

    def _snapshot(self) -> dict:
        return self.page.evaluate("""() => {
            const visible = el => {
                const rect = el.getBoundingClientRect();
                const style = getComputedStyle(el);
                return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
            };
            const anyVisible = selector => [...document.querySelectorAll(selector)].some(visible);
            return {
                url: location.href, title: document.title,
                text: (document.body?.innerText || '').slice(0, 12000),
                headings: [...document.querySelectorAll('h1, h2')].filter(visible).slice(0, 3).map(el => el.innerText),
                challenge_marker: anyVisible('#challenge-running, #challenge-stage, #challenge-form') ||
                    !!document.querySelector('script[src*="/cdn-cgi/challenge-platform/"]'),
                captcha_widget: anyVisible('iframe[src*="recaptcha"], iframe[src*="hcaptcha"], iframe[src*="challenges.cloudflare.com"], .g-recaptcha, .h-captcha, .cf-turnstile')
            };
        }""")

    def _captcha_progress(self, report: PageAccessCheck, timeout: float) -> bool | None:
        """Return active solving for this document only; idle/solved is not readiness."""
        if self.captcha_status is None:
            return False
        try:
            states = self.captcha_status(timeout)
            matching = [state for state in states if document_url(field(state, "url", "")) == document_url(report.url)]
            if self._steel_page_id is not None:
                matching = [state for state in matching if field(state, "page_id") == self._steel_page_id]
            if len(matching) != 1:
                if len(matching) > 1:
                    report.evidence.append("Steel CAPTCHA status is ambiguous across tabs at the same URL.")
                    return None
                return False
            state = matching[0]
            self._steel_page_id = field(state, "page_id")
            tasks = []
            for task in field(state, "tasks", []):
                task_url = field(task, "url")
                if task_url and document_url(task_url) != document_url(report.url):
                    continue
                task_page = field(task, "page_id")
                if task_page and task_page != self._steel_page_id:
                    continue
                detected = field(task, "detection_time") or field(task, "created")
                if isinstance(detected, (float, int)) and detected < self._document_started:
                    continue
                tasks.append(str(field(task, "status", "unknown")))
            report.captcha_statuses = sorted(set(tasks))
            if FAILED_CAPTCHA_STATUSES.intersection(tasks):
                report.evidence.append("Steel reports a failed CAPTCHA task; recheck the page before treating it as blocked.")
            # With timestamped stale tasks, an old page-level flag must not stall a new document.
            active = bool(ACTIVE_CAPTCHA_STATUSES.intersection(tasks)) or (
                field(state, "is_solving_captcha", False) and (bool(tasks) or not field(state, "tasks", []))
            )
            return active
        except Exception as exc:
            report.evidence.append(f"Steel CAPTCHA status is unavailable ({type(exc).__name__}); no successful solve is assumed.")
            return None

    def check(self, *, initial: bool = False) -> PageAccessCheck:
        started = time.monotonic()
        deadline = started + self.wait_timeout
        waited = False
        last_active = False
        last_url = self.page.url
        while True:
            if self.page.is_closed() or self._crashed:
                return PageAccessCheck(
                    state="browser_error", url=self.page.url, failure_reason="browser_error",
                    evidence=["The browser page closed or crashed."],
                )
            if initial and self._navigation_error and self._http_status is None:
                return PageAccessCheck(
                    state="navigation_error", url=self.page.url,
                    failure_reason="navigation_error", evidence=[self._navigation_error],
                )
            try:
                snapshot = self._snapshot()
            except PlaywrightError as exc:
                connected = self.page.context.browser is None or self.page.context.browser.is_connected()
                terminal = self.page.is_closed() or self._crashed or not connected
                return PageAccessCheck(
                    state="browser_error" if terminal else "unknown", url=self.page.url,
                    failure_reason="browser_error" if terminal else None,
                    evidence=[f"Could not inspect the current document ({type(exc).__name__})."],
                )
            current_response = document_url(snapshot["url"]) == document_url(self._response_url)
            report = classify_page(
                snapshot, self._http_status if current_response else None,
                self._challenged if current_response else False,
            )
            report.waited_seconds = round(time.monotonic() - started, 2)
            if report.failure_reason:
                return report
            if self._navigation_error:
                report.evidence.append(self._navigation_error)
                if (initial and self._http_status is None) or snapshot["url"].startswith("chrome-error:"):
                    report.state = "navigation_error"
                    report.failure_reason = "navigation_error"
                    return report
                report.evidence.append("The previous navigation failed; the current page may still offer a way back.")

            remaining = max(0, deadline - time.monotonic())
            active = self._captcha_progress(report, max(0.05, min(5, remaining)))
            if report.url != last_url:
                last_active = False
                last_url = report.url
            # A status API outage does not prove previously active solving finished.
            active = last_active if active is None else active
            last_active = active
            if active:
                report.state = "captcha_solving"
                report.evidence.append("Steel is detecting, solving, or validating a CAPTCHA on this document.")
            elif report.state == "challenge" and FAILED_CAPTCHA_STATUSES.intersection(report.captcha_statuses):
                report.failure_reason = "verification_required"
                report.evidence.append("Steel reported a failed task and the current document still shows a verification page.")
                return report
            if active or report.state == "challenge":
                if time.monotonic() >= deadline:
                    report.failure_reason = "verification_required"
                    report.evidence.append("Verification did not clear within the configured CAPTCHA wait budget.")
                    report.waited_seconds = round(time.monotonic() - started, 2)
                    return report
                waited = True
                try:
                    self.page.wait_for_timeout(max(0, min(self.poll_interval, deadline - time.monotonic())) * 1000)
                except PlaywrightError:
                    # Inspect close/crash/disconnect state on the next iteration.
                    pass
                continue
            if waited:
                report.evidence.append("CAPTCHA activity ended; the document was inspected again before continuing.")
            return report
