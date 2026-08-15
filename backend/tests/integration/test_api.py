"""HTTP integration tests for the FastAPI API. Spec: docs/plan.md §4–5, §8.1.

Fake Gemini is injected; no network. Each test gets a temporary data dir.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.gemini import FakeGeminiClient as FakeGemini
from app.main import create_app
from app.storage import Storage

EMAIL = "mira@example.com"
NAME = "Mira Hassan"
BOOT_ID = "test-boot"
BOOK = "The Mole had been working very hard all the morning."
STEPS = ("style", "characters", "portraits", "chapters", "illustrations")


@dataclass
class Harness:
    client: TestClient
    fake_gemini: FakeGemini
    data_dir: Path
    headers: dict[str, str] = field(default_factory=dict)


@pytest.fixture
def fake_gemini() -> FakeGemini:
    return FakeGemini()


@pytest.fixture
def harness(tmp_path: Path, fake_gemini: FakeGemini) -> Harness:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    app = create_app(data_dir=data_dir, gemini=fake_gemini, boot_id=BOOT_ID)
    with TestClient(app) as client:
        yield Harness(client=client, fake_gemini=fake_gemini, data_dir=data_dir)


@pytest.fixture
def identified(harness: Harness) -> Harness:
    response = harness.client.post(
        "/api/identify",
        json={"name": NAME, "email": EMAIL},
    )
    assert response.status_code == 200
    harness.headers = {"X-User-Email": EMAIL}
    return harness


def _create_project(harness: Harness, title: str = "Wind in the Willows") -> str:
    response = harness.client.post(
        "/api/projects",
        headers=harness.headers,
        json={"title": title, "text": BOOK},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "draft"
    return body["id"]


def _wait_until_not_running(harness: Harness, project_id: str) -> dict:
    for _ in range(80):
        response = harness.client.get(
            f"/api/projects/{project_id}",
            headers=harness.headers,
        )
        assert response.status_code == 200
        body = response.json()
        if body["run"] != "running" or body["stuck"]:
            return body
        time.sleep(0.05)
    raise AssertionError("project still running")


def _run_step(harness: Harness, project_id: str, step: str, json_body: dict | None = None) -> dict:
    response = harness.client.post(
        f"/api/projects/{project_id}/steps/{step}",
        headers=harness.headers,
        json=json_body if json_body is not None else {},
    )
    assert response.status_code == 202, response.text
    body = response.json()
    assert "run_boot_id" not in body
    assert "gemini" not in body
    return _wait_until_not_running(harness, project_id)


# --- identify -----------------------------------------------------------------


def test_identify_creates_user(harness: Harness) -> None:
    response = harness.client.post(
        "/api/identify",
        json={"name": NAME, "email": EMAIL},
    )
    assert response.status_code == 200
    assert response.json() == {"email": EMAIL, "name": NAME}

    me = harness.client.get("/api/me", headers={"X-User-Email": EMAIL})
    assert me.status_code == 200
    assert me.json() == {"email": EMAIL, "name": NAME}


def test_identify_updates_existing_user_name(harness: Harness) -> None:
    harness.client.post("/api/identify", json={"name": "Mira", "email": EMAIL})
    response = harness.client.post(
        "/api/identify",
        json={"name": NAME, "email": EMAIL},
    )
    assert response.status_code == 200
    assert response.json()["name"] == NAME

    me = harness.client.get("/api/me", headers={"X-User-Email": EMAIL})
    assert me.json()["name"] == NAME


def test_me_unknown_email_is_401(harness: Harness) -> None:
    response = harness.client.get("/api/me", headers={"X-User-Email": "nobody@example.com"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


# --- create + list ------------------------------------------------------------


def test_create_project_json(identified: Harness) -> None:
    response = identified.client.post(
        "/api/projects",
        headers=identified.headers,
        json={"title": "River Bank", "text": BOOK},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "River Bank"
    assert body["book_text"] == BOOK
    assert body["status"] == "draft"
    assert body["completed_step"] == "none"
    assert body["current_step"] == "style"
    assert body["run"] == "idle"
    assert body["action"] == "run"
    assert body["stuck"] is False
    assert identified.fake_gemini.calls == []
    assert identified.fake_gemini.book_sends == 0


def test_create_project_multipart(identified: Harness) -> None:
    response = identified.client.post(
        "/api/projects",
        headers=identified.headers,
        data={"title": "From upload"},
        files={"file": ("book.txt", BOOK.encode(), "text/plain")},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "From upload"
    assert body["book_text"] == BOOK
    assert body["status"] == "draft"


def test_list_projects_empty_then_one(identified: Harness) -> None:
    empty = identified.client.get("/api/projects", headers=identified.headers)
    assert empty.status_code == 200
    assert empty.json() == []

    project_id = _create_project(identified, title="Listed")
    listed = identified.client.get("/api/projects", headers=identified.headers)
    assert listed.status_code == 200
    rows = listed.json()
    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == project_id
    assert row["title"] == "Listed"
    assert row["status"] == "draft"
    assert row["action"] == "run"
    assert row["stuck"] is False
    assert "book_text" not in row
    assert "run_boot_id" not in row


# --- happy path ---------------------------------------------------------------


def test_five_step_happy_path(identified: Harness) -> None:
    project_id = _create_project(identified)

    style = _run_step(identified, project_id, "style")
    assert style["run"] == "idle"
    assert style["completed_step"] == "style"
    assert style["style_source"] == "generated"
    assert style["style"]
    assert style["current_step"] == "characters"
    assert style["action"] == "run"

    characters = _run_step(identified, project_id, "characters")
    assert characters["completed_step"] == "characters"
    assert len(characters["characters"]) == 2
    assert {c["name"] for c in characters["characters"]} == {"Mole", "Rat"}
    assert all(c["portrait_url"] is None for c in characters["characters"])

    portraits = _run_step(identified, project_id, "portraits")
    assert portraits["completed_step"] == "portraits"
    assert all(c["portrait_url"] for c in portraits["characters"])

    chapters = _run_step(identified, project_id, "chapters")
    assert chapters["completed_step"] == "chapters"
    assert len(chapters["chapters"]) == 1
    assert chapters["chapters"][0]["illustration_url"] is None

    done = _run_step(identified, project_id, "illustrations")
    assert done["status"] == "done"
    assert done["completed_step"] == "illustrations"
    assert done["current_step"] is None
    assert done["action"] == "none"
    assert done["run"] == "idle"
    assert done["chapters"][0]["illustration_url"]

    assert identified.fake_gemini.book_sends == 1
    assert identified.fake_gemini.calls == list(STEPS)


# --- duplicate in-flight ------------------------------------------------------


def test_duplicate_step_post_one_202_one_409(identified: Harness) -> None:
    project_id = _create_project(identified)
    fake = identified.fake_gemini
    fake.block()
    codes: list[int] = []

    def post_style() -> None:
        response = identified.client.post(
            f"/api/projects/{project_id}/steps/style",
            headers=identified.headers,
            json={},
        )
        codes.append(response.status_code)
        if response.status_code == 409:
            assert response.json()["error"]["code"] == "in_flight"

    first = threading.Thread(target=post_style)
    first.start()
    assert fake.entered.wait(timeout=2)

    second = threading.Thread(target=post_style)
    second.start()
    second.join(timeout=2)
    assert not second.is_alive()

    fake.unblock()
    first.join(timeout=2)
    assert not first.is_alive()

    assert sorted(codes) == [202, 409]
    assert fake.calls.count("style") == 1


# --- stuck recovery -----------------------------------------------------------


def test_stuck_recovery_after_foreign_boot_id(identified: Harness) -> None:
    project_id = _create_project(identified)
    storage = Storage(identified.data_dir)

    def mark_stuck(doc: dict) -> None:
        doc["run"] = "running"
        doc["run_boot_id"] = "dead-process-boot"
        doc["run_started_at"] = "2026-08-13T12:00:00+00:00"

    storage.update_project(project_id, mark_stuck)

    listed = identified.client.get("/api/projects", headers=identified.headers)
    assert listed.status_code == 200
    row = listed.json()[0]
    assert row["stuck"] is True
    assert row["action"] == "recover"
    assert row["run"] == "running"

    detail = identified.client.get(
        f"/api/projects/{project_id}",
        headers=identified.headers,
    )
    assert detail.status_code == 200
    body = detail.json()
    assert body["stuck"] is True
    assert body["action"] == "recover"
    assert body["current_step"] == "style"

    recovered = _run_step(identified, project_id, "style")
    assert recovered["stuck"] is False
    assert recovered["run"] == "idle"
    assert recovered["completed_step"] == "style"
    assert identified.fake_gemini.calls.count("style") == 1


# --- failure + retry ----------------------------------------------------------


def test_step_failure_then_retry(identified: Harness) -> None:
    project_id = _create_project(identified)
    identified.fake_gemini.fail_steps.add("style")

    response = identified.client.post(
        f"/api/projects/{project_id}/steps/style",
        headers=identified.headers,
        json={},
    )
    assert response.status_code == 202
    failed = _wait_until_not_running(identified, project_id)
    assert failed["run"] == "failed"
    assert failed["action"] == "retry"
    assert failed["completed_step"] == "none"
    assert failed["current_step"] == "style"
    assert failed["error"] is not None
    assert failed["error"]["message"]

    identified.fake_gemini.fail_steps.clear()
    retried = _run_step(identified, project_id, "style")
    assert retried["run"] == "idle"
    assert retried["completed_step"] == "style"
    assert retried["error"] is None
    assert identified.fake_gemini.calls.count("style") == 2
