import json 
import os 
from typing import Literal

from google import genai
from google.genai import types
from playwright.sync_api import Locator, Page
from pydantic import BaseModel

from models import Persona, TaskResult

GEMINI_MODEL = "gemini-3.6-flash"
MAX_STEPS = 15

INTERACTIVE_SELECTOR = (
    'a, button, input, textarea, select, '
    '[role="button"], [role="link"], [role="textbox"], '
    '[contenteditable="true"]'
)

class BrowserDecision(BaseModel):
    action: Literal["click", "fill", "press", "back", "finish"]
    element_index: int | None = None
    value: str | None = None
    success: bool | None = None
    reasoning: str
    summary: str

def observe_page(page: Page) -> tuple[Locator, str]:
    elements = page.locator(INTERACTIVE_SELECTOR)
    element_details = elements.evaluate_all(
        """
        elements => elements.map((element, index) => {
            const rect = element.getBoundingClientRect();
            
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
                visible: rect.width > 0 && rect.height > 0
            };
        })
        .filter(element => element.visible)
        """
    )

    body_text = page.locator("body").inner_text(timeout=10_000)

    observation = {
        "url": page.url,
        "title": page.title(),
        "body_text": body_text[:6000],
        "interactive_elements": element_details[:100],
    }

    return elements, json.dumps(observation, ensure_ascii=False)

def choose_next_action(client: genai.Client, page: Page, persona: Persona, task: str, step_number: int) -> tuple[Locator, BrowserDecision]:
    elements, observation = observe_page(page)
    screenshot = page.screenshot(type="png")

    prompt = f"""
You are controlling a browser as this user persona:

Name: {persona.name}
Behavior:
{persona.system_prompt}

Your assigned task is:
{task}

This is step {step_number} of {MAX_STEPS}.

Examine the screenshot and page observation, then choose exactly one action.

Action rules:
- click: provide the element_index to click.
- fill: provide the element_index and text in value.
- press: provide the element_index and keyboard key in value.
- back: navigate to the previous page.
- finish: use only when the task has succeeded or cannot be completed.
- For finish, set success to true or false and explain the outcome in summary.
- Do not claim success merely because the website loaded.
- Only choose element indexes listed in interactive_elements.

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

    return elements, decision

def execute_action(page: Page, elements: Locator, decision: BrowserDecision) -> TaskResult | None:
    if decision.action == "finish":
        if decision.success is None:
            raise ValueError("A finish decision must include a success value.")

        return TaskResult(success=decision.success, summary=decision.summary)

    if decision.action == "back":
        page.go_back(wait_until="domcontentloaded", timeout=30_000)
        return None

    if (decision.action == "press" and decision.element_index is None):
        if decision.value is None:
            raise ValueError("A press action requires a keyboard key.")

        page.keyboard.press(decision.value)
        page.wait_for_timeout(500)
        return None

    if decision.element_index is None:
        raise ValueError(f"{decision.action} requires an element index.")

    if not 0 <= decision.element_index < elements.count():
        raise ValueError(f"Invalid element index: {decision.element_index}")

    element = elements.nth(decision.element_index)

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
    try:
        for step_number in range(1, MAX_STEPS + 1):
            elements, decisions = choose_next_action(
                client=client, 
                page=page, 
                persona=persona, 
                task=task, 
                step_number=step_number
            )

            result = execute_action(
                page=page, 
                elements=elements,
                decision=decisions
            )

            if result is not None:
                return result

        return TaskResult(
            success=False, 
            summary=(f"The agent reached the maximum of {MAX_STEPS} actions without completing the task.")
        ) 
    finally:
        client.close() 