import re
from pathlib import Path


SCREENSHOT_ROOT = Path(__file__).resolve().parent / "artifacts" / "screenshots"
FIXED_SCREENSHOT_ROOT = Path(__file__).resolve().parent / "artifacts" / "screenshots_fixed"
SAFE_PATH_COMPONENT = re.compile(r"^[A-Za-z0-9_-]+$")


def screenshot_path(run_id: str, persona_id: str, step: int) -> Path:
    """Return the local path for a validated step screenshot."""
    if not SAFE_PATH_COMPONENT.fullmatch(run_id):
        raise ValueError("Invalid run ID.")
    if not SAFE_PATH_COMPONENT.fullmatch(persona_id):
        raise ValueError("Invalid persona ID.")
    if step < 1:
        raise ValueError("Invalid step number.")

    return SCREENSHOT_ROOT / run_id / persona_id / f"step-{step:03d}.png"


def fixed_screenshot_path(run_id: str, persona_id: str, step: int) -> Path:
    """Return the local path for a validated AI-proposed screenshot."""
    if not SAFE_PATH_COMPONENT.fullmatch(run_id):
        raise ValueError("Invalid run ID.")
    if not SAFE_PATH_COMPONENT.fullmatch(persona_id):
        raise ValueError("Invalid persona ID.")
    if step < 1:
        raise ValueError("Invalid step number.")

    return FIXED_SCREENSHOT_ROOT / run_id / persona_id / f"step-{step:03d}.png"


def save_step_screenshot(
    run_id: str,
    persona_id: str,
    step: int,
    image: bytes,
) -> str:
    """Persist the exact image sent to the model and return its API path."""
    path = screenshot_path(run_id, persona_id, step)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(image)

    return (
        f"/runs/{run_id}/personas/{persona_id}"
        f"/steps/{step}/screenshot"
    )


def save_fixed_step_screenshot(
    run_id: str,
    persona_id: str,
    step: int,
    image: bytes,
) -> str:
    """Persist an AI-proposed screenshot and return its API path."""
    path = fixed_screenshot_path(run_id, persona_id, step)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(image)

    return (
        f"/runs/{run_id}/personas/{persona_id}"
        f"/steps/{step}/screenshot-fixed"
    )
