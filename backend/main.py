"""
PersonaAgent - FastAPI server
"""

from __future__ import annotations

import os
import re
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from persona_agent import run_persona_agent
from runner import execute_run

from artifacts import fixed_screenshot_path, screenshot_path
from models import Revamp, RevampImage
from personas import PERSONAS
from revamp import execute_revamp, image_settings

load_dotenv()

app = FastAPI(title="PersonaAgent", version="0.1.0")

# Direct browser requests from Vercel need CORS; Vite's local proxy does not.
cors_origins = [
    origin.strip().rstrip("/")
    for origin in os.environ.get(
        "CORS_ALLOW_ORIGINS",
        "https://persona-agents-nu.vercel.app,http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

# Request / Response Models
from models import Persona
from models import RunRequest
from models import Run
from models import PersonaCreate

# In-memory storage for runs
RUNS: dict[str, Run] = {}
REVAMPS: dict[str, Revamp] = {}

def create_persona_id(name: str) -> str:
    persona_id = re.sub(r"[^a-z0-9]+", "_", name.lower())
    persona_id = persona_id.strip("_")

    if not persona_id:
        persona_id = f"persona_{uuid4().hex[:8]}"

    return persona_id

# REST API routes
@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}

@app.get("/personas")
async def list_personas() -> dict[str, Persona]:
    return PERSONAS

@app.post("/personas", response_model=Persona, status_code=201)
async def create_persona(request: PersonaCreate) -> Persona:
    persona_id = create_persona_id(request.name)
    if persona_id in PERSONAS:
        raise HTTPException(
            status_code=409,
            detail=f"A persona with the ID '{persona_id}' already exists.",
        )

    persona = Persona(
        id=persona_id,
        **request.model_dump(),
    )

    PERSONAS[persona_id] = persona
    return persona

@app.post("/runs", status_code=201)
async def create_run(request: RunRequest, background_tasks: BackgroundTasks) -> dict[str, str]:
    unknown_personas = [
        persona_name
        for persona_name in request.personas
        if persona_name not in request.persona_definitions and persona_name not in PERSONAS
    ]

    if unknown_personas:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown personas: {', '.join(unknown_personas)}",
        )

    if len(request.personas) != len(set(request.personas)):
        raise HTTPException(
            status_code=400,
            detail="Duplicate personas are not allowed.",
        )

    run_id = str(uuid4())
    definitions = {
        persona_id: (
            Persona(id=persona_id, **request.persona_definitions[persona_id].model_dump())
            if persona_id in request.persona_definitions
            else PERSONAS[persona_id].model_copy(deep=True)
        )
        for persona_id in request.personas
    }
    RUNS[run_id] = Run(
        id=run_id,
        **request.model_dump(exclude={"persona_definitions"}),
        persona_definitions=definitions,
    )

    background_tasks.add_task(
        execute_run,
        RUNS[run_id],
        run_persona_agent
    )

    return {"run_id": run_id}

@app.get("/runs/{id}")
async def get_run(id: str) -> Run:
    run = RUNS.get(id)
    if not run:
        raise HTTPException(
            status_code=404, 
            detail="Run not found"
        )
    return run


@app.post("/runs/{id}/revamp", response_model=Revamp, status_code=202)
async def create_revamp(id: str, background_tasks: BackgroundTasks) -> Revamp:
    run = RUNS.get(id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    if run.status in ("created", "running"):
        raise HTTPException(
            status_code=409,
            detail="The run must finish before it can be revamped.",
        )

    existing = REVAMPS.get(id)
    if existing:
        return existing

    images = [
        RevampImage(
            persona_id=persona_id,
            step=step.step,
            reasoning=step.reasoning,
            score=result.score,
            score_justification=result.score_justification,
            original_screenshot_url=step.screenshot_url,
        )
        for persona_id, result in run.results.items()
        for step in result.steps
        if step.screenshot_url is not None
    ]
    if not images:
        raise HTTPException(
            status_code=422,
            detail="The run has no step screenshots to revamp.",
        )

    try:
        model, quality = image_settings()
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    revamp = Revamp(
        run_id=id,
        model=model,
        quality=quality,
        total_images=len(images),
        images=images,
    )
    REVAMPS[id] = revamp
    background_tasks.add_task(execute_revamp, run, run.persona_definitions, revamp)
    return revamp


@app.get("/runs/{id}/revamp", response_model=Revamp)
async def get_revamp(id: str) -> Revamp:
    if id not in RUNS:
        raise HTTPException(status_code=404, detail="Run not found")

    revamp = REVAMPS.get(id)
    if not revamp:
        raise HTTPException(status_code=404, detail="Revamp not found")

    return revamp


@app.get(
    "/runs/{run_id}/personas/{persona_id}/steps/{step}/screenshot",
    response_class=FileResponse,
)
async def get_step_screenshot(
    run_id: str,
    persona_id: str,
    step: int,
) -> FileResponse:
    run = RUNS.get(run_id)
    if not run or persona_id not in run.results:
        raise HTTPException(status_code=404, detail="Screenshot not found")

    try:
        path = screenshot_path(run_id, persona_id, step)
    except ValueError:
        raise HTTPException(status_code=404, detail="Screenshot not found") from None

    if not path.is_file():
        raise HTTPException(status_code=404, detail="Screenshot not found")

    return FileResponse(
        path,
        media_type="image/png",
        headers={"Cache-Control": "private, max-age=86400"},
    )


@app.get(
    "/runs/{run_id}/personas/{persona_id}/steps/{step}/screenshot-fixed",
    response_class=FileResponse,
)
async def get_fixed_step_screenshot(
    run_id: str,
    persona_id: str,
    step: int,
) -> FileResponse:
    revamp = REVAMPS.get(run_id)
    if not revamp or not any(
        image.persona_id == persona_id
        and image.step == step
        and image.status == "completed"
        for image in revamp.images
    ):
        raise HTTPException(status_code=404, detail="Fixed screenshot not found")

    try:
        path = fixed_screenshot_path(run_id, persona_id, step)
    except ValueError:
        raise HTTPException(status_code=404, detail="Fixed screenshot not found") from None

    if not path.is_file():
        raise HTTPException(status_code=404, detail="Fixed screenshot not found")

    return FileResponse(
        path,
        media_type="image/png",
        headers={"Cache-Control": "private, max-age=86400"},
    )
