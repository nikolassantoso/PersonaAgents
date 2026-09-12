from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

from playwright.sync_api import Page

from browser import open_persona_browser
from models import Persona, Run, TaskResult
from personas import DEFAULT_PERSONAS

AgentFunction = Callable[[Page, Persona, str], TaskResult]

def execute_persona(run: Run, persona: Persona, agent: AgentFunction) -> TaskResult:
    with open_persona_browser(str(run.url)) as (_, page):
        return agent(page, persona, run.task)

def execute_run(run: Run, agent: AgentFunction) -> None:
    run.status = "running"

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = {
                executor.submit(
                    execute_persona,
                    run,
                    DEFAULT_PERSONAS[persona_id],
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
                        persona_id: type(exc).__name__,
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