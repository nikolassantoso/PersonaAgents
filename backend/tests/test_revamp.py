import io
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

import artifacts
from gemini_images import GeminiImageGenerator, ImageGenerationError, image_to_png
from models import Run, StepRecord, TaskResult
from revamp import RevampService, create_revamp_router


def png(color="white"):
    output = io.BytesIO()
    Image.new("RGB", (64, 40), color).save(output, format="PNG")
    return output.getvalue()


@pytest.fixture
def source_run(tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts, "SCREENSHOT_ROOT", tmp_path / "screenshots")
    monkeypatch.setattr(artifacts, "FIXED_SCREENSHOT_ROOT", tmp_path / "screenshots_fixed")
    run = Run(id="example-run", url="https://www.wikipedia.org/", task="Find Pikachu",
              personas=["first_time", "elderly"], status="completed")
    for persona, count, score in [("first_time", 3, 9), ("elderly", 5, 6)]:
        run.results[persona] = TaskResult(
            success=True, summary="Found Pikachu", score=score,
            score_justification=f"{persona}: Improve readable text and reduce popup friction.",
            steps=[StepRecord(
                step=n, action="click", reasoning=f"{persona} reasoning for step {n}", outcome="ok",
                screenshot_url=artifacts.save_step_screenshot(run.id, persona, n, png()),
            ) for n in range(1, count + 1)],
        )
    return run


def client_for(run, service):
    app = FastAPI()
    app.include_router(create_revamp_router({run.id: run}, service))
    return TestClient(app)


def test_eight_images_one_per_step_and_originals_unchanged(source_run):
    calls = []
    original = source_run.model_dump_json()
    def generate(prompt, image):
        calls.append((prompt, image))
        return png("green")
    service = RevampService(generate)
    client = client_for(source_run, service)
    response = client.post("/runs/example-run/revamp")
    assert response.status_code == 202
    # BackgroundTasks execute after the response body; polling exposes final results.
    job = client.get("/runs/example-run/revamp").json()
    assert job["status"] == "completed"
    assert (job["expected_images"], job["generated_images"], job["failed_images"]) == (8, 8, 0)
    assert [len(r["steps"]) for r in job["results"].values()] == [3, 5]
    assert len(calls) == 8
    index = 0
    for persona_id, result in source_run.results.items():
        for step in result.steps:
            prompt, image = calls[index]
            assert result.score_justification in prompt
            assert f"{result.score}/10" in prompt
            assert step.reasoning in prompt
            assert f"Step: {step.step}" in prompt
            assert image == png()
            output_step = job["results"][persona_id]["steps"][step.step - 1]
            assert output_step["source_screenshot_url"] == step.screenshot_url
            assert output_step["screenshot_url"] != step.screenshot_url
            downloaded = client.get(output_step["screenshot_url"])
            assert downloaded.status_code == 200
            assert downloaded.headers["content-type"] == "image/png"
            assert downloaded.content == png("green")
            assert artifacts.screenshot_path(source_run.id, persona_id, step.step).read_bytes() == png()
            index += 1
    assert source_run.model_dump_json() == original
    assert len(list(artifacts.FIXED_SCREENSHOT_ROOT.rglob("*.png"))) == 8
    # Repeated POST/GET cannot inadvertently consume another eight generations.
    assert client.post("/runs/example-run/revamp").status_code == 200
    assert client.get("/runs/example-run/revamp").status_code == 200
    assert len(calls) == 8


def test_partial_failure_and_explicit_retry_only_failed_step(source_run):
    calls = []
    def generate(prompt, image):
        calls.append(prompt)
        if "elderly reasoning for step 2" in prompt and len(calls) <= 8:
            raise RuntimeError("secret-provider-token")
        return png("blue")
    service = RevampService(generate)
    client = client_for(source_run, service)
    client.post("/runs/example-run/revamp")
    response = client.get("/runs/example-run/revamp")
    job = response.json()
    assert job["status"] == "partial"
    assert job["generated_images"] == 7 and job["failed_images"] == 1
    failed = job["results"]["elderly"]["steps"][1]
    assert failed["screenshot_url"] is None
    assert failed["generation_status"] == "failed"
    assert "secret-provider-token" not in response.text
    assert len(job["results"]["elderly"]["steps"]) == 5
    assert client.get("/runs/example-run/personas/elderly/steps/2/screenshot-fixed").status_code == 404
    assert client.post("/runs/example-run/revamp").status_code == 200
    assert len(calls) == 8
    assert client.post("/runs/example-run/revamp?retry_failed=true").status_code == 202
    assert len(calls) == 9
    assert "elderly reasoning for step 2" in calls[-1]
    assert client.get("/runs/example-run/revamp").json()["generated_images"] == 8


