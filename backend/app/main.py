"""FastAPI app. Spec: docs/plan.md §4–5."""

from __future__ import annotations

import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any, Literal

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from app.gemini import FakeGeminiClient, GeminiConfigError, RealGeminiClient
from app.state import STEPS, attempts_view, can_claim, next_step, to_view
from app.storage import Storage

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

MAX_CHARACTERS = 2
MAX_CHAPTERS = 1


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message


class IdentifyIn(BaseModel):
    name: str
    email: str


class AttemptOut(BaseModel):
    step: Literal["style", "characters", "portraits", "chapters", "illustrations"]
    at: str
    outcome: Literal["success", "failed"]
    message: str | None = None


class UnconfiguredGemini:
    def load_session(
        self,
        gemini_doc: dict[str, Any] | None = None,
        *,
        style: str | None = None,
    ) -> None:
        del gemini_doc, style

    def dump_session(self) -> dict[str, Any]:
        return {"file_id": None, "interaction_id": None}

    def send_book(self, text: str) -> None:
        raise RuntimeError("GEMINI_API_KEY is missing. Copy .env.example to .env.")

    def style(self, user_style: str | None = None) -> str:
        raise RuntimeError("GEMINI_API_KEY is missing. Copy .env.example to .env.")

    def characters(self) -> list[dict]:
        raise RuntimeError("GEMINI_API_KEY is missing. Copy .env.example to .env.")

    def portraits(self, characters: list[dict]) -> list[bytes]:
        raise RuntimeError("GEMINI_API_KEY is missing. Copy .env.example to .env.")

    def chapters(self) -> list[dict]:
        raise RuntimeError("GEMINI_API_KEY is missing. Copy .env.example to .env.")

    def illustrations(
        self,
        chapters: list[dict],
        portraits: list[bytes] | None = None,
    ) -> list[bytes]:
        raise RuntimeError("GEMINI_API_KEY is missing. Copy .env.example to .env.")


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def default_gemini() -> Any:
    # Same public methods as RealGeminiClient. Flip this off to use the
    # notebook Files + Interactions adapter; routes and session dump stay unchanged.
    if _truthy(os.environ.get("USE_FAKE_GEMINI")):
        return FakeGeminiClient()
    try:
        return RealGeminiClient.from_env()
    except GeminiConfigError:
        return UnconfiguredGemini()


def _error_body(code: str, message: str) -> dict[str, Any]:
    return {"error": {"code": code, "message": message}}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _project_dir(storage: Storage, project_id: str) -> Path:
    return storage.data_dir / "projects" / project_id


def _read_book(storage: Storage, project_id: str) -> str:
    return (_project_dir(storage, project_id) / "book.txt").read_text(encoding="utf-8")


def _write_book(storage: Storage, project_id: str, text: str) -> None:
    path = _project_dir(storage, project_id) / "book.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _detail_view(doc: dict[str, Any], boot_id: str, book_text: str) -> dict[str, Any]:
    view = to_view(doc, boot_id)
    project_id = doc["id"]
    view["book_text"] = book_text
    view["style"] = doc.get("style")
    view["style_source"] = doc.get("style_source")
    view["characters"] = [
        {
            "name": char.get("name", ""),
            "prompt": char.get("prompt", ""),
            "portrait_url": (
                f"/api/projects/{project_id}/files/portraits/{index}.png"
                if char.get("portrait_path")
                else None
            ),
        }
        for index, char in enumerate(doc.get("characters") or [])
    ]
    view["chapters"] = [
        {
            "name": chapter.get("name", ""),
            "prompt": chapter.get("prompt", ""),
            "illustration_url": (
                f"/api/projects/{project_id}/files/illustrations/{index}.png"
                if chapter.get("illustration_path")
                else None
            ),
        }
        for index, chapter in enumerate(doc.get("chapters") or [])
    ]
    view["attempts"] = [
        AttemptOut.model_validate(row).model_dump() for row in attempts_view(doc)
    ]
    return view


def _persist_gemini_session(doc: dict[str, Any], gemini: Any) -> dict[str, Any]:
    dump = getattr(gemini, "dump_session", None)
    if dump is None:
        return doc
    slot = doc.setdefault("gemini", {})
    for key, value in dump().items():
        if value is not None:
            slot[key] = value
    return doc


