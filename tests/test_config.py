import os

import pytest

from novel_pipeline.config import ConfigError, LLMConfig


def test_default_deepseek() -> None:
    env = {"DEEPSEEK_API_KEY": "sk-test"}
    cfg = LLMConfig.from_env(env)
    assert cfg.provider == "deepseek"
    assert cfg.model == "deepseek-chat"
    assert cfg.base_url == "https://api.deepseek.com"
    assert cfg.protocol == "openai"
    assert cfg.resolve_api_key(env) == "sk-test"


def test_anthropic_compatible_with_auth_token() -> None:
    env = {
        "NOVEL_LLM_PROVIDER": "anthropic-compatible",
        "NOVEL_LLM_BASE_URL": "https://api.deepseek.com/anthropic/",
        "NOVEL_LLM_MODEL": "deepseek-v4-flash",
        "NOVEL_LLM_API_KEY_ENV": "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_AUTH_TOKEN": "sk-test",
    }
    cfg = LLMConfig.from_env(env)
    assert cfg.provider == "anthropic-compatible"
    assert cfg.base_url == "https://api.deepseek.com/anthropic"
    assert cfg.protocol == "anthropic"
    assert cfg.resolve_api_key(env) == "sk-test"


def test_compatible_requires_base_url() -> None:
    env = {
        "NOVEL_LLM_PROVIDER": "anthropic-compatible",
        "NOVEL_LLM_MODEL": "x",
        "ANTHROPIC_API_KEY": "k",
    }
    with pytest.raises(ConfigError, match="NOVEL_LLM_BASE_URL"):
        LLMConfig.from_env(env)


def test_compatible_requires_model() -> None:
    env = {
        "NOVEL_LLM_PROVIDER": "openai-compatible",
        "NOVEL_LLM_BASE_URL": "http://localhost:1234/v1",
        "OPENAI_API_KEY": "k",
    }
    with pytest.raises(ConfigError, match="NOVEL_LLM_MODEL"):
        LLMConfig.from_env(env)


def test_missing_key() -> None:
    with pytest.raises(ConfigError, match="DEEPSEEK_API_KEY"):
        LLMConfig.from_env(
            {"NOVEL_LLM_PROVIDER": "deepseek", "NOVEL_LLM_MODEL": "deepseek-chat"}
        )


def test_validate_key_false_allows_missing_key() -> None:
    cfg = LLMConfig.from_env({"NOVEL_LLM_PROVIDER": "deepseek"}, validate_key=False)
    assert cfg.model == "deepseek-chat"


def test_storyagents_mapping_anthropic_compatible() -> None:
    env = {
        "NOVEL_LLM_PROVIDER": "anthropic-compatible",
        "NOVEL_LLM_BASE_URL": "https://api.deepseek.com/anthropic",
        "NOVEL_LLM_MODEL": "deepseek-v4-flash",
        "NOVEL_LLM_API_KEY_ENV": "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_AUTH_TOKEN": "sk-test",
    }
    out = LLMConfig.from_env(env).to_storyagents_env(env)
    assert out["STORYAGENTS_LLM_PROVIDER"] == "anthropic"
    assert out["ANTHROPIC_API_KEY"] == "sk-test"
    assert out["ANTHROPIC_BASE_URL"] == "https://api.deepseek.com/anthropic"
    assert out["STORYAGENTS_QUICK_THINK_LLM"] == "deepseek-v4-flash"
    assert "ANTHROPIC_AUTH_TOKEN" not in out


def test_invalid_temperature() -> None:
    env = {"DEEPSEEK_API_KEY": "k", "NOVEL_LLM_TEMPERATURE": "3"}
    with pytest.raises(ConfigError, match="NOVEL_LLM_TEMPERATURE"):
        LLMConfig.from_env(env)


def test_from_env_loads_dotenv_without_overriding_shell(
    tmp_path, monkeypatch
) -> None:
    (tmp_path / ".env").write_text(
        "NOVEL_LLM_PROVIDER=deepseek\n"
        "NOVEL_LLM_MODEL=file-model\n"
        "DEEPSEEK_API_KEY=sk-file\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    env = {"NOVEL_LLM_MODEL": "shell-model"}
    monkeypatch.setattr(os, "environ", env)

    cfg = LLMConfig.from_env()

    assert cfg.provider == "deepseek"
    assert cfg.model == "shell-model"
    assert cfg.resolve_api_key() == "sk-file"
