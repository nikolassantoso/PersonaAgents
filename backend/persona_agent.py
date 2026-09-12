import json 
import os 
from typing import Literal

from google import genai
from google.genai import types
from playwright.sync_api import Page
from pydantic import BaseModel

from models import Persona, StepRecord, TaskResult

GEMINI_MODEL = "gemini-3.6-flash"
MAX_STEPS = 15

INTERACTIVE_SELECTOR = (
    'a, button, input, textarea, select, '
    '[role="button"], [role="link"], [role="textbox"], '
    '[contenteditable="true"]'
)

class BrowserDecision(BaseModel):
    action: Literal["click", "fill", "press", "back", "scroll", "goto", "finish"]
    element_index: int | None = None
    value: str | None = None
    success: bool | None = None
    reasoning: str
    summary: str

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

    observation = {
        "url": page.url,
        "title": page.title(),
        "scroll_position": viewport,
        "at_page_bottom": (
            viewport["scroll_y"] + viewport["viewport_height"]
            >= viewport["page_height"] - 2
        ),
        "body_text": body_text[:6000],
        "interactive_elements": element_details[:100],
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

    return "\n".join(lines)

def choose_next_action(client: genai.Client, page: Page, persona: Persona, task: str, step_number: int, history: list[StepRecord]) -> BrowserDecision:
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
- If the information the task asks for is already visible in body_text,
  finish now instead of clicking further.
- Elements with in_viewport set to false are on the page but off screen. Scroll
  them into view before trying to click them.
- Do not scroll again if at_page_bottom is true, or if your last two actions
  were both scrolls in the same direction and no new elements appeared.

In reasoning, state in one or two sentences, in the voice of your persona,
what you see and why you are choosing this action.

Page observation:
{observation}
"""

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=[
            prompt, 
            types.Part.from_bytes(
                data=screenshot,
                mime_type="image/png"
            ), 
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=BrowserDecision,
            temperature=0.2,
        ),
    )

    if isinstance(response.parsed, BrowserDecision):
        decision = response.parsed
    elif response.text:
        decision = BrowserDecision.model_validate_json(response.text)
    else:
        raise RuntimeError("Gemini returned an empty response.")

    return decision

def execute_action(page: Page, decision: BrowserDecision) -> TaskResult | None:
    if decision.action == "finish":
        if decision.success is None:
            raise ValueError("A finish decision must include a success value.")

        return TaskResult(success=decision.success, summary=decision.summary)

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
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable is not set.")

    client = genai.Client(api_key=api_key)
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