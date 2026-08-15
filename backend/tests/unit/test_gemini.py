"""Unit tests for Gemini helpers. No network."""

from __future__ import annotations

import base64
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.gemini import (
    CHARACTERS_PROMPT,
    DEFAULT_IMAGE_MODEL,
    DEFAULT_TEXT_MODEL,
    FAKE_PNG,
    FakeGeminiClient,
    GeminiConfigError,
    GeminiError,
    PROMPT_LIST_FORMAT,
    RealGeminiClient,
    image_bytes_from_interaction,
    _parse_prompt_list,
)


def _text_interaction(interaction_id: str, text: str) -> SimpleNamespace:
    return SimpleNamespace(id=interaction_id, output_text=text, steps=[], output_image=None)


def _image_interaction(interaction_id: str, raw: bytes) -> SimpleNamespace:
    part = SimpleNamespace(
        type="image",
        data=base64.b64encode(raw).decode(),
        mime_type="image/png",
    )
    step = SimpleNamespace(type="model_output", content=[part])
    return SimpleNamespace(
        id=interaction_id,
        output_text="",
        output_image=part,
        steps=[step],
    )


def test_fake_portraits_are_png() -> None:
    fake = FakeGeminiClient()
    blobs = fake.portraits([{"name": "Mole", "prompt": "A mole."}])
    assert blobs == [FAKE_PNG]
    assert FAKE_PNG[:8] == b"\x89PNG\r\n\x1a\n"


def test_from_env_missing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(GeminiConfigError, match="GEMINI_API_KEY"):
        RealGeminiClient.from_env()


def test_invalid_key_is_config_error() -> None:
    sdk = MagicMock()

    class AuthErr(Exception):
        status_code = 401

    sdk.interactions.create.side_effect = AuthErr("Unauthorized")
    real = RealGeminiClient(api_key="bad", sdk=sdk)
    real.load_session({"file_id": "files/book", "interaction_id": "int-book"})
    with pytest.raises(GeminiConfigError, match="invalid"):
        real.style(None)


def test_image_bytes_from_output_image() -> None:
    raw = b"png-bytes"
    interaction = SimpleNamespace(
        output_image=SimpleNamespace(data=base64.b64encode(raw).decode(), type="image"),
        steps=[],
    )
    assert image_bytes_from_interaction(interaction) == raw


def test_image_bytes_from_steps_when_output_image_missing() -> None:
    raw = b"from-step"
    part = SimpleNamespace(type="image", data=base64.b64encode(raw).decode())
    step = SimpleNamespace(type="model_output", content=[part])
    interaction = SimpleNamespace(output_image=None, steps=[step])
    assert image_bytes_from_interaction(interaction) == raw


def test_image_bytes_missing_raises() -> None:
    interaction = SimpleNamespace(output_image=None, steps=[])
    with pytest.raises(GeminiError, match="no image"):
        image_bytes_from_interaction(interaction)


def test_parse_prompt_list_slices_and_unwraps_fence() -> None:
    raw = """```json
    [{"name": "A", "prompt": "one"}, {"name": "B", "prompt": "two"}, {"name": "C", "prompt": "three"}]
    ```"""
    items = _parse_prompt_list(raw, limit=2)
    assert [i["name"] for i in items] == ["A", "B"]


def test_send_book_uploads_file_and_starts_interaction() -> None:
    uploaded = SimpleNamespace(name="files/book-1", uri="https://files/book-1")
    sdk = MagicMock()
    sdk.files.upload.return_value = uploaded
    sdk.interactions.create.return_value = _text_interaction("int-book", "ok")
    real = RealGeminiClient(api_key="k", sdk=sdk)
    real.load_session({})
    real.send_book("Once upon a time")

    sdk.files.upload.assert_called_once()
    path = sdk.files.upload.call_args.kwargs["file"]
    assert path.endswith(".txt")
    sdk.interactions.create.assert_called_once()
    body = sdk.interactions.create.call_args.kwargs
    assert body["model"] == DEFAULT_TEXT_MODEL
    assert body["input"][0]["type"] == "text"
    assert "Don't say anything for now" in body["input"][0]["text"]
    assert body["input"][1] == {"type": "document", "uri": uploaded.uri}
    assert "previous_interaction_id" not in body
    dumped = real.dump_session()
    assert dumped["file_id"] == "files/book-1"
    assert dumped["file_uri"] == uploaded.uri
    assert dumped["interaction_id"] == "int-book"


