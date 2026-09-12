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