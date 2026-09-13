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


def fixed_artifact_path(run_id: str, persona_id: str | None = None, step: int = 1) -> Path:
    """Keep generated images and their manifest within the fixed artifacts root."""
    screenshot_path(run_id, persona_id or "manifest", step)  # shared ID validation
    root = FIXED_SCREENSHOT_ROOT.resolve()
    path = root / run_id / "revamp.json"
    if persona_id is not None:
        path = root / run_id / persona_id / f"step-{step:03d}.png"
    resolved = path.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("Invalid artifact path.")
    return resolved


def write_artifact_atomic(path: Path, data: bytes) -> None:
    """Readers should never receive a partially written image or manifest."""
    from uuid import uuid4

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_bytes(data)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def save_fixed_screenshot(run_id: str, persona_id: str, step: int, image: bytes) -> str:
    write_artifact_atomic(fixed_artifact_path(run_id, persona_id, step), image)
    return f"/runs/{run_id}/personas/{persona_id}/steps/{step}/screenshot-fixed"
