"""Gemini clients (real SDK + test fake). Spec: docs/plan.md §7.

Pipeline is the cookbook notebook steps 1–5 only:
https://github.com/google-gemini/cookbook/blob/main/examples/Book_illustration.ipynb

Uses ``google-genai`` (``from google import genai``): ``files.upload`` plus
``interactions.create`` with ``previous_interaction_id``. Caps (max 2
characters, max 1 chapter) are assignment limits, not the notebook's.
"""

from __future__ import annotations

import base64
import json
import os
import re
import tempfile
import threading
from typing import Any, NoReturn

from pydantic import BaseModel

# Notebook defaults (Select models cell). Override with GEMINI_*_MODEL.
DEFAULT_TEXT_MODEL = "gemini-3.7-flash"
DEFAULT_IMAGE_MODEL = "gemini-3.1-flash-lite-image"
MAX_CHARACTERS = 2
MAX_CHAPTERS = 1

# 1×1 PNG so FakeGemini portraits/illustrations are displayable in <img>.
FAKE_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d4944415478da63fccfc0500f000485018084a98c210000000049454e44ae426082"
)

# Notebook ``system_instructions`` cell — used on the image chain, not as SDK system_instruction.
SYSTEM_INSTRUCTIONS = """
 There must be no text on the image, it should not look like a cover page.
 It should be an full illustration with no borders, titles, nor description.
 Unless asked otherwise, stay family-friendly with uplifting colors.
 Each produced should be a simple image, no panels.
"""

BOOK_INTRO = (
    "Here's a book, to illustrate using Nano Banana. "
    "Don't say anything for now, instructions will follow."
)

STYLE_GENERATE_PROMPT = (
    "Can you define a art style that would fit the story but with a twist? "
    "Just give us the prompt for the art syle that will added to the furture prompts."
)

CHARACTERS_PROMPT = (
    "Can you describe the main characters (only the adults) and prepare a prompt "
    "describing them with as much details as possible (use the descriptions from "
    "the book) so Nano Banana can generate images of them? Each prompt should be "
    "at least 50 words."
)

CHAPTERS_PROMPT = (
    "Now, for each chapters of the book, give me a prompt to illustrate what "
    "happens in it. It should be a single image, not a multi-tiled page. Be "
    "very descriptive, especially of the characters. Be very descriptive and "
    "remember to tell their name and to reuse the character prompts if they "
    "appear in the images. Also list all characters who appear in it."
)

PORTRAIT_SETUP_PROMPT = """
 You are going to generate portrait images to illustrate this book.
 The style we want you to follow is: {style}
 Also follow those rules: {system_instructions}
 """

CHAPTER_SETUP_PROMPT = (
    "Starting from now, we're going to illustrate the book's chapters. Don't "
    "forget to refer to your previous illustrations of the characters to keep "
    "the characters consistency, but feel free to change their position."
)


class Prompt(BaseModel):
    """Notebook structured-output row: name + image prompt."""

    name: str
    prompt: str


