from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

from playwright.sync_api import Page

from browser import open_persona_browser
from models import Persona, Run, TaskResult
from personas import PERSONAS
from page_access import PageAccessMonitor

AgentFunction = Callable[[Page, Persona, str, PageAccessMonitor], TaskResult]

import os
from urllib.parse import quote_plus
def format_error(exc: Exception) -> str:
    message = str(exc)

    for variable_name in ("STEEL_API_KEY", "CLAUDE_API_KEY"):
        secret = os.environ.get(variable_name)

        if secret:
            message = message.replace(secret, "[REDACTED]")
            message = message.replace(
                quote_plus(secret),
                "[REDACTED]",
            )

    return f"{type(exc).__name__}: {message}"[:2000]

def execute_persona(run: Run, persona: Persona, agent: AgentFunction) -> TaskResult:
    with open_persona_browser(str(run.url)) as (session, page, access):
        run.session_viewer_urls[persona.id] = session.session_viewer_url
        return agent(page, persona, run.task, access)

def execute_run(run: Run, agent: AgentFunction) -> None:
    run.status = "running"

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = {
                executor.submit(
                    execute_persona,
                    run,
                    PERSONAS[persona_id],
                    agent, 
                ): persona_id
                for persona_id in run.personas
            }

            for future in as_completed(futures):
                persona_id = futures[future]

                try: 
                    result = future.result()
                except Exception as exc:
                    run.errors = {
                        **run.errors,
                        persona_id: format_error(exc),
                    }
                else:
                    run.results = {
                        **run.results,
                        persona_id: result,
                    }

    except Exception:
        run.status = "failed"
        raise 

    run.status = "failed" if run.errors else "completed"
