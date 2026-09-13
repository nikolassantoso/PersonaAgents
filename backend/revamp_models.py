"""Image generation status is separate from the original usability assessment."""

from typing import Literal

from pydantic import BaseModel, Field

from models import RunRequest, StepRecord


GenerationStatus = Literal["created", "running", "completed", "partial", "failed"]


class RevampedStep(StepRecord):
    source_screenshot_url: str | None = None
    # screenshot_url is the NEW image, never the original or a placeholder.
    generation_status: Literal["pending", "completed", "failed"] = "pending"
    generation_error: str | None = None


class RevampedResult(BaseModel):
    success: bool
    summary: str
    # These are the source assessment, not a re-score of the generated image.
    score: int | None = None
    score_justification: str | None = None
    generation_status: GenerationStatus = "created"
    steps: list[RevampedStep] = Field(default_factory=list)


class RevampedRun(RunRequest):
    id: str
    status: GenerationStatus = "created"
    model: str
    expected_images: int = 0
    generated_images: int = 0
    failed_images: int = 0
    results: dict[str, RevampedResult] = Field(default_factory=dict)
    errors: dict[str, str] = Field(default_factory=dict)
