"""
PersonaAgent - FastAPI server
"""

from __future__ import annotations

from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel

load_dotenv()

app = FastAPI(title="PersonaAgent", version="0.1.0")

# REST API routes
@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}