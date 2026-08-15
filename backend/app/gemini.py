"""Gemini pipeline client via OpenRouter. Spec: docs/plan.md §7; notebook steps 1–5.

OpenRouter is the provider (OpenAI-compatible chat + Image API). The public
methods stay the same so FastAPI and FakeGeminiClient do not change.
"""

from __future__ import annotations

import base64
import json
import os
import re
import threading
from typing import Any, NoReturn

DEFAULT_TEXT_MODEL = "google/gemini-2.5-flash"
DEFAULT_IMAGE_MODEL = "stabilityai/stable-diffusion-3"
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
MAX_CHARACTERS = 2
MAX_CHAPTERS = 1

SYSTEM_INSTRUCTIONS = """
There must be no text on the image, it should not look like a cover page.
It should be a full illustration with no borders, titles, nor description.
Unless asked otherwise, stay family-friendly with uplifting colors.
Each product should be a simple image, no panels.
"""

PROMPT_ITEM_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "prompt": {"type": "string"},
    },
    "required": ["name", "prompt"],
    "additionalProperties": False,
}

# OpenRouter strict json_schema wants an object, not a top-level array.
PROMPT_OBJECT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "items": {"type": "array", "items": PROMPT_ITEM_SCHEMA},
    },
    "required": ["items"],
    "additionalProperties": False,
}

JSON_SCHEMA_FORMAT: dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "prompt_list",
        "strict": True,
        "schema": PROMPT_OBJECT_SCHEMA,
    },
}


class GeminiError(RuntimeError):
    """A single generation attempt failed. Do not retry automatically."""


class GeminiConfigError(GeminiError):
    """API key missing or rejected."""


