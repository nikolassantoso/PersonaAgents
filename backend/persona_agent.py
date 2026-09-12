import json 
import os 
from typing import Literal

from google import genai
from google.genai import types
from playwright.sync_api import Locator, Page
from pydantic import BaseModel

from models import Persona, TaskResult

GEMINI_MODEL = "gemini-2.5-flash"
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

def choose_next_action(client: genai.Client, page: Page, persona: Persona, task: str, step_number: int) -> Tuple[Locator, BrowserDecision]:
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