PROMPT_LIST_FORMAT: dict[str, Any] = {
    "type": "text",
    "mime_type": "application/json",
    "schema": {"type": "array", "items": Prompt.model_json_schema()},
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
        return [FAKE_PNG for _ in characters]

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
        return [FAKE_PNG for _ in chapters]


class RealGeminiClient:
    """Notebook pipeline via google-genai Files + Interactions.

    Session IDs live on a thread-local so two projects in the pool cannot
    clobber each other. One ``interactions.create`` per call — no SDK retry loop.
    """

    def __init__(
        self,
        *,
        api_key: str,
        text_model: str = DEFAULT_TEXT_MODEL,
        image_model: str = DEFAULT_IMAGE_MODEL,
        sdk: Any | None = None,
    ) -> None:
        key = (api_key or "").strip()
        if not key:
            raise GeminiConfigError(
                "GEMINI_API_KEY is missing. Copy .env.example to .env and set a key "
                "from https://aistudio.google.com/apikey"
            )
        self.api_key = key
        self.text_model = _normalize_model(text_model, DEFAULT_TEXT_MODEL)
        self.image_model = _normalize_model(image_model, DEFAULT_IMAGE_MODEL)
        self._tls = threading.local()
        if sdk is not None:
            self._sdk = sdk
        else:
            from google import genai

            # Notebook enables HttpRetryOptions(attempts=5). Plan forbids auto-retry.
            self._sdk = genai.Client(api_key=key)

    @classmethod
    def from_env(cls) -> RealGeminiClient:
        return cls(
            api_key=os.environ.get("GEMINI_API_KEY", ""),
            text_model=os.environ.get("GEMINI_TEXT_MODEL") or DEFAULT_TEXT_MODEL,
            image_model=os.environ.get("GEMINI_IMAGE_MODEL") or DEFAULT_IMAGE_MODEL,
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
        self._tls.style = style
        self._tls.portraits: list[bytes] = []

    def dump_session(self) -> dict[str, Any]:
        return {
            "file_id": getattr(self._tls, "file_id", None),
            "file_uri": getattr(self._tls, "file_uri", None),
            "interaction_id": getattr(self._tls, "interaction_id", None),
            "image_interaction_id": getattr(self._tls, "image_interaction_id", None),
        }

    def send_book(self, text: str) -> None:
        self._ensure_session()
        body = (text or "").strip()
        if not body:
            raise GeminiError("Book text is empty; cannot send to Gemini.")
        uploaded = self._upload_book(body)
        self._tls.file_id = getattr(uploaded, "name", None) or getattr(uploaded, "id", None)
        self._tls.file_uri = getattr(uploaded, "uri", None)
        if not self._tls.file_uri:
            raise GeminiError("Gemini file upload returned no URI.")
        interaction = self._interact(
            model=self.text_model,
            input=[
                {"type": "text", "text": BOOK_INTRO},
                {"type": "document", "uri": self._tls.file_uri},
            ],
        )
        self._tls.interaction_id = interaction.id

    def style(self, user_style: str | None = None) -> str:
        previous = self._require_text_session()
        if user_style and user_style.strip():
            chosen = user_style.strip()
            prompt = (
                f'The art style will be:"{chosen}". Keep that in mind when '
                "generating future prompts. Keep quiet for now, instructions will follow."
            )
            interaction = self._interact(
                model=self.text_model,
                input=prompt,
                previous_interaction_id=previous,
            )
            self._tls.interaction_id = interaction.id
            self._tls.style = chosen
            return chosen

        interaction = self._interact(
            model=self.text_model,
            input=STYLE_GENERATE_PROMPT,
            previous_interaction_id=previous,
        )
        self._tls.interaction_id = interaction.id
        reply = _interaction_text(interaction)
        if not reply:
            raise GeminiError("Gemini returned an empty art style.")
        self._tls.style = reply
        return reply

    def characters(self) -> list[dict]:
        previous = self._require_text_session()
        interaction = self._interact(
            model=self.text_model,
            input=CHARACTERS_PROMPT,
            previous_interaction_id=previous,
            response_format=PROMPT_LIST_FORMAT,
        )
        self._tls.interaction_id = interaction.id
        return _parse_prompt_list(_interaction_text(interaction), limit=MAX_CHARACTERS)

    def portraits(self, characters: list[dict]) -> list[bytes]:
        self._ensure_session()
        style = getattr(self._tls, "style", None) or ""
        styled = f'Follow this style: "{style}" ' if style else style
        setup = self._interact(
            model=self.image_model,
            input=PORTRAIT_SETUP_PROMPT.format(
                style=styled,
                system_instructions=SYSTEM_INSTRUCTIONS,
            ),
        )
        self._tls.image_interaction_id = setup.id
        images: list[bytes] = []
        for character in characters[:MAX_CHARACTERS]:
            name = character.get("name") or "character"
            prompt = character.get("prompt") or ""
            interaction = self._interact(
                model=self.image_model,
                input=(
                    f"Create an illustration for {name} following this description: {prompt}"
                ),
                previous_interaction_id=self._tls.image_interaction_id,
            )
            self._tls.image_interaction_id = interaction.id
            images.append(image_bytes_from_interaction(interaction))
        self._tls.portraits = list(images)
        return images

    def chapters(self) -> list[dict]:
        previous = self._require_text_session()
        interaction = self._interact(
            model=self.text_model,
            input=CHAPTERS_PROMPT,
            previous_interaction_id=previous,
            response_format=PROMPT_LIST_FORMAT,
        )
        self._tls.interaction_id = interaction.id
        return _parse_prompt_list(_interaction_text(interaction), limit=MAX_CHAPTERS)

    def illustrations(
        self,
        chapters: list[dict],
        portraits: list[bytes] | None = None,
    ) -> list[bytes]:
        self._ensure_session()
        refs = portraits if portraits is not None else list(getattr(self._tls, "portraits", []) or [])
        previous = getattr(self._tls, "image_interaction_id", None)
        setup = self._interact(
            model=self.image_model,
            input=CHAPTER_SETUP_PROMPT,
            previous_interaction_id=previous,
        )
        self._tls.image_interaction_id = setup.id
        images: list[bytes] = []
        for chapter in chapters[:MAX_CHAPTERS]:
            name = chapter.get("name") or "chapter"
            prompt = chapter.get("prompt") or ""
            text = (
                f"Create an illustration for {name} using the previously generated "
                f"characters following this description: {prompt}"
            )
            interaction = self._interact(
                model=self.image_model,
                input=_illustration_input(text, refs),
                previous_interaction_id=self._tls.image_interaction_id,
            )
            self._tls.image_interaction_id = interaction.id
            images.append(image_bytes_from_interaction(interaction))
        return images

    def _ensure_session(self) -> None:
        if not hasattr(self._tls, "file_id"):
            self.load_session({})

    def _require_text_session(self) -> str:
        self._ensure_session()
        previous = getattr(self._tls, "interaction_id", None)
        if not previous:
            raise GeminiError(
                "No text session. The book must be sent once (send_book) before later steps."
            )
        return previous

    def _upload_book(self, text: str) -> Any:
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".txt",
                delete=False,
                encoding="utf-8",
            ) as tmp:
                tmp.write(text)
                tmp_path = tmp.name
            try:
                return self._sdk.files.upload(file=tmp_path)
            except Exception as exc:
                _reraise_gemini(exc)
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    def _interact(
        self,
        *,
        model: str,
        input: Any,
        previous_interaction_id: str | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> Any:
        kwargs: dict[str, Any] = {"model": model, "input": input}
        if previous_interaction_id:
            kwargs["previous_interaction_id"] = previous_interaction_id
        if response_format is not None:
            kwargs["response_format"] = response_format
        try:
            interaction = self._sdk.interactions.create(**kwargs)
        except Exception as exc:
            _reraise_gemini(exc)
        if interaction is None or not getattr(interaction, "id", None):
            raise GeminiError("Gemini returned no interaction id.")
        return interaction


def _illustration_input(text: str, portraits: list[bytes]) -> Any:
    if not portraits:
        return text
    parts: list[dict[str, Any]] = [{"type": "text", "text": text}]
    for blob in portraits:
        parts.append(
            {
                "type": "image",
                "data": base64.b64encode(blob).decode("ascii"),
                "mime_type": "image/png",
            }
        )
    return parts


def _normalize_model(value: str | None, default: str) -> str:
    raw = (value or "").strip() or default
    if raw.startswith("google/"):
        raw = raw[len("google/") :]
    return raw


def _interaction_text(interaction: Any) -> str:
    text = getattr(interaction, "output_text", None)
    if isinstance(text, str) and text.strip():
        return text.strip()
    steps = getattr(interaction, "steps", None) or []
    for step in reversed(list(steps)):
        for part in reversed(list(getattr(step, "content", None) or [])):
            chunk = getattr(part, "text", None)
            if chunk is None and isinstance(part, dict):
                chunk = part.get("text")
            if isinstance(chunk, str) and chunk.strip():
                return chunk.strip()
    return ""


def _reraise_gemini(exc: BaseException) -> NoReturn:
    message = str(exc)
    lowered = message.lower()
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None) or getattr(exc, "status", None)
    invalid_key = (
        status in {401, 403}
        or "api key" in lowered
        or "unauthorized" in lowered
        or "no auth credentials" in lowered
        or "invalid api key" in lowered
        or "api_key_invalid" in lowered
    )
    if invalid_key:
        raise GeminiConfigError(
            "GEMINI_API_KEY is missing or invalid. Set it in .env "
            "(https://aistudio.google.com/apikey)."
        ) from exc
    raise GeminiError(f"Gemini request failed (no automatic retry): {exc}") from exc


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
        raise GeminiError("Gemini returned empty structured output.")
    cleaned = raw.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise GeminiError(f"Gemini returned invalid JSON: {exc}") from exc
    if isinstance(parsed, dict):
        for key in ("items", "characters", "chapters"):
            if isinstance(parsed.get(key), list):
                parsed = parsed[key]
                break
    if not isinstance(parsed, list):
        raise GeminiError("Gemini JSON was not a list of {name, prompt} objects.")
    items: list[dict] = []
    for entry in parsed[:limit]:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "").strip()
        prompt = str(entry.get("prompt") or "").strip()
        if name and prompt:
            items.append({"name": name, "prompt": prompt})
    if not items:
        raise GeminiError("Gemini JSON had no usable name/prompt entries.")
    return items
