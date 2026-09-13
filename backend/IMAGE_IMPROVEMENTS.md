# Persona-based image improvements

Gemini creates one proposed redesign for **each original step screenshot**. The
complete persona `score_justification` and original `score` are repeated in every
request, together with that step's `reasoning`, action, task and reference image.
For the supplied Wikipedia example, this means **3 first-time-user images and 5
elderly-persona images**, not three images shared between personas.

These are generated design proposals. The original scores remain the source
evaluation, not a measured score of the proposed design. No website code or
browser behavior is changed by generating an image.

## Setup

From `backend`, install the additional dependencies in your Python environment:

```powershell
python -m pip install -r requirements-images.txt
```

Add `GEMINI_API_KEY` to `backend/.env`; `GEMINI_AI` is accepted as an alias.
`GEMINI_IMAGE_MODEL` defaults to `gemini-3.1-flash-image` and can be changed to an
image-capable Gemini model available to your account. The key stays server-side.
See `.env.images.example` for the configuration entries.

The implementation uses Google's `google-genai` SDK and its documented
[image editing API](https://ai.google.dev/gemini-api/docs/generate-content/image-generation#image_editing_text-and-image-to-image).

Run the existing backend on port 8000 with **one worker**, as the original run
store and generation coordination are in-process:

```powershell
python -m uvicorn main:app --port 8000
```

## 1. Start generation

Complete a normal persona run first, then:

```http
POST /runs/{run_id}/revamp
```

No body is required. The endpoint snapshots the original results and schedules
background work. A new job returns `202`; an existing job returns `200` and does
not call Gemini again. Runs still `created` or `running` return `409`. Missing
runs return `404`; missing Gemini configuration or unavailable storage returns
`503`.

PowerShell example:

```powershell
$runId = '35eb13c8-f8a4-4abb-bdd2-2f6627583a8d'
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/runs/$runId/revamp"
```

Each step makes its own image-to-image request. At most two provider requests
run concurrently across jobs within this server. Requests have a 120-second
timeout and no automatic retries; a timeout may still incur provider usage.
Normal `GET /runs/{run_id}` requests never start paid generation.

## 2. Retrieve progress and improved results

```http
GET /runs/{run_id}/revamp
```

Poll until `status` is `completed`, `partial`, or `failed`. While work remains,
status is `created` or `running`. The response keeps the original per-persona,
per-step structure, including the source score and reasoning. In this response,
`steps[].screenshot_url` points to the **improved image**;
`steps[].source_screenshot_url` retains the original image URL. The original
`GET /runs/{run_id}` response is not changed.

Illustrative shortened response (the real response includes every step):

```json
{
  "id": "35eb13c8-f8a4-4abb-bdd2-2f6627583a8d",
  "url": "https://www.wikipedia.org/",
  "personas": ["first_time", "elderly"],
  "task": "Search for Pikachu",
  "status": "completed",
  "model": "gemini-3.1-flash-image",
  "expected_images": 8,
  "generated_images": 8,
  "failed_images": 0,
  "results": {
    "first_time": {
      "success": true,
      "summary": "Found the Pikachu article.",
      "score": 9,
      "score_justification": "Search was easy; the donation popup caused minor friction.",
      "generation_status": "completed",
      "steps": [
        {
          "step": 1,
          "action": "fill",
          "element_index": 11,
          "value": "Pikachu",
          "reasoning": "I see the search bar and will type Pikachu.",
          "outcome": "ok",
          "source_screenshot_url": "/runs/35eb13c8-f8a4-4abb-bdd2-2f6627583a8d/personas/first_time/steps/1/screenshot",
          "screenshot_url": "/runs/35eb13c8-f8a4-4abb-bdd2-2f6627583a8d/personas/first_time/steps/1/screenshot-fixed",
          "generation_status": "completed",
          "generation_error": null
        }
      ]
    }
  },
  "errors": {}
}
```

`success`, `summary`, `score`, `score_justification`, `action` and `outcome` all
describe the **original** evaluation. Only the `generation_*` fields describe
the redesign job. A pending or failed image has `screenshot_url: null`.

Retrieve an individual image using its returned URL:

```http
GET /runs/{run_id}/personas/{persona_id}/steps/{step}/screenshot-fixed
```

This serves `image/png`, or `404` if the image is not ready or does not exist.
All URLs are backend-relative; a frontend using the existing Vite proxy should
prefix them with `/api`.

## Files and failure handling

```text
backend/artifacts/
  screenshots/{run_id}/{persona_id}/step-001.png       # Original, unchanged
  screenshots_fixed/{run_id}/revamp.json               # Durable result manifest
  screenshots_fixed/{run_id}/{persona_id}/step-001.png  # Improved image
```

Images and progress manifests are written atomically. Generated JPEG or WebP
responses are decoded and saved as real PNGs. Extra model images and internal
thought images are not exposed as extra step results. No arbitrary screenshot
URLs are fetched: reference pixels are read from the existing validated local
artifact path. Both source and generated images are validated before storage.

Every original step remains represented, even if generation fails. Missing
screenshots, missing scores/justifications, invalid images, provider refusals,
timeouts and storage errors are reported explicitly. `completed` means every
expected step generated an image; `partial` means some succeeded; `failed`
means none did. Personas without original results are identified in `errors`.

To retry **only failed steps**, preserving successful images:

```http
POST /runs/{run_id}/revamp?retry_failed=true
```

Retries require the original run to remain in the backend's in-memory store.
Saved improved results and PNGs remain readable after a restart, even when the
original run is gone. Interrupted pending steps become explicit failures when
their manifest is loaded after a restart. They do not restart paid requests
automatically. For multiple workers or distributed deployment, replace the
in-process job coordination with a shared queue and lock before enabling it.

## Tests

```powershell
python -m pip install -r requirements-test.txt
python -m pytest -q
```

Tests use temporary files and a mocked Gemini client. They exercise the actual
FastAPI routes, SDK request shape, 3-and-5 image counts, original preservation,
partial failures, retry behavior, duplicate submissions, persistence, and error
handling without using Gemini credits. Live generation additionally requires a
valid provider key, model access and original screenshots on disk.
