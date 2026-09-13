import base64
import json 
import os 
from typing import Literal

import anthropic
from playwright.sync_api import Error as PlaywrightError, Page
from pydantic import BaseModel, Field

from artifacts import save_step_screenshot
from models import PageAccessCheck, Persona, StepRecord, TaskResult
from page_access import PageAccessMonitor

CLAUDE_MODEL = "claude-sonnet-5"
MAX_OUTPUT_TOKENS = 4096
MAX_STEPS = 40
MAX_BODY_TEXT_CHARS = 40_000
MAX_REPORTED_ELEMENTS = 400
MIN_ZOOM_PERCENT = 25
MAX_ZOOM_PERCENT = 500

INTERACTIVE_SELECTOR = (
    'a, button, input, textarea, select, '
    '[role="button"], [role="link"], [role="textbox"], '
    '[contenteditable="true"]'
)

class BrowserDecision(BaseModel):
    action: Literal["click", "fill", "press", "back", "scroll", "zoom", "goto", "finish"]
    element_index: int | None = None
    value: str | None = None
    success: bool | None = None
    reasoning: str
    summary: str
    score: int | None = Field(
        default=None, ge=0, le=10, strict=True,
        description="Required for finish with success=true: overall usability for this persona, from 0 to 10.",
    )
    score_justification: str | None = Field(
        default=None,
        description="Required for a successful finish: justify the score using the full step history and earlier persona reasoning.",
    )

def get_page_zoom_percent(page: Page) -> float:
    """Read the current document's CSS zoom, including after navigation."""
    return page.evaluate(
        """() => (parseFloat(getComputedStyle(document.documentElement).zoom) || 1) * 100"""
    )


def zoom_page(page: Page, value: str | None) -> None:
    """Set absolute CSS page magnification and verify the computed result.

    This reflows page content but does not emulate native browser zoom's
    viewport/media-query changes. A new document uses its own initial zoom.
    """
    try:
        percent = float((value or "").strip().removesuffix("%"))
    except ValueError:
        raise ValueError(
            "A zoom action requires a percentage in value, such as '150'."
        ) from None

    if not MIN_ZOOM_PERCENT <= percent <= MAX_ZOOM_PERCENT:
        raise ValueError(
            f"Zoom must be between {MIN_ZOOM_PERCENT}% and {MAX_ZOOM_PERCENT}%."
        )

    page.evaluate(
        """percent => document.documentElement.style.setProperty(
            "zoom", String(percent / 100), "important"
        )""",
        percent,
    )
    page.wait_for_function(
        """percent => Math.abs(
            (parseFloat(getComputedStyle(document.documentElement).zoom) || 1)
            * 100 - percent
        ) < 0.1""",
        arg=percent,
        timeout=2_000,
    )


def observe_page(page: Page, access_check: PageAccessCheck | None = None) -> str:
    element_details = page.locator(INTERACTIVE_SELECTOR).evaluate_all(
        """
        elements => {
            document
                .querySelectorAll("[data-persona-index]")
                .forEach(stale => stale.removeAttribute("data-persona-index"));

            return elements.map((element, index) => {
                const rect = element.getBoundingClientRect();
                const rendered = rect.width > 0 && rect.height > 0;

                if (rendered) {
                    element.setAttribute("data-persona-index", String(index));
                }

                return {
                    index,
                    tag: element.tagName.toLowerCase(),
                    type: element.getAttribute("type"),
                    text: (element.innerText || element.value || "")
                        .replace(/\\s+/g, " ")
                        .trim()
                        .slice(0, 200),
                    aria_label: element.getAttribute("aria-label"),
                    placeholder: element.getAttribute("placeholder"),
                    name: element.getAttribute("name"),
                    rendered,
                    in_viewport: (
                        rendered &&
                        rect.bottom > 0 && rect.top < window.innerHeight &&
                        rect.right > 0 && rect.left < window.innerWidth
                    )
                };
            })
            .filter(element => element.rendered);
        }
        """
    )

    viewport = page.evaluate(
        """
        () => ({
            scroll_y: Math.round(window.scrollY),
            viewport_height: window.innerHeight,
            page_height: Math.round(document.documentElement.scrollHeight)
        })
        """
    )

    body_text = page.locator("body").inner_text(timeout=10_000)

    reported_elements = sorted(
        element_details,
        key=lambda element: not element["in_viewport"],
    )[:MAX_REPORTED_ELEMENTS]

    observation = {
        "url": page.url,
        "title": page.title(),
        "page_access": access_check.model_dump() if access_check else {"state": "unknown"},
        "zoom_percent": get_page_zoom_percent(page),
        "scroll_position": viewport,
        "at_page_bottom": (
            viewport["scroll_y"] + viewport["viewport_height"]
            >= viewport["page_height"] - 2
        ),
        "body_text": body_text[:MAX_BODY_TEXT_CHARS],
        "body_text_total_chars": len(body_text),
        "body_text_truncated": len(body_text) > MAX_BODY_TEXT_CHARS,
        "interactive_elements": reported_elements,
        "interactive_elements_omitted": len(element_details) - len(reported_elements),
    }

    return json.dumps(observation, ensure_ascii=False)

