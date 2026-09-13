"""Background generation with one image per original step and resumable failures."""

import os
from collections.abc import Callable
from threading import Lock, Semaphore

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Response
from fastapi.responses import FileResponse

from artifacts import fixed_artifact_path, save_fixed_screenshot, screenshot_path, write_artifact_atomic
from gemini_images import (
    DEFAULT_IMAGE_MODEL, MAX_IMAGE_BYTES, GeminiImageGenerator, ImageGenerationError,
    build_revamp_prompt, image_to_png,
)
from models import Run
from revamp_models import RevampedResult, RevampedRun, RevampedStep


Generator = Callable[[str, bytes], bytes]


class RevampService:
    def __init__(self, generator: Generator | None = None):
        self.jobs: dict[str, RevampedRun] = {}
        self.lock = Lock()
        self.capacity = Semaphore(2)  # Bound concurrent provider calls across runs.
        self.generator = generator

    def _save(self, job: RevampedRun) -> None:
        write_artifact_atomic(fixed_artifact_path(job.id), job.model_dump_json(indent=2).encode())

    def _load(self, run_id: str) -> RevampedRun | None:
        if run_id in self.jobs:
            return self.jobs[run_id]
        path = fixed_artifact_path(run_id)
        if not path.is_file():
            return None
        job = RevampedRun.model_validate_json(path.read_text(encoding="utf-8"))
        if job.id != run_id:
            raise ValueError("Artifact manifest does not match run ID.")
        # A previous process cannot still be executing this in-memory job.
        if job.status in {"created", "running"}:
            for result in job.results.values():
                for step in result.steps:
                    if step.generation_status == "pending":
                        step.generation_status = "failed"
                        step.generation_error = "Generation was interrupted by a server restart."
            self._summarize(job)
            self._save(job)
        self.jobs[run_id] = job
        return job

    @staticmethod
    def _summarize(job: RevampedRun) -> None:
        steps = [step for result in job.results.values() for step in result.steps]
        job.generated_images = sum(s.generation_status == "completed" for s in steps)
        job.failed_images = sum(s.generation_status == "failed" for s in steps)
        for result in job.results.values():
            statuses = [s.generation_status for s in result.steps]
            result.generation_status = (
                "running" if "pending" in statuses else
                "completed" if statuses and all(s == "completed" for s in statuses) else
                "partial" if "completed" in statuses else "failed"
            )
        job.status = (
            "running" if any(s.generation_status == "pending" for s in steps) else
            "completed" if steps and job.generated_images == job.expected_images and not job.errors else
            "partial" if job.generated_images else "failed"
        )

    def get(self, run_id: str) -> RevampedRun | None:
        with self.lock:
            job = self._load(run_id)
            return job.model_copy(deep=True) if job else None

    def prepare(self, run: Run, retry_failed: bool = False) -> tuple[RevampedRun, bool]:
        with self.lock:
            existing = self._load(run.id)
            if existing and (not retry_failed or existing.status in {"created", "running", "completed"}):
                return existing.model_copy(deep=True), False
            if run.status not in {"completed", "failed"}:
                raise HTTPException(409, "Wait for the original run to finish before generating improvements.")
            if self.generator is None:
                GeminiImageGenerator.check_configuration()
            if existing:
                job = existing.model_copy(deep=True)
                job.errors.pop("storage", None)
                for result in job.results.values():
                    for step in result.steps:
                        if step.generation_status == "failed":
                            step.generation_status = "pending"
                            step.generation_error = None
            else:
                job = RevampedRun(
                    id=run.id, url=run.url, task=run.task, personas=run.personas,
                    model=os.environ.get("GEMINI_IMAGE_MODEL", "").strip() or DEFAULT_IMAGE_MODEL,
                )
                for persona_id in run.personas:
                    result = run.results.get(persona_id)
                    if result is None:
                        job.errors[persona_id] = "The original run has no result for this persona."
                        continue
                    if not result.steps:
                        job.errors[persona_id] = "The original persona result contains no steps."
                    seen: set[int] = set()
                    for step in result.steps:
                        screenshot_path(run.id, persona_id, step.step)
                        if step.step in seen:
                            raise HTTPException(422, "Original step numbers must be unique per persona.")
                        seen.add(step.step)
                    job.results[persona_id] = RevampedResult(
                        success=result.success, summary=result.summary, score=result.score,
                        score_justification=result.score_justification,
                        steps=[RevampedStep(
                            **step.model_dump(exclude={"screenshot_url"}),
                            source_screenshot_url=step.screenshot_url,
                        ) for step in result.steps],
                    )
                job.expected_images = sum(len(result.steps) for result in job.results.values())
            self._summarize(job)
            pending = any(s.generation_status == "pending" for r in job.results.values() for s in r.steps)
            if pending:
                job.status = "created"
            self._save(job)
            self.jobs[job.id] = job
            return job.model_copy(deep=True), pending

    def execute(self, run: Run) -> None:
        with self.lock:
            job = self.jobs[run.id]
            job.status = "running"
            work = [(pid, step.step) for pid, result in job.results.items()
                    for step in result.steps if step.generation_status == "pending"]
        generator = self.generator or GeminiImageGenerator(job.model)
        try:
            for persona_id, number in work:
                url, error = None, None
                try:
                    result = run.results[persona_id]
                    step = next(s for s in result.steps if s.step == number)
                    if result.score is None or not result.score_justification or not result.score_justification.strip():
                        raise ImageGenerationError("The original persona result needs a score and score_justification.")
                    expected_url = f"/runs/{run.id}/personas/{persona_id}/steps/{number}/screenshot"
                    if step.screenshot_url != expected_url:
                        raise ImageGenerationError("The step has no matching original screenshot URL.")
                    source_path = screenshot_path(run.id, persona_id, number)
                    if not source_path.is_file():
                        raise ImageGenerationError("The original step screenshot is missing from disk.")
                    if source_path.stat().st_size > MAX_IMAGE_BYTES:
                        raise ImageGenerationError("The original screenshot exceeds the 20 MB limit.")
                    source = image_to_png(source_path.read_bytes())
                    prompt = build_revamp_prompt(run, persona_id, result, step)
                    with self.capacity:
                        generated = generator(prompt, source)
                    png = image_to_png(generated)
                    url = save_fixed_screenshot(run.id, persona_id, number, png)
                except ImageGenerationError as exc:
                    error = str(exc)
                except Exception:
                    error = "This image could not be generated or saved. Retry this step when the problem is resolved."
                with self.lock:
                    target = next(s for s in job.results[persona_id].steps if s.step == number)
                    target.screenshot_url = url
                    target.generation_status = "failed" if error else "completed"
                    target.generation_error = error
                    self._summarize(job)
                    self._save(job)
        except Exception:
            # Ensure even disk/manifest failures do not leave the in-memory job running forever.
            with self.lock:
                for result in job.results.values():
                    for step in result.steps:
                        if step.generation_status == "pending":
                            step.generation_status = "failed"
                            step.generation_error = "Generation stopped because its progress could not be saved."
                job.errors["storage"] = "Unable to persist generation progress. Check artifact storage."
                self._summarize(job)


