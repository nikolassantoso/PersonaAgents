"""
PersonaAgent - FastAPI server
"""

from __future__ import annotations

from uuid import uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException

from personas import DEFAULT_PERSONAS

load_dotenv()

app = FastAPI(title="PersonaAgent", version="0.1.0")

# Request / Response Models
from models import Persona
from models import RunRequest
from models import Run

# In-memory storage for runs
RUNS: dict[str, Run] = {}

# REST API routes
@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}

@app.get("/personas")
async def list_personas() -> dict[str, Persona]:
    return DEFAULT_PERSONAS

@app.post("/runs", status_code=201)
async def create_run(request: RunRequest) -> dict[str, str]:
    unknown_personas = [
        persona_name
        for persona_name in request.personas
        if persona_name not in DEFAULT_PERSONAS
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
    RUNS[run_id] = request
    return {"run_id": run_id}