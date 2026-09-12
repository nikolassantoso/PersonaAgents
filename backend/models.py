from pydantic import BaseModel, ConfigDict, Field, HttpUrl
from typing import Literal

# Request / Response Models
class Persona(BaseModel):
    id: str
    name: str
    description: str
    system_prompt: str

class RunRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    url: HttpUrl
    personas: list[str] = Field(min_length=1)
    task: str = Field(min_length=1)

class TaskResult(BaseModel):
    success: bool
    summary: str

class Run(RunRequest):
    id: str
    status: Literal["created", "running", "completed", "failed"] = "created"
    session_viewer_urls: dict[str, str] = Field(default_factory=dict)
    results: dict[str, TaskResult] = Field(default_factory=dict)
    errors: dict[str, str] = Field(default_factory=dict)