def _append_attempt(
    doc: dict[str, Any],
    *,
    step: str,
    outcome: str,
    message: str | None,
) -> None:
    rows = doc.setdefault("attempts", [])
    if not isinstance(rows, list):
        rows = []
        doc["attempts"] = rows
    rows.append(
        {
            "step": step,
            "at": _now(),
            "outcome": outcome,
            "message": message,
        }
    )


def _finish_ok(doc: dict[str, Any], claimed_boot: str, step: str) -> dict[str, Any]:
    if doc.get("run_boot_id") != claimed_boot:
        return doc
    doc["completed_step"] = step
    doc["run"] = "idle"
    doc["run_boot_id"] = None
    doc["run_started_at"] = None
    doc["error"] = None
    _append_attempt(doc, step=step, outcome="success", message=None)
    return doc


def _finish_fail(
    doc: dict[str, Any],
    claimed_boot: str,
    exc: BaseException,
    step: str,
) -> dict[str, Any]:
    if doc.get("run_boot_id") != claimed_boot:
        return doc
    message = str(exc)
    doc["run"] = "failed"
    doc["error"] = {"code": "gemini_error", "message": message}
    _append_attempt(doc, step=step, outcome="failed", message=message)
    return doc


def create_app(
    *,
    data_dir: Path | str,
    gemini: Any,
    boot_id: str,
) -> FastAPI:
    storage = Storage(data_dir)
    executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="gemini")

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        executor.shutdown(wait=False, cancel_futures=True)

    app = FastAPI(title="Book Illustration Studio", lifespan=lifespan)

    @app.exception_handler(ApiError)
    async def api_error_handler(_request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(exc.code, exc.message),
        )

    def require_user(
        x_user_email: Annotated[str | None, Header()] = None,
    ) -> str:
        if not x_user_email:
            raise ApiError(401, "unauthenticated", "Missing X-User-Email")
        users = storage.load_users()["users"]
        if x_user_email not in users:
            raise ApiError(401, "unauthenticated", "Unknown email")
        return x_user_email

    def load_owned(project_id: str, email: str) -> dict[str, Any]:
        try:
            doc = storage.load_project(project_id)
        except FileNotFoundError as exc:
            raise ApiError(404, "not_found", "Project not found") from exc
        if doc.get("user_email") != email:
            raise ApiError(403, "forbidden", "Not the owner")
        return doc

    def claim_step(project_id: str, email: str, step: str) -> dict[str, Any]:
        box: dict[str, Any] = {}

        def mutator(doc: dict[str, Any]) -> dict[str, Any]:
            if doc.get("user_email") != email:
                box["error"] = ApiError(403, "forbidden", "Not the owner")
                return doc
            if next_step(doc["completed_step"]) != step:
                box["error"] = ApiError(
                    409,
                    "wrong_step",
                    "That step is not next in the pipeline",
                )
                return doc
            if not can_claim(doc, boot_id):
                box["error"] = ApiError(
                    409,
                    "in_flight",
                    "A step is already running",
                )
                return doc
            doc["run"] = "running"
            doc["run_boot_id"] = boot_id
            doc["run_started_at"] = _now()
            doc["error"] = None
            box["claimed"] = True
            return doc

        try:
            doc = storage.update_project(project_id, mutator)
        except FileNotFoundError as exc:
            raise ApiError(404, "not_found", "Project not found") from exc
        if "error" in box:
            raise box["error"]
        return doc

    def run_worker(
        project_id: str,
        step: str,
        claimed_boot: str,
        user_style: str | None,
    ) -> None:
        try:
            book_text = _read_book(storage, project_id)
            current = storage.load_project(project_id)
            loader = getattr(gemini, "load_session", None)
            if loader is not None:
                loader(current.get("gemini"), style=current.get("style"))

            def persist(doc: dict[str, Any]) -> dict[str, Any]:
                return _persist_gemini_session(doc, gemini)

            if not (current.get("gemini") or {}).get("file_id"):
                gemini.send_book(book_text)
                storage.update_project(project_id, persist)

            if step == "style":
                text = gemini.style(user_style)

                def apply(doc: dict[str, Any]) -> dict[str, Any]:
                    if doc.get("run_boot_id") != claimed_boot:
                        return doc
                    doc["style"] = text
                    doc["style_source"] = "user" if user_style else "generated"
                    persist(doc)
                    return _finish_ok(doc, claimed_boot, "style")

                storage.update_project(project_id, apply)
                return

            if step == "characters":
                raw = gemini.characters()[:MAX_CHARACTERS]
                chars = [
                    {
                        "name": item.get("name", ""),
                        "prompt": item.get("prompt", ""),
                        "portrait_path": None,
                    }
                    for item in raw
                ]

                def apply(doc: dict[str, Any]) -> dict[str, Any]:
                    if doc.get("run_boot_id") != claimed_boot:
                        return doc
                    doc["characters"] = chars
                    persist(doc)
                    return _finish_ok(doc, claimed_boot, "characters")

                storage.update_project(project_id, apply)
                return

            if step == "portraits":
                doc = storage.load_project(project_id)
                characters = list(doc.get("characters") or [])
                images = gemini.portraits(characters)
                portraits_dir = _project_dir(storage, project_id) / "portraits"
                portraits_dir.mkdir(parents=True, exist_ok=True)
                for index, blob in enumerate(images[:MAX_CHARACTERS]):
                    filename = f"{index}.png"
                    (portraits_dir / filename).write_bytes(blob)
                    rel = f"portraits/{filename}"

                    def set_path(
                        current: dict[str, Any],
                        *,
                        i: int = index,
                        relative: str = rel,
                    ) -> dict[str, Any]:
                        if current.get("run_boot_id") != claimed_boot:
                            return current
                        if i < len(current.get("characters") or []):
                            current["characters"][i]["portrait_path"] = relative
                        persist(current)
                        return current

                    storage.update_project(project_id, set_path)

                storage.update_project(
                    project_id,
                    lambda d: persist(_finish_ok(d, claimed_boot, "portraits")),
                )
                return

            if step == "chapters":
                raw = gemini.chapters()[:MAX_CHAPTERS]
                chapters = [
                    {
                        "name": item.get("name", ""),
                        "prompt": item.get("prompt", ""),
                        "illustration_path": None,
                    }
                    for item in raw
                ]

                def apply(doc: dict[str, Any]) -> dict[str, Any]:
                    if doc.get("run_boot_id") != claimed_boot:
                        return doc
                    doc["chapters"] = chapters
                    persist(doc)
                    return _finish_ok(doc, claimed_boot, "chapters")

                storage.update_project(project_id, apply)
                return

            if step == "illustrations":
                doc = storage.load_project(project_id)
                chapters = list(doc.get("chapters") or [])
                portrait_blobs: list[bytes] = []
                for char in doc.get("characters") or []:
                    rel = char.get("portrait_path")
                    if not rel:
                        continue
                    path = _project_dir(storage, project_id) / rel
                    if path.is_file():
                        portrait_blobs.append(path.read_bytes())
                images = gemini.illustrations(chapters, portraits=portrait_blobs)
                ill_dir = _project_dir(storage, project_id) / "illustrations"
                ill_dir.mkdir(parents=True, exist_ok=True)
                for index, blob in enumerate(images[:MAX_CHAPTERS]):
                    filename = f"{index}.png"
                    (ill_dir / filename).write_bytes(blob)
                    rel = f"illustrations/{filename}"

                    def set_path(
                        current: dict[str, Any],
                        *,
                        i: int = index,
                        relative: str = rel,
                    ) -> dict[str, Any]:
                        if current.get("run_boot_id") != claimed_boot:
                            return current
                        if i < len(current.get("chapters") or []):
                            current["chapters"][i]["illustration_path"] = relative
                        persist(current)
                        return current

                    storage.update_project(project_id, set_path)

                storage.update_project(
                    project_id,
                    lambda d: persist(_finish_ok(d, claimed_boot, "illustrations")),
                )
        except Exception as exc:  # noqa: BLE001 — step failure is a user-visible error
            storage.update_project(
                project_id,
                lambda d: _finish_fail(d, claimed_boot, exc, step),
            )

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/identify")
    def identify(body: IdentifyIn) -> dict[str, str]:
        name = body.name.strip()
        email = body.email.strip()
        if not name or not email or "@" not in email:
            raise ApiError(400, "validation", "Enter a name and a valid email")

        def upsert(users: dict[str, Any]) -> dict[str, Any]:
            bucket = users.setdefault("users", {})
            existing = bucket.get(email)
            if existing:
                existing["name"] = name
            else:
                bucket[email] = {"email": email, "name": name, "project_ids": []}
            return users

        storage.update_users(upsert)
        return {"email": email, "name": name}

    @app.get("/api/me")
    def me(email: str = Depends(require_user)) -> dict[str, str]:
        user = storage.load_users()["users"][email]
        return {"email": user["email"], "name": user["name"]}

    @app.get("/api/projects")
    def list_projects(email: str = Depends(require_user)) -> list[dict[str, Any]]:
        user = storage.load_users()["users"][email]
        views: list[dict[str, Any]] = []
        for project_id in user.get("project_ids") or []:
            try:
                doc = storage.load_project(project_id)
            except FileNotFoundError:
                continue
            if doc.get("user_email") != email:
                continue
            views.append(to_view(doc, boot_id))
        return views

    @app.post("/api/projects")
    async def create_project(
        request: Request,
        email: str = Depends(require_user),
    ) -> JSONResponse:
        content_type = request.headers.get("content-type", "")
        if content_type.startswith("multipart/form-data"):
            form = await request.form()
            title = str(form.get("title") or "").strip()
            upload = form.get("file")
            filename = getattr(upload, "filename", None) or ""
            if not filename.lower().endswith(".txt"):
                raise ApiError(400, "validation", "Upload a .txt file")
            raw = await upload.read()
            text = raw.decode("utf-8")
        else:
            payload = await request.json()
            title = str(payload.get("title") or "").strip()
            text = str(payload.get("text") or "")

        text = text.strip()
        if not title or not text:
            raise ApiError(400, "validation", "Give the project a title and book text")

        project_id = str(uuid.uuid4())
        doc = {
            "id": project_id,
            "user_email": email,
            "title": title,
            "created_at": _now(),
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
        storage.save_project(doc)
        _write_book(storage, project_id, text)

        def add_id(users: dict[str, Any]) -> dict[str, Any]:
            ids = users["users"][email].setdefault("project_ids", [])
            ids.insert(0, project_id)
            return users

        storage.update_users(add_id)
        return JSONResponse(
            status_code=201,
            content=_detail_view(doc, boot_id, text),
        )

    @app.get("/api/projects/{project_id}")
    def get_project(
        project_id: str,
        email: str = Depends(require_user),
    ) -> dict[str, Any]:
        doc = load_owned(project_id, email)
        return _detail_view(doc, boot_id, _read_book(storage, project_id))

    @app.post("/api/projects/{project_id}/steps/{step}")
    async def post_step(
        project_id: str,
        step: str,
        request: Request,
        email: str = Depends(require_user),
    ) -> JSONResponse:
        if step not in STEPS:
            raise ApiError(404, "not_found", "Unknown step")

        user_style: str | None = None
        if step == "style":
            try:
                payload = await request.json()
            except Exception:
                payload = {}
            raw_style = (payload or {}).get("style")
            if isinstance(raw_style, str) and raw_style.strip():
                user_style = raw_style.strip()

        claimed = claim_step(project_id, email, step)
        executor.submit(run_worker, project_id, step, boot_id, user_style)
        return JSONResponse(
            status_code=202,
            content=_detail_view(
                claimed,
                boot_id,
                _read_book(storage, project_id),
            ),
        )

    @app.get("/api/projects/{project_id}/files/{kind}/{filename}")
    def get_file(
        project_id: str,
        kind: str,
        filename: str,
        email: str = Depends(require_user),
    ) -> FileResponse:
        load_owned(project_id, email)
        if kind not in {"portraits", "illustrations"}:
            raise ApiError(404, "not_found", "Unknown file")
        if "/" in filename or "\\" in filename or filename.startswith("."):
            raise ApiError(404, "not_found", "Unknown file")
        path = _project_dir(storage, project_id) / kind / filename
        if not path.is_file():
            raise ApiError(404, "not_found", "Unknown file")
        return FileResponse(path)

    return app


app = create_app(
    data_dir=ROOT / "data",
    gemini=default_gemini(),
    boot_id=str(uuid.uuid4()),
)