def format_history(history: list[StepRecord]) -> str:
    if not history:
        return "Not yet. This is your first action."

    lines = []
    for record in history:
        parts = [f"{record.step}. {record.action}"]

        if record.element_index is not None:
            parts.append(f"element {record.element_index}")
        if record.value:
            parts.append(f"value={record.value!r}")

        lines.append(f"{' '.join(parts)} -> {record.outcome}")

        if record.reasoning:
            lines.append(f"   you were thinking: {record.reasoning}")

    return "\n".join(lines)

def choose_next_action(client: anthropic.Anthropic, page: Page, persona: Persona, task: str, step_number: int, history: list[StepRecord], access_check: PageAccessCheck | None = None) -> tuple[BrowserDecision, bytes]:
    observation = observe_page(page, access_check)
    screenshot = page.screenshot(type="png")

    prompt = f"""
You are controlling a browser as this user persona:

Name: {persona.name}
Behavior:
{persona.system_prompt}

Your assigned task is:
{task}

This is step {step_number} of {MAX_STEPS}.

Actions you have already taken:
{format_history(history)}

Examine the screenshot and page observation, then choose exactly one action.

Action rules:
- click: provide the element_index to click.
- fill: provide the element_index and text in value.
- press: provide the element_index and keyboard key in value, or omit
  element_index to send the key to the page itself.
- zoom: omit element_index and provide an absolute percentage in value,
  such as "150" for 150% or "100" to reset. The allowed range is
  {MIN_ZOOM_PERCENT}% to {MAX_ZOOM_PERCENT}%. This sets CSS page magnification.
  Always use this action to enlarge page content; do not use press with
  Ctrl+Plus or other browser zoom shortcuts.
  zoom_percent reports the current document's applied zoom. If it is already
  at your desired level, continue the task instead of zooming again.
  Navigation to a new document can reset zoom; check zoom_percent afterward.
- scroll: provide "down" or "up" in value.
- goto: provide an absolute URL in value. Use this only to return to the site
  under test if you have navigated away from it.
- back: navigate to the previous page.
- finish: use only when the task has succeeded or cannot be completed.
- For finish, set success to true or false and explain the outcome in summary.
- For finish with success=true, also provide score and score_justification
  following the scoring rules below. For other decisions, leave both null.
- Do not claim success merely because the website loaded.
- Only choose element indexes listed in interactive_elements.

Progress rules:
- page_access contains browser and Steel CAPTCHA evidence. "unknown" means
  access has not been established, not that the page is usable or blocked.
- Do not solve CAPTCHAs yourself. Steel handles enabled CAPTCHA solving, and
  the runner waits for active solving before asking you for another action.
- Login screens, cookie notices, subscription screens, and HTTP errors are
  not automatically automation blocks. Interpret them in the task's context.
- If an error occurs after navigation, consider going back or using another
  visible route. Report errors as test findings. Never claim success just
  because Steel finished a CAPTCHA task or the page returned HTTP 200.
- Never repeat an action that already appears above with a failed outcome.
- If the same approach has failed twice, choose a different path or finish
  with success set to false.
- Elements with in_viewport set to false are on the page but off screen. Scroll
  them into view before trying to click them.
- Do not scroll again if at_page_bottom is true, or if your last two actions
  were both scrolls in the same direction and no new elements appeared.
- body_text holds the whole page's text no matter where the page is scrolled,
  so scroll to bring elements within reach, not to read more text.
- If interactive_elements_omitted is above zero, the page has more controls than
  you were shown. Scroll to bring the ones you need into view.

Exploration rules:
- This is a usability test, not a trivia question. Your job is to find out
  whether a real user can accomplish this task through the interface, so use
  the interface instead of only reading the page.
- Finding an answer written in body_text is not the same as completing the
  task. Follow the links, menus, and controls a real user would follow.
- Do not finish before step 4 unless the task is genuinely impossible on this
  site. Before finishing, make sure you have looked at the whole page and at
  the main navigation.

Scoring rules for a successful finish:
- Give an integer score from 0 to 10 for the overall usability of completing
  this task as this persona. Success alone does not justify a high score.
- Review ALL recorded steps, their outcomes, and your earlier reasoning in
  Actions you have already taken, together with the persona's needs, assigned
  task, and current screenshot/observation. Do not judge only the final page.
- Consider readability, clarity of labels/navigation, feedback, effort,
  confusion, failed attempts, and recovery across the whole journey.
- Use this scale consistently: 0-2 extremely difficult/frustrating; 3-4
  difficult; 5-6 mixed; 7-8 mostly clear with minor friction; 9-10 very clear
  and easy for this persona.
- In score_justification, write two to four sentences in the persona's voice.
  Cite specific step numbers and observations where available, explain what
  helped or hindered you, and connect that evidence to the score. Do not
  invent issues or positive experiences that were not observed. Distinguish
  automation/infrastructure failures from problems with the site's usability.

In reasoning, state in two or three sentences, in the voice of your persona,
what you see, what you have learned so far, and why you are choosing this
action. Call out anything confusing, hard to find, or badly labelled. Those
observations are the point of this test, and you will be shown your own
reasoning again on later steps.

Page observation:
{observation}
"""

    response = client.messages.parse(
        model=CLAUDE_MODEL,
        max_tokens=MAX_OUTPUT_TOKENS,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": base64.standard_b64encode(screenshot).decode("ascii"),
                        },
                    },
                    {
                        "type": "text",
                        "text": prompt,
                    },
                ],
            }
        ],
        output_format=BrowserDecision,
    )

    if response.stop_reason == "refusal":
        raise RuntimeError("Claude refused to act on this page.")

    if response.stop_reason == "max_tokens":
        raise RuntimeError(
            f"Claude hit the {MAX_OUTPUT_TOKENS} token output limit "
            f"before returning a decision."
        )

    decision = response.parsed_output

    if not isinstance(decision, BrowserDecision):
        raise RuntimeError("Claude returned no parsable decision.")

    return decision, screenshot

