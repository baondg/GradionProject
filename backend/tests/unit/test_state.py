"""Pure state-machine tests for next_step, can_claim, and to_view.

Imports from app.state, which does not exist yet — this file should fail (red).
Spec: docs/plan.md §3 and §8.1.
"""

from __future__ import annotations

import pytest

from app.state import can_claim, next_step, to_view

LIVE_BOOT = "boot-live"
STALE_BOOT = "boot-old"

STEP_ORDER = ("style", "characters", "portraits", "chapters", "illustrations")


def make_doc(**overrides: object) -> dict:
    doc: dict = {
        "id": "proj-1",
        "user_email": "mira@example.com",
        "title": "The Wind in the Willows",
        "created_at": "2026-08-13T12:00:00+00:00",
        "completed_step": "none",
        "run": "idle",
        "run_started_at": None,
        "run_boot_id": None,
        "error": None,
        "style": None,
        "style_source": None,
        "characters": [],
        "chapters": [],
        "gemini": {"file_id": None, "interaction_id": None},
    }
    doc.update(overrides)
    return doc


# --- next_step ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("completed", "expected"),
    [
        ("none", "style"),
        ("style", "characters"),
        ("characters", "portraits"),
        ("portraits", "chapters"),
        ("chapters", "illustrations"),
        ("illustrations", None),
    ],
)
def test_next_step_follows_pipeline_order(completed: str, expected: str | None) -> None:
    assert next_step(completed) == expected


# --- can_claim ----------------------------------------------------------------
# Gate is only run + boot id. Wrong-step and "already done" are checked elsewhere.


def test_can_claim_idle() -> None:
    assert can_claim(make_doc(run="idle"), LIVE_BOOT) is True


def test_can_claim_failed() -> None:
    assert (
        can_claim(
            make_doc(
                run="failed",
                completed_step="style",
                error={"code": "gemini_error", "message": "boom"},
            ),
            LIVE_BOOT,
        )
        is True
    )


def test_can_claim_stale_running() -> None:
    assert (
        can_claim(
            make_doc(run="running", run_boot_id=STALE_BOOT, completed_step="characters"),
            LIVE_BOOT,
        )
        is True
    )


def test_can_claim_live_running_rejected() -> None:
    assert (
        can_claim(
            make_doc(run="running", run_boot_id=LIVE_BOOT, completed_step="characters"),
            LIVE_BOOT,
        )
        is False
    )


def test_can_claim_running_with_null_boot_id_is_stale() -> None:
    assert can_claim(make_doc(run="running", run_boot_id=None), LIVE_BOOT) is True


# --- to_view ------------------------------------------------------------------


def _step_views(view: dict) -> dict[str, str]:
    return {item["key"]: item["view"] for item in view["steps"]}


def test_to_view_fresh_project_is_draft_ready_to_run() -> None:
    view = to_view(make_doc(), LIVE_BOOT)

    assert view["status"] == "draft"
    assert view["completed_step"] == "none"
    assert view["current_step"] == "style"
    assert view["run"] == "idle"
    assert view["stuck"] is False
    assert view["action"] == "run"
    assert view["error"] is None
    assert _step_views(view) == {
        "style": "current",
        "characters": "pending",
        "portraits": "pending",
        "chapters": "pending",
        "illustrations": "pending",
    }
    assert [item["key"] for item in view["steps"]] == list(STEP_ORDER)


def test_to_view_idle_mid_pipeline_is_in_progress_run() -> None:
    view = to_view(make_doc(completed_step="characters"), LIVE_BOOT)

    assert view["status"] == "in_progress"
    assert view["current_step"] == "portraits"
    assert view["action"] == "run"
    assert view["stuck"] is False
    assert _step_views(view) == {
        "style": "done",
        "characters": "done",
        "portraits": "current",
        "chapters": "pending",
        "illustrations": "pending",
    }


def test_to_view_live_running_is_wait() -> None:
    view = to_view(
        make_doc(
            completed_step="style",
            run="running",
            run_boot_id=LIVE_BOOT,
            run_started_at="2026-08-13T12:01:00+00:00",
        ),
        LIVE_BOOT,
    )

    assert view["status"] == "in_progress"
    assert view["current_step"] == "characters"
    assert view["run"] == "running"
    assert view["stuck"] is False
    assert view["action"] == "wait"


def test_to_view_stale_running_is_stuck_recover() -> None:
    view = to_view(
        make_doc(
            completed_step="characters",
            run="running",
            run_boot_id=STALE_BOOT,
        ),
        LIVE_BOOT,
    )

    assert view["run"] == "running"
    assert view["stuck"] is True
    assert view["action"] == "recover"
    assert view["status"] == "in_progress"
    assert view["current_step"] == "portraits"


def test_to_view_failed_is_retry_cursor_unchanged() -> None:
    error = {"code": "gemini_error", "message": "quota"}
    view = to_view(
        make_doc(completed_step="portraits", run="failed", error=error),
        LIVE_BOOT,
    )

    assert view["status"] == "in_progress"
    assert view["completed_step"] == "portraits"
    assert view["current_step"] == "chapters"
    assert view["run"] == "failed"
    assert view["stuck"] is False
    assert view["action"] == "retry"
    assert view["error"] == error


def test_to_view_failed_before_any_step_is_not_draft() -> None:
    view = to_view(
        make_doc(
            completed_step="none",
            run="failed",
            error={"code": "gemini_error", "message": "boom"},
        ),
        LIVE_BOOT,
    )

    assert view["status"] == "in_progress"
    assert view["action"] == "retry"
    assert view["current_step"] == "style"


def test_to_view_done_project() -> None:
    view = to_view(make_doc(completed_step="illustrations", run="idle"), LIVE_BOOT)

    assert view["status"] == "done"
    assert view["current_step"] is None
    assert view["action"] == "none"
    assert view["stuck"] is False
    assert _step_views(view) == {key: "done" for key in STEP_ORDER}


def test_to_view_does_not_expose_disk_only_fields() -> None:
    view = to_view(
        make_doc(run="running", run_boot_id=LIVE_BOOT, completed_step="style"),
        LIVE_BOOT,
    )

    assert "run_boot_id" not in view
    assert "gemini" not in view
    assert "run_started_at" not in view
    assert "user_email" not in view
