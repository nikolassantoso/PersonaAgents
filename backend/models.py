from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator
from typing import Annotated, Literal

PersonaId = Annotated[str, Field(min_length=1, pattern=r"^[A-Za-z0-9_-]+$")]


class PersonaCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=100)
    system_prompt: str = Field(min_length=1, max_length=10_000)

# Request / Response Models
class Persona(PersonaCreate):
    id: PersonaId

class RunRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    url: HttpUrl
    personas: list[PersonaId] = Field(min_length=1)
    task: str = Field(min_length=1)
    persona_definitions: dict[PersonaId, PersonaCreate] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_persona_definitions(self):
        if set(self.persona_definitions) - set(self.personas):
            raise ValueError("Persona definitions must belong to selected personas.")
        return self

class StepRecord(BaseModel):
    step: int
    action: str
    element_index: int | None = None
    value: str | None = None
    reasoning: str = ""
    outcome: str # "ok" or a failure descriptions
    screenshot_url: str | None = None

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
    persona_definitions: dict[PersonaId, Persona] = Field(default_factory=dict)
    id: str
    status: Literal["created", "running", "completed", "failed"] = "created"
    session_viewer_urls: dict[str, str] = Field(default_factory=dict)
    results: dict[str, TaskResult] = Field(default_factory=dict)
    errors: dict[str, str] = Field(default_factory=dict)


class RevampImage(BaseModel):
    persona_id: str
    step: int
    reasoning: str
    score: int | None
    score_justification: str | None
    original_screenshot_url: str
    fixed_screenshot_url: str | None = None
    status: Literal["pending", "generating", "completed", "failed"] = "pending"
    error: str | None = None


class Revamp(BaseModel):
    run_id: str
    status: Literal["created", "running", "completed", "partial", "failed"] = "created"
    model: str
    quality: Literal["low", "medium", "high", "xhigh", "max", "auto"]
    total_images: int
    completed_images: int = 0
    images: list[RevampImage] = Field(default_factory=list)
    error: str | None = None