def execute_action(page: Page, decision: BrowserDecision) -> TaskResult | None:
    if decision.action == "finish":
        if decision.success is None:
            raise ValueError("A finish decision must include a success value.")

        return TaskResult(
            success=decision.success,
            summary=decision.summary,
            score=decision.score if decision.success else None,
            score_justification=decision.score_justification if decision.success else None,
        )

    if decision.action == "zoom":
        if decision.element_index is not None:
            raise ValueError("A zoom action applies to the page; omit element_index.")
        zoom_page(page, decision.value)
        return None

    if decision.action == "back":
        page.go_back(wait_until="domcontentloaded", timeout=30_000)
        return None

    if decision.action == "goto":
        if decision.value is None:
            raise ValueError("A goto action requires a URL.")
        page.goto(decision.value, wait_until="domcontentloaded", timeout=60_000)
        return None
 
    if decision.action == "scroll":
        direction = (decision.value or "down").strip().lower()
        if direction not in ("up", "down"):
            raise ValueError(f"A scroll action requires 'up' or 'down', got {decision.value!r}.")

        offset = page.evaluate("() => Math.round(window.innerHeight * 0.8)")
        page.mouse.wheel(0, offset if direction == "down" else -offset)
        page.wait_for_timeout(500)
        return None

    if (decision.action == "press" and decision.element_index is None):
        if decision.value is None:
            raise ValueError("A press action requires a keyboard key.")

        page.keyboard.press(decision.value)
        page.wait_for_timeout(500)
        return None
    
    if decision.element_index is None:
        raise ValueError(f"{decision.action} requires an element index.")

    element = page.locator(f'[data-persona-index="{decision.element_index}"]')
    matches = element.count()

    if matches == 0:
        raise ValueError(
            f"Element {decision.element_index} is no longer on the page. "
            f"The page changed after it was observed. Re-read the current "
            f"observation and choose a different element."
        )

    if matches > 1:
        raise ValueError(
            f"Element {decision.element_index} is ambiguous ({matches} matches). "
            f"Choose a different element."
        )

    if decision.action == "click":
        element.click(timeout=30_000)

    elif decision.action == "fill":
        if decision.value is None:
            raise ValueError("A fill action requires a value")

        element.fill(decision.value, timeout=30_000)

    elif decision.action == "press":
        if decision.value is None:
            raise ValueError("A press action requires a keyboard key.")

        element.press(decision.value, timeout=30_000)

    page.wait_for_timeout(500)
    return None

