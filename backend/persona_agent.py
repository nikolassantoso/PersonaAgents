import base64
import json 
import os 
from typing import Literal

import anthropic
from playwright.sync_api import Page
from pydantic import BaseModel

from models import Persona, StepRecord, TaskResult

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


def observe_page(page: Page) -> str:
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

def choose_next_action(client: anthropic.Anthropic, page: Page, persona: Persona, task: str, step_number: int, history: list[StepRecord]) -> BrowserDecision:
    observation = observe_page(page)
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
- Do not claim success merely because the website loaded.
- Only choose element indexes listed in interactive_elements.

Progress rules:
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

    return decision

def execute_action(page: Page, decision: BrowserDecision) -> TaskResult | None:
    if decision.action == "finish":
        if decision.success is None:
            raise ValueError("A finish decision must include a success value.")

        return TaskResult(success=decision.success, summary=decision.summary)

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

def run_persona_agent(page: Page, persona: Persona, task: str) -> TaskResult:
    api_key = os.environ.get("CLAUDE_API_KEY")
    if not api_key:
        raise ValueError("CLAUDE_API_KEY environment variable is not set.")

    client = anthropic.Anthropic(api_key=api_key)
    history: list[StepRecord] = []

    try:
        for step_number in range(1, MAX_STEPS + 1):
            try:
                decision = choose_next_action(
                    client=client, 
                    page=page, 
                    persona=persona, 
                    task=task, 
                    step_number=step_number, 
                    history=history
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
                )

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
                )
            )

            if result is not None:
                return result.model_copy(update={"steps": history})

        return TaskResult(
            success=False,
            summary=(
                f"The agent reached the maximum of {MAX_STEPS} actions "
                f"without completing the task."
            ),
            steps=history,
        )
    finally:
        client.close()
