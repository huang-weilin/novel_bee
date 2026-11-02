import io
import json
import urllib.error
from unittest.mock import patch

import pytest

from novel_pipeline.config import LLMConfig
from novel_pipeline.llm import (
    DEFAULT_LLM_MAX_TOKENS,
    LLMClient,
    LLMError,
)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def anthropic_config() -> LLMConfig:
    return LLMConfig(
        provider="anthropic-compatible",
        model="test-model",
        base_url="https://example.test/anthropic",
        api_key_env=None,
        api_key="secret-key",
        timeout_seconds=5,
    )


def openai_config() -> LLMConfig:
    return LLMConfig(
        provider="openai-compatible",
        model="test-model",
        base_url="https://example.test/v1",
        api_key_env=None,
        api_key="secret-key",
        timeout_seconds=5,
    )


def test_default_generation_budget_leaves_room_for_thinking() -> None:
    # A thinking model can spend a small cap entirely on reasoning blocks and
    # return no text; the structured/revision calls share this default.
    assert DEFAULT_LLM_MAX_TOKENS >= 16_384


def test_anthropic_request_shape() -> None:
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = {
            key.lower(): value for key, value in request.header_items()
        }
        captured["body"] = json.loads(request.data)
        return FakeResponse({"content": [{"type": "text", "text": "ok"}]})

    with patch("novel_pipeline.llm.urllib.request.urlopen", fake_urlopen):
        text = LLMClient(anthropic_config()).complete(
            "hello", system="system", temperature=0.2, max_tokens=10
        )

    assert text == "ok"
    assert captured["url"] == "https://example.test/anthropic/v1/messages"
    assert captured["headers"]["x-api-key"] == "secret-key"
    assert captured["body"]["system"] == "system"
    assert captured["body"]["messages"][0]["content"] == "hello"
    assert captured["body"]["max_tokens"] == 10


def test_openai_request_shape() -> None:
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = {
            key.lower(): value for key, value in request.header_items()
        }
        captured["body"] = json.loads(request.data)
        return FakeResponse({"choices": [{"message": {"content": "ok"}}]})

    with patch("novel_pipeline.llm.urllib.request.urlopen", fake_urlopen):
        text = LLMClient(openai_config()).complete("hello", system="system")

    assert text == "ok"
    assert captured["url"] == "https://example.test/v1/chat/completions"
    assert captured["headers"]["authorization"] == "Bearer secret-key"
    assert captured["body"]["messages"][0] == {
        "role": "system",
        "content": "system",
    }


def test_http_error_is_wrapped() -> None:
    def fake_urlopen(request, timeout):
        raise urllib.error.HTTPError(
            request.full_url,
            401,
            "Unauthorized",
            {},
            io.BytesIO(b'{"error":"bad key"}'),
        )

    with patch(
        "novel_pipeline.llm.urllib.request.urlopen", fake_urlopen
    ), pytest.raises(LLMError, match="401"):
        LLMClient(anthropic_config()).complete("hello")


def test_read_timeout_is_wrapped() -> None:
    def fake_urlopen(request, timeout):
        raise TimeoutError("read timed out")

    with patch(
        "novel_pipeline.llm.urllib.request.urlopen", fake_urlopen
    ), pytest.raises(LLMError, match="timed out"):
        LLMClient(anthropic_config()).complete("hello")


def test_empty_response_is_rejected() -> None:
    with patch(
        "novel_pipeline.llm.urllib.request.urlopen",
        lambda request, timeout: FakeResponse({"content": []}),
    ), pytest.raises(LLMError):
        LLMClient(anthropic_config()).complete("hello")


def test_thinking_only_response_is_rejected() -> None:
    with patch(
        "novel_pipeline.llm.urllib.request.urlopen",
        lambda request, timeout: FakeResponse(
            {"content": [{"type": "thinking", "thinking": "reasoning"}]}
        ),
    ), pytest.raises(LLMError, match="thinking"):
        LLMClient(anthropic_config()).complete("hello")


def test_thinking_only_response_retries_with_larger_budget() -> None:
    bodies = []
    responses = [
        {"content": [{"type": "thinking", "thinking": "reasoning"}]},
        {"content": [{"type": "text", "text": "ok"}]},
    ]

    def fake_urlopen(request, timeout):
        bodies.append(json.loads(request.data))
        return FakeResponse(responses.pop(0))

    with patch("novel_pipeline.llm.urllib.request.urlopen", fake_urlopen):
        text = LLMClient(anthropic_config()).complete(
            "hello", max_tokens=16_384
        )

    assert text == "ok"
    assert [body["max_tokens"] for body in bodies] == [16_384, 32_768]


def test_config_repr_hides_key() -> None:
    assert "secret-key" not in repr(anthropic_config())