def run_persona_agent(
    page: Page,
    persona: Persona,
    task: str,
    access: PageAccessMonitor | None = None,
    run_id: str | None = None,
) -> TaskResult:
    if not run_id:
        raise ValueError("A run ID is required to store step screenshots.")

    owned_access = access is None
    access = access or PageAccessMonitor.from_environment(page)
    client = None
    history: list[StepRecord] = []
    access_checks: list[PageAccessCheck] = []
    previous_failure: tuple | None = None

    try:
        for step_number in range(1, MAX_STEPS + 1):
            access_check = access.check(initial=not history)
            access_checks.append(access_check)
            if access_check.failure_reason:
                return TaskResult(
                    success=False,
                    failure_reason=access_check.failure_reason,
                    summary=f"Persona session stopped: {access_check.failure_reason.replace('_', ' ')}. "
                    + " ".join(access_check.evidence),
                    steps=history,
                    access_checks=access_checks,
                )
            if client is None:
                api_key = os.environ.get("CLAUDE_API_KEY")
                if not api_key:
                    raise ValueError("CLAUDE_API_KEY environment variable is not set.")
                client = anthropic.Anthropic(api_key=api_key)
            try:
                decision, screenshot = choose_next_action(
                    client=client, 
                    page=page, 
                    persona=persona, 
                    task=task, 
                    step_number=step_number, 
                    history=history,
                    access_check=access_check,
                )
            except PlaywrightError as exc:
                return TaskResult(
                    success=False, failure_reason="browser_error",
                    summary=f"The browser could not be observed at step {step_number} ({type(exc).__name__}).",
                    steps=history, access_checks=access_checks,
                )
            except Exception as exc:
                if not history:
                    raise 

                return TaskResult(
                    success=False, 
                    summary=(
                        f"The model call failed at step {step_number} after "
                        f"{len(history)} completed actions: "
                        f"{type(exc).__name__}: {exc}"
                    ),
                    steps=history,
                    access_checks=access_checks,
                )

            screenshot_url = save_step_screenshot(
                run_id=run_id,
                persona_id=persona.id,
                step=step_number,
                image=screenshot,
            )

            action_url = page.url
            try:
                result = execute_action(
                    page=page,
                    decision=decision
                )
                outcome = "ok"
                if decision.action == "zoom":
                    outcome = f"ok: CSS page zoom is now {get_page_zoom_percent(page):g}%"
            except Exception as exc:
                result = None 
                outcome = f"failed: {type(exc).__name__}: {exc}"

            history.append(
                StepRecord(
                    step=step_number,
                    action=decision.action,
                    element_index=decision.element_index,
                    value=decision.value,
                    reasoning=decision.reasoning,
                    outcome=outcome,
                    screenshot_url=screenshot_url,
                )
            )

            if result is not None:
                return result.model_copy(update={"steps": history, "access_checks": access_checks})

            failure = (action_url, decision.action, decision.element_index, decision.value)
            if outcome.startswith("failed:"):
                if failure == previous_failure:
                    return TaskResult(
                        success=False, failure_reason="no_progress",
                        summary="The same action failed twice consecutively on the same page.",
                        steps=history, access_checks=access_checks,
                    )
                previous_failure = failure
            else:
                previous_failure = None

        return TaskResult(
            success=False,
            summary=(
                f"The agent reached the maximum of {MAX_STEPS} actions "
                f"without completing the task."
            ),
            steps=history,
            access_checks=access_checks,
        )
    finally:
        if client is not None:
            client.close()
        if owned_access:
            access.close()
