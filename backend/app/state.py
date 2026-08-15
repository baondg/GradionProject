"""Pipeline cursor, claim gate, and API view. Spec: docs/plan.md §3."""

from __future__ import annotations

from typing import Any

STEPS: tuple[str, ...] = (
    "style",
    "characters",
    "portraits",
    "chapters",
    "illustrations",
)
_CURSOR: tuple[str, ...] = ("none",) + STEPS


def next_step(completed_step: str) -> str | None:
    index = _CURSOR.index(completed_step)
    if index >= len(_CURSOR) - 1:
        return None
    return _CURSOR[index + 1]


def can_claim(doc: dict[str, Any], boot_id: str) -> bool:
    run = doc["run"]
    if run in ("idle", "failed"):
        return True
    return run == "running" and doc.get("run_boot_id") != boot_id


def to_view(doc: dict[str, Any], boot_id: str) -> dict[str, Any]:
    completed_step = doc["completed_step"]
    run = doc["run"]
    stuck = run == "running" and doc.get("run_boot_id") != boot_id
    current_step = next_step(completed_step)

    if completed_step == "none" and run == "idle":
        status = "draft"
    elif completed_step == "illustrations" and run == "idle":
        status = "done"
    else:
        status = "in_progress"

    if stuck:
        action = "recover"
    elif run == "running":
        action = "wait"
    elif run == "failed":
        action = "retry"
    elif completed_step == "illustrations" and run == "idle":
        action = "none"
    else:
        action = "run"

    completed_index = _CURSOR.index(completed_step)
    steps = []
    for key in STEPS:
        if _CURSOR.index(key) <= completed_index:
            view = "done"
        elif key == current_step:
            view = "current"
        else:
            view = "pending"
        steps.append({"key": key, "view": view})

    return {
        "id": doc["id"],
        "title": doc["title"],
        "created_at": doc["created_at"],
        "status": status,
        "completed_step": completed_step,
        "current_step": current_step,
        "run": run,
        "stuck": stuck,
        "action": action,
        "steps": steps,
        "error": doc.get("error"),
    }