def create_revamp_router(runs: dict[str, Run], service: RevampService | None = None) -> APIRouter:
    service = service or RevampService()
    router = APIRouter(tags=["Image improvements"])

    def find_job(run_id: str) -> RevampedRun:
        try:
            job = service.get(run_id)
        except ValueError:
            raise HTTPException(404, "Improved results not found") from None
        except OSError:
            raise HTTPException(503, "Improved results storage is unavailable") from None
        if job is None:
            raise HTTPException(404, "Improved results not found. POST to this endpoint to start generation.")
        return job

    @router.post("/runs/{run_id}/revamp", response_model=RevampedRun, status_code=202)
    async def start_revamp(
        run_id: str, background_tasks: BackgroundTasks, response: Response,
        retry_failed: bool = Query(False),
    ) -> RevampedRun:
        run = runs.get(run_id)
        if run is None:
            # Completed artifacts remain readable after a backend restart.
            if not retry_failed:
                job = find_job(run_id)
                response.status_code = 200
                return job
            raise HTTPException(404, "Original run not found; retries require its original results.")
        try:
            job, should_start = service.prepare(run, retry_failed)
        except ImageGenerationError as exc:
            raise HTTPException(503, str(exc)) from None
        except ValueError:
            raise HTTPException(422, "Invalid run, persona, step or saved manifest") from None
        except OSError:
            raise HTTPException(503, "Unable to create improved image artifacts") from None
        if should_start:
            background_tasks.add_task(service.execute, run.model_copy(deep=True))
        else:
            response.status_code = 200
        return job

    @router.get("/runs/{run_id}/revamp", response_model=RevampedRun)
    async def get_revamp(run_id: str) -> RevampedRun:
        return find_job(run_id)

    @router.get("/runs/{run_id}/personas/{persona_id}/steps/{step}/screenshot-fixed", response_class=FileResponse)
    async def get_fixed_screenshot(run_id: str, persona_id: str, step: int) -> FileResponse:
        job = find_job(run_id)
        result = job.results.get(persona_id)
        record = next((s for s in result.steps if s.step == step), None) if result else None
        if record is None or record.generation_status != "completed" or not record.screenshot_url:
            raise HTTPException(404, "Improved screenshot not found")
        try:
            path = fixed_artifact_path(run_id, persona_id, step)
        except ValueError:
            raise HTTPException(404, "Improved screenshot not found") from None
        if not path.is_file():
            raise HTTPException(404, "Improved screenshot not found")
        return FileResponse(path, media_type="image/png", headers={"Cache-Control": "private, max-age=86400"})

    return router
