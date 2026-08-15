"""Storage tests: project.json / users.json roundtrips and fcntl flock.

Imports from app.storage, which does not exist yet — this file should fail (red).
Spec: docs/plan.md §2.2, §3.1 (per-project flock; users.json has its own flock).

Expected API (Storage(data_dir)):

- save_project(doc) / load_project(id)
  Writes/reads data_dir/projects/{id}/project.json under that file's flock.
- update_project(id, mutator)
  flock → load → mutator(doc) → save → unlock. mutator may mutate in place.
- load_users() / update_users(mutator)
  Same pattern for data_dir/users.json. Missing file loads as {"users": {}}.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

from app.storage import Storage

PROJECT_ID = "proj-1"


def make_project(**overrides: object) -> dict:
    doc: dict = {
        "id": PROJECT_ID,
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
        "seq": 0,
    }
    doc.update(overrides)
    return doc


@pytest.fixture
def storage(tmp_path: Path) -> Storage:
    return Storage(tmp_path)


def _run_threads(workers: list) -> None:
    errors: list[BaseException] = []

    def wrap(fn) -> None:
        try:
            fn()
        except BaseException as exc:  # noqa: BLE001 — surface any thread failure
            errors.append(exc)

    threads = [threading.Thread(target=wrap, args=(fn,)) for fn in workers]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []


# --- project.json save / load -------------------------------------------------


def test_save_and_load_project_roundtrip(storage: Storage, tmp_path: Path) -> None:
    original = make_project(title="River Bank", completed_step="style")
    storage.save_project(original)

    path = tmp_path / "projects" / PROJECT_ID / "project.json"
    assert path.is_file()

    loaded = storage.load_project(PROJECT_ID)
    assert loaded["id"] == PROJECT_ID
    assert loaded["title"] == "River Bank"
    assert loaded["completed_step"] == "style"
    assert loaded["run"] == "idle"
    assert loaded["run_boot_id"] is None
    assert loaded["gemini"] == {"file_id": None, "interaction_id": None}


def test_load_project_missing_raises(storage: Storage) -> None:
    with pytest.raises(FileNotFoundError):
        storage.load_project("does-not-exist")


def test_save_project_overwrites(storage: Storage) -> None:
    storage.save_project(make_project(run="idle"))
    storage.save_project(make_project(run="running", run_boot_id="boot-1"))
    loaded = storage.load_project(PROJECT_ID)
    assert loaded["run"] == "running"
    assert loaded["run_boot_id"] == "boot-1"


def test_update_project_mutates_under_lock(storage: Storage) -> None:
    storage.save_project(make_project())

    def claim(doc: dict) -> None:
        doc["run"] = "running"
        doc["run_boot_id"] = "boot-live"

    result = storage.update_project(PROJECT_ID, claim)
    assert result["run"] == "running"
    assert storage.load_project(PROJECT_ID)["run_boot_id"] == "boot-live"


# --- project.json concurrent writes -------------------------------------------


def test_concurrent_save_project_does_not_corrupt_json(
    storage: Storage, tmp_path: Path
) -> None:
    """Two threads writing large different payloads; file must stay valid JSON."""
    storage.save_project(make_project())
    barrier = threading.Barrier(2)
    payload_a = make_project(blob="A" * 20_000, winner="A")
    payload_b = make_project(blob="B" * 20_000, winner="B")

    def write(doc: dict) -> None:
        barrier.wait()
        for _ in range(30):
            storage.save_project(doc)

    _run_threads([lambda: write(payload_a), lambda: write(payload_b)])

    raw = (tmp_path / "projects" / PROJECT_ID / "project.json").read_text()
    parsed = json.loads(raw)
    assert parsed["winner"] in ("A", "B")
    assert parsed["blob"] == parsed["winner"] * 20_000
    loaded = storage.load_project(PROJECT_ID)
    assert loaded["winner"] == parsed["winner"]


def test_concurrent_update_project_does_not_lose_increments(storage: Storage) -> None:
    """flock around read-modify-write: both increments must land (seq == 2)."""
    storage.save_project(make_project(seq=0))
    barrier = threading.Barrier(2)

    def bump() -> None:
        def add_one(doc: dict) -> None:
            current = doc["seq"]
            time.sleep(0.05)
            doc["seq"] = current + 1

        barrier.wait()
        storage.update_project(PROJECT_ID, add_one)

    _run_threads([bump, bump])
    assert storage.load_project(PROJECT_ID)["seq"] == 2


# --- users.json ---------------------------------------------------------------


def test_load_users_missing_is_empty(storage: Storage) -> None:
    assert storage.load_users() == {"users": {}}


def test_update_users_roundtrip(storage: Storage, tmp_path: Path) -> None:
    def add_mira(users: dict) -> None:
        users["users"]["mira@example.com"] = {
            "email": "mira@example.com",
            "name": "Mira Hassan",
            "project_ids": [PROJECT_ID],
        }

    storage.update_users(add_mira)
    assert (tmp_path / "users.json").is_file()

    loaded = storage.load_users()
    assert loaded["users"]["mira@example.com"]["name"] == "Mira Hassan"
    assert loaded["users"]["mira@example.com"]["project_ids"] == [PROJECT_ID]


def test_concurrent_update_users_does_not_lose_project_ids(storage: Storage) -> None:
    def seed(users: dict) -> None:
        users["users"]["mira@example.com"] = {
            "email": "mira@example.com",
            "name": "Mira Hassan",
            "project_ids": [],
        }

    storage.update_users(seed)
    barrier = threading.Barrier(2)

    def append(project_id: str) -> None:
        def add_id(users: dict) -> None:
            ids = users["users"]["mira@example.com"]["project_ids"]
            time.sleep(0.05)
            ids.append(project_id)

        barrier.wait()
        storage.update_users(add_id)

    _run_threads([lambda: append("p-a"), lambda: append("p-b")])
    ids = storage.load_users()["users"]["mira@example.com"]["project_ids"]
    assert sorted(ids) == ["p-a", "p-b"]
