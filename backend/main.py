"""
PersonaAgent - FastAPI server
"""

from __future__ import annotations

from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel

from personas import DEFAULT_PERSONAS

load_dotenv()

app = FastAPI(title="PersonaAgent", version="0.1.0")

# Request / Response Models
from models import Persona

# REST API routes
@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}

@app.get("/personas")
async def list_personas() -> dict[str, Persona]:
    return DEFAULT_PERSONAS