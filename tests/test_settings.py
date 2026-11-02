from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import novel_pipeline.server.settings as settings_module
from novel_pipeline.llm import LLMError
from novel_pipeline.server.app import create_app
from novel_pipeline.server.settings import (
    SettingsError,
    read_settings,
    save_settings,
)

_ENV_KEYS = (
    "NOVEL_LLM_PROVIDER",
    "NOVEL_LLM_MODEL",
    "NOVEL_LLM_BASE_URL",
    "NOVEL_LLM_API_KEY",
    "NOVEL_LLM_API_KEY_ENV",
    "DEEPSEEK_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
)


@pytest.fixture(autouse=True)
def _isolate_llm_environment():
    """Keep real keys and the repository's .env out of these tests."""
    saved = {key: os.environ.get(key) for key in _ENV_KEYS}
    for key in _ENV_KEYS:
        os.environ.pop(key, None)
    yield
    for key, value in saved.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


@pytest.fixture
def client(tmp_path: Path):
    app = create_app(
        data_path=tmp_path / "novel.db",
        require_llm=False,
        env_path=tmp_path / ".env",
    )
    with TestClient(app) as test_client:
        yield test_client


def _write_env(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def test_save_settings_keeps_comments_and_hides_key(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    _write_env(
        path,
        "# keep this comment\n"
        "OTHER_SETTING=1\n"
        "NOVEL_LLM_PROVIDER=deepseek\n"
        "NOVEL_LLM_PROVIDER=openai\n",
    )
    secret = "sk-test-secret-123456"

    result = save_settings(
        path,
        provider="deepseek",
        model="deepseek-chat",
        base_url="",
        api_key=secret,
        environ={},
    )

    text = path.read_text(encoding="utf-8")
    assert "# keep this comment" in text
    assert "OTHER_SETTING=1" in text
    assert text.count("NOVEL_LLM_PROVIDER=") == 1
    assert f"NOVEL_LLM_API_KEY={secret}" in text
    assert result["key_configured"] is True
    assert result["provider"] == "deepseek"
    assert result["model"] == "deepseek-chat"
    assert secret not in json.dumps(result)


def test_blank_key_keeps_the_saved_key(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    _write_env(
        path,
        "NOVEL_LLM_PROVIDER=deepseek\n"
        "NOVEL_LLM_MODEL=deepseek-chat\n"
        "NOVEL_LLM_API_KEY=sk-old-key-123456\n",
    )

    result = save_settings(
        path,
        provider="deepseek",
        model="deepseek-chat",
        base_url="",
        api_key="",
        environ={},
    )

    assert "NOVEL_LLM_API_KEY=sk-old-key-123456" in path.read_text(
        encoding="utf-8"
    )
    assert result["key_configured"] is True


def test_switching_provider_requires_a_new_key(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    _write_env(
        path,
        "NOVEL_LLM_PROVIDER=deepseek\n"
        "NOVEL_LLM_API_KEY=sk-old-key-123456\n",
    )

    with pytest.raises(SettingsError, match="更换 AI 服务商"):
        save_settings(
            path,
            provider="openai",
            model="gpt-4o-mini",
            base_url="",
            api_key="",
            environ={},
        )


def test_settings_endpoints_round_trip(client: TestClient) -> None:
    initial = client.get("/api/settings")
    assert initial.status_code == 200
    payload = initial.json()
    assert payload["key_configured"] is False
    assert len(payload["providers"]) == 6
    assert "api_key" not in payload
    assert payload["env_path"].endswith(".env")
    assert payload["data_path"].endswith("novel.db")

    secret = "sk-live-secret-987654"
    saved = client.post(
        "/api/settings",
        json={
            "provider": "deepseek",
            "model": "deepseek-chat",
            "base_url": "https://api.deepseek.com",
            "api_key": secret,
        },
    )
    assert saved.status_code == 200, saved.text
    assert secret not in saved.text
    assert saved.json()["key_configured"] is True

    health = client.get("/api/health").json()
    assert health["llm"]["configured"] is True
    assert health["llm"]["provider"] == "deepseek"
    assert health["llm"]["model"] == "deepseek-chat"

    again = client.post(
        "/api/settings",
        json={
            "provider": "deepseek",
            "model": "deepseek-chat",
            "base_url": "",
            "api_key": "",
        },
    )
    assert again.status_code == 200, again.text
    assert secret not in again.text
    assert again.json()["key_configured"] is True


def test_settings_reject_bad_values_without_echoing_key(
    client: TestClient,
) -> None:
    cases = (
        (
            {
                "provider": "unknown",
                "model": "x",
                "base_url": "",
                "api_key": "sk-value-123456",
            },
            "未知",
        ),
        (
            {
                "provider": "openai-compatible",
                "model": "x",
                "base_url": "",
                "api_key": "sk-value-123456",
            },
            "Base URL",
        ),
        (
            {
                "provider": "deepseek",
                "model": "x",
                "base_url": "ftp://example.com",
                "api_key": "sk-value-123456",
            },
            "http",
        ),
        (
            {
                "provider": "deepseek",
                "model": "x",
                "base_url": "",
                "api_key": "sk-leak-me-123456\nsecond",
            },
            "控制字符",
        ),
        (
            {
                "provider": "deepseek",
                "model": "",
                "base_url": "",
                "api_key": "sk-value-123456",
            },
            "",  # empty model falls back to the provider default
        ),
    )
    for payload, fragment in cases:
        response = client.post("/api/settings", json=payload)
        if fragment == "":
            assert response.status_code == 200, response.text
            continue
        assert response.status_code == 400, response.text
        assert fragment in response.text
        assert "sk-value-123456" not in response.text
        assert "sk-leak-me-123456" not in response.text


def test_switching_provider_endpoint_requires_key(client: TestClient) -> None:
    first = client.post(
        "/api/settings",
        json={
            "provider": "deepseek",
            "model": "deepseek-chat",
            "base_url": "",
            "api_key": "sk-deepseek-123456",
        },
    )
    assert first.status_code == 200

    switched = client.post(
        "/api/settings",
        json={
            "provider": "openai",
            "model": "gpt-4o-mini",
            "base_url": "",
            "api_key": "",
        },
    )
    assert switched.status_code == 400
    assert "更换 AI 服务商" in switched.text


def test_settings_test_connection_success_and_failure(
    client: TestClient, monkeypatch
) -> None:
    monkeypatch.setattr(
        settings_module.LLMClient, "ping", lambda self: None
    )
    ok = client.post(
        "/api/settings/test",
        json={
            "provider": "deepseek",
            "model": "deepseek-chat",
            "base_url": "",
            "api_key": "sk-test-key-123456",
        },
    )
    assert ok.status_code == 200
    assert ok.json()["ok"] is True

    secret = "sk-test-key-123456"

    def _reject(_self) -> None:
        raise LLMError(f"upstream rejected {secret}")

    monkeypatch.setattr(settings_module.LLMClient, "ping", _reject)
    failed = client.post(
        "/api/settings/test",
        json={
            "provider": "deepseek",
            "model": "deepseek-chat",
            "base_url": "",
            "api_key": secret,
        },
    )
    assert failed.status_code == 200
    assert failed.json()["ok"] is False
    assert secret not in failed.text
    assert "***" in failed.text


def test_settings_routes_are_loopback_only(client: TestClient) -> None:
    blocked = client.get(
        "/api/settings", headers={"host": "192.168.1.50:8000"}
    )
    assert blocked.status_code == 403
    assert "本机" in blocked.text

    local = client.get("/api/settings", headers={"host": "localhost:8000"})
    assert local.status_code == 200


@pytest.mark.skipif(os.name == "nt", reason="Windows 不保留 POSIX 权限")
def test_posix_env_file_is_private(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    save_settings(
        path,
        provider="deepseek",
        model="deepseek-chat",
        base_url="",
        api_key="sk-test-key-123456",
        environ={},
    )
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_read_settings_uses_the_requested_env_file(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    _write_env(
        path,
        "NOVEL_LLM_PROVIDER=openai\n"
        "NOVEL_LLM_MODEL=gpt-4o-mini\n"
        "NOVEL_LLM_API_KEY=sk-test-key-123456\n",
    )
    payload = read_settings(environ={}, env_path=path)
    assert payload["provider"] == "openai"
    assert payload["key_configured"] is True
    assert "sk-test-key-123456" not in json.dumps(payload)
