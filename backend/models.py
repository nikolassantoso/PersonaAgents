from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator
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

class StepRecord(BaseModel):
    step: int
    action: str
    element_index: int | None = None
    value: str | None = None
    reasoning: str = ""
    outcome: str # "ok" or a failure descriptions

AccessFailureReason = Literal[
    "website_blocked", "verification_required", "navigation_error", "browser_error"
]


class PageAccessCheck(BaseModel):
    state: Literal[
        "unknown", "blocked", "challenge", "captcha_solving", "http_error",
        "navigation_error", "browser_error",
    ] = "unknown"
    url: str
    title: str = ""
    http_status: int | None = None
    evidence: list[str] = Field(default_factory=list)
    captcha_statuses: list[str] = Field(default_factory=list)
    waited_seconds: float = 0
    failure_reason: AccessFailureReason | None = None


class TaskResult(BaseModel):
    success: bool
    summary: str
    score: int | None = Field(default=None, ge=0, le=10, strict=True)
    score_justification: str | None = None
    steps: list[StepRecord] = Field(default_factory=list)
    failure_reason: AccessFailureReason | Literal["no_progress"] | None = None
    access_checks: list[PageAccessCheck] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_success_score(self):
        if self.success:
            if self.score is None:
                raise ValueError("A successful result requires a score from 0 to 10.")
            if not self.score_justification or not self.score_justification.strip():
                raise ValueError("A successful result requires a nonblank score_justification.")
            self.score_justification = self.score_justification.strip()
        return self

class Run(RunRequest):
    id: str
    status: Literal["created", "running", "completed", "failed"] = "created"
    session_viewer_urls: dict[str, str] = Field(default_factory=dict)
    results: dict[str, TaskResult] = Field(default_factory=dict)
    errors: dict[str, str] = Field(default_factory=dict)

class PersonaCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=100)
    system_prompt: str = Field(min_length=1, max_length=10_000)