class FakeGeminiClient:
    """In-memory client used by HTTP tests. Same public methods as RealGeminiClient."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.book_sends = 0
        self.fail_steps: set[str] = set()
        self.entered = threading.Event()
        self._hold = threading.Event()
        self._hold.set()
        self.file_id: str | None = None
        self.interaction_id: str | None = None

    def load_session(
        self,
        gemini_doc: dict[str, Any] | None = None,
        *,
        style: str | None = None,
    ) -> None:
        del style
        if not gemini_doc:
            return
        self.file_id = gemini_doc.get("file_id") or self.file_id
        self.interaction_id = gemini_doc.get("interaction_id") or self.interaction_id

    def dump_session(self) -> dict[str, Any]:
        return {
            "file_id": self.file_id,
            "interaction_id": self.interaction_id,
        }

    def block(self) -> None:
        self.entered.clear()
        self._hold.clear()

    def unblock(self) -> None:
        self._hold.set()

    def _trace(self, step: str) -> None:
        self.calls.append(step)
        self.entered.set()
        assert self._hold.wait(timeout=5), "fake Gemini held too long"
        if step in self.fail_steps:
            raise RuntimeError(f"fake Gemini failed on {step}")

    def send_book(self, text: str) -> None:
        self.book_sends += 1
        self.book_text = text
        self.file_id = "files/fake-book"
        self.interaction_id = "fake-interaction-book"

    def style(self, user_style: str | None = None) -> str:
        self._trace("style")
        self.interaction_id = "fake-interaction-style"
        return user_style or "Warm, hand-painted watercolour with soft ink outlines."

    def characters(self) -> list[dict]:
        self._trace("characters")
        self.interaction_id = "fake-interaction-characters"
        return [
            {"name": "Mole", "prompt": "A mole in a dark waistcoat, storybook watercolour."},
            {"name": "Rat", "prompt": "A water rat with a straw hat, at the river bank."},
        ]

    def portraits(self, characters: list[dict]) -> list[bytes]:
        self._trace("portraits")
        return [f"png:{c['name']}".encode() for c in characters]

    def chapters(self) -> list[dict]:
        self._trace("chapters")
        self.interaction_id = "fake-interaction-chapters"
        return [
            {
                "name": "Opening Scene",
                "prompt": "Mole and Rat on the river bank, established style.",
            }
        ]

    def illustrations(
        self,
        chapters: list[dict],
        portraits: list[bytes] | None = None,
    ) -> list[bytes]:
        del portraits
        self._trace("illustrations")
        return [f"png:{c['name']}".encode() for c in chapters]


class RealGeminiClient:
    """OpenRouter-backed client. One HTTP attempt per call. Session lives on a
    thread-local so two projects in the pool cannot clobber each other's history.
    """

    def __init__(
        self,
        *,
        api_key: str,
        text_model: str = DEFAULT_TEXT_MODEL,
        image_model: str = DEFAULT_IMAGE_MODEL,
        base_url: str = DEFAULT_BASE_URL,
        http: Any | None = None,
    ) -> None:
        key = (api_key or "").strip()
        if not key:
            raise GeminiConfigError(
                "OPENROUTER_API_KEY is missing. Copy .env.example to .env and set a key "
                "from https://openrouter.ai/keys"
            )
        self.api_key = key
        self.text_model = _normalize_model(text_model, DEFAULT_TEXT_MODEL)
        self.image_model = _normalize_model(image_model, DEFAULT_IMAGE_MODEL)
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self._tls = threading.local()
        if http is not None:
            self._http = http
        else:
            import httpx

            self._http = httpx.Client(timeout=120.0)

    @classmethod
    def from_env(cls) -> RealGeminiClient:
        return cls(
            api_key=os.environ.get("OPENROUTER_API_KEY") or os.environ.get("GEMINI_API_KEY", ""),
            text_model=os.environ.get("GEMINI_TEXT_MODEL") or DEFAULT_TEXT_MODEL,
            image_model=os.environ.get("GEMINI_IMAGE_MODEL") or DEFAULT_IMAGE_MODEL,
            base_url=os.environ.get("OPENROUTER_BASE_URL") or DEFAULT_BASE_URL,
        )

    def load_session(
        self,
        gemini_doc: dict[str, Any] | None = None,
        *,
        style: str | None = None,
    ) -> None:
        data = dict(gemini_doc or {})
        self._tls.file_id = data.get("file_id")
        self._tls.file_uri = data.get("file_uri")
        self._tls.interaction_id = data.get("interaction_id")
        self._tls.image_interaction_id = data.get("image_interaction_id")
        self._tls.text_messages = list(data.get("text_messages") or [])
        self._tls.image_messages = list(data.get("image_messages") or [])
        self._tls.style = style
        self._tls.portraits = []

    def dump_session(self) -> dict[str, Any]:
        return {
            "file_id": getattr(self._tls, "file_id", None),
            "file_uri": getattr(self._tls, "file_uri", None),
            "interaction_id": getattr(self._tls, "interaction_id", None),
            "image_interaction_id": getattr(self._tls, "image_interaction_id", None),
            "text_messages": getattr(self._tls, "text_messages", None),
            "image_messages": getattr(self._tls, "image_messages", None),
        }

    def send_book(self, text: str) -> None:
        self._ensure_session()
        if not (text or "").strip():
            raise GeminiError("Book text is empty; cannot send to OpenRouter.")
        user = (
            "Here's a book, to illustrate using Nano Banana. "
            "Don't say anything for now, instructions will follow.\n\n"
            f"{text.strip()}"
        )
        reply, response_id = self._chat(
            [{"role": "user", "content": user}],
            model=self.text_model,
        )
        self._tls.text_messages = [
            {"role": "user", "content": user},
            {"role": "assistant", "content": reply or "OK"},
        ]
        self._tls.file_id = "openrouter:book"
        self._tls.file_uri = "openrouter:book"
        self._tls.interaction_id = response_id

    def style(self, user_style: str | None = None) -> str:
        self._require_text_session()
        if user_style and user_style.strip():
            chosen = user_style.strip()
            prompt = (
                f'The art style will be:"{chosen}". Keep that in mind when '
                "generating future prompts. Keep quiet for now, instructions will follow."
            )
            reply, response_id = self._chat_next(prompt, max_tokens=1024)
            self._tls.interaction_id = response_id
            self._tls.style = chosen
            return chosen

        prompt = (
            "Can you define an art style that would fit the story but with a twist? "
            "Just give us the prompt for the art style that will be added to future prompts."
        )
        reply, response_id = self._chat_next(prompt, max_tokens=1024)
        self._tls.interaction_id = response_id
        if not reply:
            raise GeminiError("OpenRouter returned an empty art style.")
        self._tls.style = reply
        return reply

    def characters(self) -> list[dict]:
        self._require_text_session()
        prompt = (
            "Can you describe the main characters (only the adults) and prepare a prompt "
            "describing them with as much detail as possible (use the descriptions from "
            "the book) so Nano Banana can generate images of them? Each prompt should be "
            "at least 50 words. Exclude children."
        )
        reply, response_id = self._chat_next(
            prompt,
            response_format=JSON_SCHEMA_FORMAT,
            max_tokens=2048,
        )
        self._tls.interaction_id = response_id
        return _parse_prompt_list(reply, limit=MAX_CHARACTERS)

    def portraits(self, characters: list[dict]) -> list[bytes]:
        self._ensure_session()
        style = getattr(self._tls, "style", None) or ""
        style_line = f'Follow this style: "{style}"' if style else ""
        images: list[bytes] = []
        for character in characters[:MAX_CHARACTERS]:
            name = character.get("name") or "character"
            prompt = character.get("prompt") or ""
            text = (
                f"Create a full portrait illustration of {name}. "
                "No text on the image, no borders, not a cover, not a comic panel. "
                f"{style_line} Also follow: {SYSTEM_INSTRUCTIONS} Description: {prompt}"
            )
            blob, response_id = self._image(text, aspect_ratio="9:16", max_tokens=1024)
            self._tls.image_interaction_id = response_id
            images.append(blob)
        self._tls.portraits = list(images)
        return images

    def chapters(self) -> list[dict]:
        self._require_text_session()
        prompt = (
            "Now, for each chapter of the book, give me a prompt to illustrate what "
            "happens in it. It should be a single image, not a multi-tiled page. Be "
            "very descriptive, especially of the characters. Remember to tell their "
            "name and to reuse the character prompts if they appear in the images. "
            "Also list all characters who appear in it."
        )
        reply, response_id = self._chat_next(
            prompt,
            response_format=JSON_SCHEMA_FORMAT,
            max_tokens=2048,
        )
        self._tls.interaction_id = response_id
        return _parse_prompt_list(reply, limit=MAX_CHAPTERS)

    def illustrations(
        self,
        chapters: list[dict],
        portraits: list[bytes] | None = None,
    ) -> list[bytes]:
        self._ensure_session()
        refs = portraits if portraits is not None else list(getattr(self._tls, "portraits", []) or [])
        style = getattr(self._tls, "style", None) or ""
        style_line = f'Follow this style: "{style}"' if style else ""
        images: list[bytes] = []
        for chapter in chapters[:MAX_CHAPTERS]:
            name = chapter.get("name") or "chapter"
            prompt = chapter.get("prompt") or ""
            text = (
                f"Create an illustration for {name} using the previously generated "
                "characters so they stay visually consistent, but feel free to change "
                "their position. Use the provided images as references of what the "
                "characters look like. No text, no borders, full scene, not a comic "
                f"page. {style_line} Also follow: {SYSTEM_INSTRUCTIONS} "
                f"Description: {prompt}"
            )
            blob, response_id = self._image(text, references=refs, max_tokens=1024)
            self._tls.image_interaction_id = response_id
            images.append(blob)
        return images

    def _ensure_session(self) -> None:
        if not hasattr(self._tls, "text_messages"):
            self.load_session({})

    def _require_text_session(self) -> None:
        self._ensure_session()
        if not getattr(self._tls, "text_messages", None):
            raise GeminiError(
                "No text session. The book must be sent once (send_book) before later steps."
            )

    def _chat_next(
        self,
        prompt: str,
        *,
        response_format: dict[str, Any] | None = None,
        max_tokens: int = 2048,
    ) -> tuple[str, str]:
        history = list(self._tls.text_messages)
        history.append({"role": "user", "content": prompt})
        reply, response_id = self._chat(
            history,
            model=self.text_model,
            response_format=response_format,
            max_tokens=max_tokens,
        )
        history.append({"role": "assistant", "content": reply or ""})
        self._tls.text_messages = history
        return reply, response_id

    def _chat(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str,
        response_format: dict[str, Any] | None = None,
        max_tokens: int = 2048,
    ) -> tuple[str, str]:
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
        }
        if response_format is not None:
            body["response_format"] = response_format
        data = self._request("/chat/completions", body)
        reply = _text_from_chat(data)
        return reply, str(data.get("id") or "openrouter:text")

    def _image(
        self,
        prompt: str,
        *,
        aspect_ratio: str | None = None,
        references: list[bytes] | None = None,
        max_tokens: int = 1024,
    ) -> tuple[bytes, str]:
        body: dict[str, Any] = {
            "model": self.image_model,
            "prompt": prompt,
            "n": 1,
            "output_format": "png",
            "max_tokens": max_tokens,
        }
        if aspect_ratio:
            body["aspect_ratio"] = aspect_ratio
        if references:
            body["input_references"] = [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{base64.b64encode(blob).decode('ascii')}"
                    },
                }
                for blob in references
            ]
        data = self._request("/images", body)
        return image_bytes_from_openrouter(data), str(data.get("id") or "openrouter:image")

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://127.0.0.1:5173",
            "X-Title": "Book Illustration Studio",
        }

    def _request(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            response = self._http.post(url, headers=self._headers(), json=body)
        except Exception as exc:
            _reraise_openrouter(exc)
        status = getattr(response, "status_code", None)
        payload = _response_json(response)
        if status in {401, 403}:
            raise GeminiConfigError(
                "OPENROUTER_API_KEY is missing or invalid. Set it in .env "
                "(https://openrouter.ai/keys)."
            )
        if status is not None and int(status) >= 400:
            raise GeminiError(
                f"OpenRouter request failed (no automatic retry): {_error_message(payload, response)}"
            )
        if not isinstance(payload, dict):
            raise GeminiError("OpenRouter returned a non-JSON body.")
        return payload


def _normalize_model(value: str | None, default: str) -> str:
    raw = (value or "").strip() or default
    if "/" not in raw:
        return f"google/{raw}"
    return raw


def _response_json(response: Any) -> Any:
    parser = getattr(response, "json", None)
    if callable(parser):
        try:
            return parser()
        except Exception:
            return None
    return None


def _error_message(payload: Any, response: Any) -> str:
    if isinstance(payload, dict):
        err = payload.get("error")
        if isinstance(err, dict) and err.get("message"):
            return str(err["message"])
        if isinstance(err, str) and err:
            return err
        if payload.get("message"):
            return str(payload["message"])
    text = getattr(response, "text", None)
    if isinstance(text, str) and text.strip():
        return text.strip()[:500]
    return f"HTTP {getattr(response, 'status_code', '?')}"


def _reraise_openrouter(exc: BaseException) -> NoReturn:
    message = str(exc)
    lowered = message.lower()
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None) or getattr(exc, "status", None)
    invalid_key = (
        status in {401, 403}
        or "api key" in lowered
        or "unauthorized" in lowered
        or "no auth credentials" in lowered
    )
    if invalid_key:
        raise GeminiConfigError(
            "OPENROUTER_API_KEY is missing or invalid. Set it in .env "
            "(https://openrouter.ai/keys)."
        ) from exc
    raise GeminiError(f"OpenRouter request failed (no automatic retry): {exc}") from exc


def _text_from_chat(data: dict[str, Any]) -> str:
    choices = data.get("choices") or []
    if not choices:
        return ""
    message = (choices[0] or {}).get("message") or {}
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        chunks: list[str] = []
        for part in content:
            if isinstance(part, dict) and part.get("type") in {None, "text"}:
                text = part.get("text")
                if isinstance(text, str) and text.strip():
                    chunks.append(text.strip())
        return "\n".join(chunks)
    return ""


def image_bytes_from_openrouter(data: dict[str, Any]) -> bytes:
    rows = data.get("data") or []
    for row in rows:
        if not isinstance(row, dict):
            continue
        blob = _decode_image_field(row.get("b64_json") or row.get("b64"))
        if blob:
            return blob
        url = row.get("url")
        if isinstance(url, str) and url.startswith("data:"):
            blob = _decode_image_field(url)
            if blob:
                return blob
    raise GeminiError("OpenRouter returned no image bytes for this illustration.")


def image_bytes_from_interaction(interaction: Any) -> bytes:
    image = getattr(interaction, "output_image", None)
    blob = _part_to_bytes(image)
    if blob:
        return blob
    steps = getattr(interaction, "steps", None) or []
    for step in reversed(list(steps)):
        if getattr(step, "type", None) != "model_output":
            continue
        for part in reversed(list(getattr(step, "content", None) or [])):
            if getattr(part, "type", None) == "image":
                blob = _part_to_bytes(part)
                if blob:
                    return blob
    raise GeminiError("Gemini returned no image bytes for this illustration.")


def _part_to_bytes(part: Any) -> bytes | None:
    if part is None:
        return None
    data = getattr(part, "data", None)
    if data is None and isinstance(part, dict):
        data = part.get("data")
    return _decode_image_field(data)


def _decode_image_field(data: Any) -> bytes | None:
    if data is None:
        return None
    if isinstance(data, (bytes, bytearray)):
        return bytes(data)
    if isinstance(data, str):
        payload = data.split(",", 1)[-1] if data.startswith("data:") else data
        try:
            return base64.b64decode(payload)
        except Exception as exc:
            raise GeminiError("Image data was not valid base64.") from exc
    return None


def _parse_prompt_list(raw: str, *, limit: int) -> list[dict]:
    if not (raw or "").strip():
        raise GeminiError("OpenRouter returned empty structured output.")
    cleaned = raw.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise GeminiError(f"OpenRouter returned invalid JSON: {exc}") from exc
    if isinstance(parsed, dict):
        for key in ("items", "characters", "chapters"):
            if isinstance(parsed.get(key), list):
                parsed = parsed[key]
                break
    if not isinstance(parsed, list):
        raise GeminiError("OpenRouter JSON was not a list of {name, prompt} objects.")
    items: list[dict] = []
    for entry in parsed[:limit]:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "").strip()
        prompt = str(entry.get("prompt") or "").strip()
        if name and prompt:
            items.append({"name": name, "prompt": prompt})
    if not items:
        raise GeminiError("OpenRouter JSON had no usable name/prompt entries.")
    return items
