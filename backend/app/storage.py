"""JSON-on-disk storage with per-file fcntl flock. Spec: docs/plan.md §3.1."""

from __future__ import annotations

import fcntl
import json
import os
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

Mutator = Callable[[dict[str, Any]], Any]


class Storage:
    def __init__(self, data_dir: Path | str) -> None:
        self.data_dir = Path(data_dir)

    def save_project(self, doc: dict[str, Any]) -> None:
        path = self._project_path(doc["id"])
        with self._locked(path, create=True) as handle:
            _write_json(handle, doc)

    def load_project(self, project_id: str) -> dict[str, Any]:
        path = self._project_path(project_id)
        with self._locked(path, create=False) as handle:
            return _read_json(handle)

    def update_project(self, project_id: str, mutator: Mutator) -> dict[str, Any]:
        path = self._project_path(project_id)
        with self._locked(path, create=False) as handle:
            doc = _read_json(handle)
            result = mutator(doc)
            if result is not None:
                doc = result
            _write_json(handle, doc)
            return doc

    def load_users(self) -> dict[str, Any]:
        path = self._users_path()
        if not path.is_file():
            return {"users": {}}
        with self._locked(path, create=False) as handle:
            return _read_json(handle) or {"users": {}}

    def update_users(self, mutator: Mutator) -> dict[str, Any]:
        path = self._users_path()
        with self._locked(path, create=True) as handle:
            raw = handle.read()
            users: dict[str, Any] = json.loads(raw) if raw.strip() else {"users": {}}
            result = mutator(users)
            if result is not None:
                users = result
            _write_json(handle, users)
            return users

    def _project_path(self, project_id: str) -> Path:
        return self.data_dir / "projects" / project_id / "project.json"

    def _users_path(self) -> Path:
        return self.data_dir / "users.json"

    @contextmanager
    def _locked(self, path: Path, *, create: bool) -> Iterator[Any]:
        if create:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch(exist_ok=True)
        elif not path.is_file():
            raise FileNotFoundError(path)

        with path.open("r+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield handle
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _read_json(handle: Any) -> dict[str, Any]:
    handle.seek(0)
    raw = handle.read()
    if not raw.strip():
        raise FileNotFoundError("empty json file")
    data = json.loads(raw)
    return data


def _write_json(handle: Any, doc: dict[str, Any]) -> None:
    handle.seek(0)
    handle.truncate(0)
    json.dump(doc, handle, ensure_ascii=False)
    handle.flush()
    os.fsync(handle.fileno())
