"""Unit tests for Gemini helpers. No network."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.gemini import (
    GeminiConfigError,
    GeminiError,
    RealGeminiClient,
    image_bytes_from_interaction,
    image_bytes_from_openrouter,
    _parse_prompt_list,
)


def _http_ok(payload: dict) -> MagicMock:
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = payload
    response.text = json.dumps(payload)
    return response


def _http_err(status: int, message: str) -> MagicMock:
    response = MagicMock()
    response.status_code = status
    response.json.return_value = {"error": {"message": message}}
    response.text = message
    return response


def test_from_env_missing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(GeminiConfigError, match="OPENROUTER_API_KEY"):
        RealGeminiClient.from_env()


def test_invalid_key_is_config_error() -> None:
    http = MagicMock()
    http.post.return_value = _http_err(401, "Unauthorized")
    real = RealGeminiClient(api_key="bad", http=http)
    real.load_session({"text_messages": [{"role": "user", "content": "book"}]})
    with pytest.raises(GeminiConfigError, match="invalid"):
        real.style(None)


def test_image_bytes_from_output_image() -> None:
    import base64

    raw = b"png-bytes"
    interaction = SimpleNamespace(
        output_image=SimpleNamespace(data=base64.b64encode(raw).decode(), type="image"),
        steps=[],
    )
    assert image_bytes_from_interaction(interaction) == raw


def test_image_bytes_from_steps_when_output_image_missing() -> None:
    import base64

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


def test_send_book_posts_chat_once() -> None:
    http = MagicMock()
    http.post.return_value = _http_ok(
        {
            "id": "gen-book",
            "choices": [{"message": {"role": "assistant", "content": "ok"}}],
        }
    )
    real = RealGeminiClient(api_key="k", http=http)
    real.load_session({})
    real.send_book("Once upon a time")

    http.post.assert_called_once()
    url, kwargs = http.post.call_args.args[0], http.post.call_args.kwargs
    assert url.endswith("/chat/completions")
    assert kwargs["json"]["model"] == "google/gemini-2.5-flash"
    assert kwargs["json"]["max_tokens"] == 2048
    assert "Once upon a time" in kwargs["json"]["messages"][0]["content"]
    dumped = real.dump_session()
    assert dumped["file_id"] == "openrouter:book"
    assert dumped["interaction_id"] == "gen-book"
    assert len(dumped["text_messages"]) == 2


def test_characters_uses_json_schema_and_slices() -> None:
    raw = json.dumps(
        {
            "items": [
                {"name": "Mole", "prompt": "A mole in a waistcoat."},
                {"name": "Rat", "prompt": "A water rat."},
                {"name": "Toad", "prompt": "A toad in a motorcar."},
            ]
        }
    )
    http = MagicMock()
    http.post.return_value = _http_ok(
        {"id": "gen-chars", "choices": [{"message": {"content": raw}}]}
    )
    real = RealGeminiClient(api_key="k", http=http)
    real.load_session(
        {
            "file_id": "openrouter:book",
            "text_messages": [{"role": "user", "content": "book"}],
        }
    )
    items = real.characters()
    assert [i["name"] for i in items] == ["Mole", "Rat"]
    body = http.post.call_args.kwargs["json"]
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["schema"]["type"] == "object"
    assert body["max_tokens"] == 2048
    http.post.assert_called_once()


def test_portraits_and_illustrations_use_image_api_and_pass_refs() -> None:
    import base64

    portrait = b"portrait-png"
    chapter = b"chapter-png"
    http = MagicMock()
    http.post.side_effect = [
        _http_ok({"id": "img-1", "data": [{"b64_json": base64.b64encode(portrait).decode()}]}),
        _http_ok({"id": "img-2", "data": [{"b64_json": base64.b64encode(chapter).decode()}]}),
    ]
    real = RealGeminiClient(api_key="k", http=http)
    real.load_session({"file_id": "openrouter:book"}, style="ink")
    blobs = real.portraits([{"name": "Mole", "prompt": "A mole."}])
    assert blobs == [portrait]
    ill = real.illustrations(
        [{"name": "Opening", "prompt": "River bank."}],
        portraits=blobs,
    )
    assert ill == [chapter]
    first = http.post.call_args_list[0]
    second = http.post.call_args_list[1]
    assert first.args[0].endswith("/images")
    assert first.kwargs["json"]["model"] == "stabilityai/stable-diffusion-3"
    assert first.kwargs["json"]["aspect_ratio"] == "9:16"
    assert first.kwargs["json"]["max_tokens"] == 1024
    assert second.kwargs["json"]["max_tokens"] == 1024
    refs = second.kwargs["json"]["input_references"]
    assert len(refs) == 1
    assert base64.b64decode(refs[0]["image_url"]["url"].split(",", 1)[1]) == portrait
    assert real.dump_session()["image_interaction_id"] == "img-2"
    assert http.post.call_count == 2


def test_image_bytes_from_openrouter_payload() -> None:
    import base64

    raw = b"png-from-api"
    assert image_bytes_from_openrouter(
        {"data": [{"b64_json": base64.b64encode(raw).decode()}]}
    ) == raw


def test_bare_model_id_gets_google_prefix() -> None:
    real = RealGeminiClient(
        api_key="k",
        text_model="gemini-3.7-flash",
        image_model="gemini-2.5-flash-image",
        http=MagicMock(),
    )
    assert real.text_model == "google/gemini-3.7-flash"
    assert real.image_model == "google/gemini-2.5-flash-image"