def test_characters_uses_array_schema_and_slices() -> None:
    raw = json.dumps(
        [
            {"name": "Mole", "prompt": "A mole in a waistcoat."},
            {"name": "Rat", "prompt": "A water rat."},
            {"name": "Toad", "prompt": "A toad in a motorcar."},
        ]
    )
    sdk = MagicMock()
    sdk.interactions.create.return_value = _text_interaction("int-chars", raw)
    real = RealGeminiClient(api_key="k", sdk=sdk)
    real.load_session({"file_id": "files/book", "interaction_id": "int-style"})
    items = real.characters()
    assert [i["name"] for i in items] == ["Mole", "Rat"]
    body = sdk.interactions.create.call_args.kwargs
    assert body["model"] == DEFAULT_TEXT_MODEL
    assert body["previous_interaction_id"] == "int-style"
    assert body["input"] == CHARACTERS_PROMPT
    assert "only the adults" in body["input"]
    assert body["response_format"] == PROMPT_LIST_FORMAT
    assert body["response_format"]["schema"]["type"] == "array"
    sdk.interactions.create.assert_called_once()


def test_portraits_and_illustrations_chain_image_session_and_pass_refs() -> None:
    portrait = b"portrait-png"
    chapter = b"chapter-png"
    sdk = MagicMock()
    sdk.interactions.create.side_effect = [
        _text_interaction("img-ctx", "ok"),
        _image_interaction("img-1", portrait),
        _text_interaction("img-ch-ctx", "ok"),
        _image_interaction("img-2", chapter),
    ]
    real = RealGeminiClient(api_key="k", sdk=sdk)
    real.load_session({"file_id": "files/book", "interaction_id": "int-chars"}, style="ink")
    blobs = real.portraits([{"name": "Mole", "prompt": "A mole."}])
    assert blobs == [portrait]
    ill = real.illustrations(
        [{"name": "Opening", "prompt": "River bank."}],
        portraits=blobs,
    )
    assert ill == [chapter]
    assert sdk.interactions.create.call_count == 4
    setup, portrait_call, chapter_setup, chapter_call = [
        call.kwargs for call in sdk.interactions.create.call_args_list
    ]
    assert setup["model"] == DEFAULT_IMAGE_MODEL
    assert "previous_interaction_id" not in setup
    assert "no text on the image" in setup["input"]
    assert portrait_call["previous_interaction_id"] == "img-ctx"
    assert "Create an illustration for Mole" in portrait_call["input"]
    assert chapter_setup["previous_interaction_id"] == "img-1"
    assert "illustrate the book's chapters" in chapter_setup["input"]
    assert chapter_call["previous_interaction_id"] == "img-ch-ctx"
    parts = chapter_call["input"]
    assert isinstance(parts, list)
    assert parts[0]["type"] == "text"
    assert "Opening" in parts[0]["text"]
    assert parts[1]["type"] == "image"
    assert base64.b64decode(parts[1]["data"]) == portrait
    assert real.dump_session()["image_interaction_id"] == "img-2"


def test_google_prefix_is_stripped_from_model_ids() -> None:
    real = RealGeminiClient(
        api_key="k",
        text_model="google/gemini-3.7-flash",
        image_model="google/gemini-2.5-flash-image",
        sdk=MagicMock(),
    )
    assert real.text_model == "gemini-3.7-flash"
    assert real.image_model == "gemini-2.5-flash-image"