@pytest.mark.parametrize("problem", ["missing_file", "missing_url", "foreign_url", "invalid_image", "missing_score"])
def test_bad_source_is_an_explicit_step_failure_not_an_invented_image(source_run, problem):
    calls = []
    step = source_run.results["first_time"].steps[0]
    path = artifacts.screenshot_path(source_run.id, "first_time", 1)
    if problem == "missing_file":
        path.unlink()
    elif problem == "missing_url":
        step.screenshot_url = None
    elif problem == "foreign_url":
        step.screenshot_url = "https://untrusted.example/image.png"
    elif problem == "invalid_image":
        path.write_bytes(b"not an image")
    else:
        source_run.results["first_time"].score = None
    def generate(prompt, image):
        calls.append(prompt)
        return png()
    service = RevampService(generate)
    client = client_for(source_run, service)
    client.post("/runs/example-run/revamp")
    job = client.get("/runs/example-run/revamp").json()
    assert job["status"] == "partial"
    assert job["expected_images"] == 8
    assert job["generated_images"] == (5 if problem == "missing_score" else 7)
    assert job["results"]["first_time"]["steps"][0]["generation_error"]
    assert len(calls) == job["generated_images"]


def test_no_key_and_unfinished_run_rejected_before_scheduling(source_run, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_AI", raising=False)
    service = RevampService()
    client = client_for(source_run, service)
    assert client.post("/runs/example-run/revamp").status_code == 503
    assert service.jobs == {}
    source_run.status = "running"
    assert client.post("/runs/example-run/revamp").status_code == 409
    assert client.get("/runs/not-a-run/revamp").status_code == 404
    assert client.post("/runs/not-a-run/revamp").status_code == 404


def test_concurrent_reservations_schedule_only_one_job(source_run):
    service = RevampService(lambda prompt, image: png())
    with ThreadPoolExecutor(max_workers=6) as pool:
        responses = list(pool.map(lambda _: service.prepare(source_run), range(6)))
    assert sum(should_start for _, should_start in responses) == 1


def test_saved_results_survive_restart_without_original_run(source_run):
    service = RevampService(lambda prompt, image: png())
    client = client_for(source_run, service)
    client.post("/runs/example-run/revamp")
    app = FastAPI()
    app.include_router(create_revamp_router({}, RevampService()))
    restarted = TestClient(app)
    job = restarted.get("/runs/example-run/revamp").json()
    assert job["status"] == "completed" and job["generated_images"] == 8
    assert restarted.get(job["results"]["first_time"]["steps"][0]["screenshot_url"]).status_code == 200
    assert restarted.post("/runs/example-run/revamp").status_code == 200
    assert restarted.post("/runs/example-run/revamp?retry_failed=true").status_code == 404


def test_interrupted_job_is_recoverable(source_run):
    service = RevampService(lambda prompt, image: png())
    service.prepare(source_run)
    restarted = RevampService(lambda prompt, image: png())
    job = restarted.get(source_run.id)
    assert job.status == "failed" and job.failed_images == 8
    client = client_for(source_run, restarted)
    client.post("/runs/example-run/revamp?retry_failed=true")
    assert client.get("/runs/example-run/revamp").json()["status"] == "completed"


def test_invalid_identifiers_and_duplicate_steps_cannot_overwrite_artifacts(source_run):
    for args in [("..", "first_time", 1), ("run", "../escape", 1), ("run", "persona", 0)]:
        with pytest.raises(ValueError):
            artifacts.fixed_artifact_path(*args)
    source_run.results["first_time"].steps[1].step = 1
    client = client_for(source_run, RevampService(lambda prompt, image: png()))
    assert client.post("/runs/example-run/revamp").status_code == 422
    assert not artifacts.FIXED_SCREENSHOT_ROOT.exists()


def test_missing_result_and_unscored_failed_persona_do_not_report_complete(source_run):
    del source_run.results["elderly"]
    source_run.status = "failed"
    source_run.results["first_time"].success = False
    source_run.results["first_time"].score = None
    source_run.results["first_time"].score_justification = None
    def never_call(prompt, image):
        pytest.fail("Unscored results must not be sent to Gemini")
    client = client_for(source_run, RevampService(never_call))
    client.post("/runs/example-run/revamp")
    job = client.get("/runs/example-run/revamp").json()
    assert job["status"] == "failed"
    assert job["expected_images"] == 3 and job["failed_images"] == 3
    assert "elderly" in job["errors"]


def test_invalid_output_and_all_provider_failures_are_terminal(source_run):
    client = client_for(source_run, RevampService(lambda prompt, image: b"not a PNG"))
    client.post("/runs/example-run/revamp")
    job = client.get("/runs/example-run/revamp").json()
    assert job["status"] == "failed" and job["failed_images"] == 8
    assert not list(artifacts.FIXED_SCREENSHOT_ROOT.rglob("*.png"))


def test_gemini_sdk_request_uses_reference_image_and_one_attempt(monkeypatch):
    from google import genai
    from google.genai import types

    captured = {}
    payload = io.BytesIO()
    Image.new("RGB", (64, 40), "yellow").save(payload, format="JPEG")
    class FakeClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.models = self
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def generate_content(self, **kwargs):
            captured.update(kwargs)
            return types.GenerateContentResponse(candidates=[types.Candidate(content=types.Content(parts=[
                types.Part(text="Explanation"),
                types.Part(inline_data=types.Blob(data=png("red"), mime_type="image/png"), thought=True),
                types.Part.from_bytes(data=payload.getvalue(), mime_type="image/jpeg"),
                types.Part.from_bytes(data=png("blue"), mime_type="image/png"),
            ]))])
    monkeypatch.setattr(genai, "Client", FakeClient)
    monkeypatch.setenv("GEMINI_API_KEY", "test-only-key")
    image = GeminiImageGenerator("test-image-model")("The score justification", png())
    assert image.startswith(b"\x89PNG\r\n\x1a\n")
    assert captured["contents"][0] == "The score justification"
    assert captured["contents"][1].inline_data.data == png()
    assert captured["http_options"].timeout == 120_000
    assert captured["http_options"].retry_options.attempts == 1
    assert captured["model"] == "test-image-model"
    assert captured["config"].response_modalities == ["TEXT", "IMAGE"]
    assert Image.open(io.BytesIO(image)).getpixel((0, 0)) != (255, 0, 0)


@pytest.mark.parametrize("provider_fails", [True, False])
def test_gemini_failure_and_text_only_response_are_safe(monkeypatch, provider_fails):
    from google import genai
    class FakeClient:
        def __init__(self, **kwargs):
            self.models = self
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def generate_content(self, **kwargs):
            if provider_fails:
                raise RuntimeError("sensitive-api-key")
            return SimpleNamespace(candidates=[])
    monkeypatch.setattr(genai, "Client", FakeClient)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_AI", "sensitive-api-key")
    with pytest.raises(ImageGenerationError) as failure:
        GeminiImageGenerator("test-model")("prompt", png())
    assert "sensitive-api-key" not in str(failure.value)


def test_png_validation():
    with pytest.raises(ImageGenerationError):
        image_to_png(b"malformed")


def test_missing_justification_fails_only_affected_persona(source_run):
    source_run.results["elderly"].score_justification = "   "
    calls = []
    def generate(prompt, image):
        calls.append(prompt)
        return png()
    client = client_for(source_run, RevampService(generate))
    client.post("/runs/example-run/revamp")
    job = client.get("/runs/example-run/revamp").json()
    assert job["generated_images"] == 3 and job["failed_images"] == 5
    assert len(calls) == 3


def test_unwritable_manifest_rejects_job_without_generation(source_run, monkeypatch):
    service = RevampService(lambda prompt, image: pytest.fail("Must not call provider"))
    def fail_save(job):
        raise OSError("Disk full")
    monkeypatch.setattr(service, "_save", fail_save)
    client = client_for(source_run, service)
    assert client.post("/runs/example-run/revamp").status_code == 503
    assert service.jobs == {}


def test_progress_storage_failure_is_terminal_and_can_be_retried(source_run, monkeypatch):
    calls = []
    def generate(prompt, image):
        calls.append(prompt)
        return png()
    service = RevampService(generate)
    service.prepare(source_run)
    normal_save = service._save
    def fail_save(job):
        raise OSError("Disk full")
    monkeypatch.setattr(service, "_save", fail_save)
    service.execute(source_run)
    job = service.get(source_run.id)
    assert job.status == "partial"
    assert job.generated_images == 1 and job.failed_images == 7
    assert "storage" in job.errors
    monkeypatch.setattr(service, "_save", normal_save)
    client = client_for(source_run, service)
    client.post("/runs/example-run/revamp?retry_failed=true")
    job = client.get("/runs/example-run/revamp").json()
    assert job["status"] == "completed" and job["errors"] == {}
    assert len(calls) == 8


def test_get_returns_running_progress_without_duplicate_work(source_run):
    service = RevampService(lambda prompt, image: png())
    service.prepare(source_run)
    client = client_for(source_run, service)
    response = client.get("/runs/example-run/revamp")
    assert response.status_code == 200
    assert response.json()["status"] == "created"
    assert response.json()["generated_images"] == 0
    assert client.post("/runs/example-run/revamp?retry_failed=true").status_code == 200
    assert service.get(source_run.id).generated_images == 0
