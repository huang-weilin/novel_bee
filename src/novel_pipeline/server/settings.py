"""AI settings for the local web app.

The browser writes only the four ``NOVEL_LLM_*`` keys into the local ``.env``.
Nothing here talks to a central service: the key stays on this machine and is
never returned by an HTTP response. Environment variables still win over the
file, matching :mod:`novel_pipeline.envfile`.
"""

from __future__ import annotations

import os
import re
import tempfile
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlparse

from ..config import (
    DEFAULT_MODELS,
    PROVIDERS,
    ConfigError,
    LLMConfig,
)
from ..envfile import parse_env
from ..llm import LLMClient, LLMError

MANAGED_KEYS = (
    "NOVEL_LLM_PROVIDER",
    "NOVEL_LLM_MODEL",
    "NOVEL_LLM_BASE_URL",
    "NOVEL_LLM_API_KEY",
)

PROVIDER_LABELS = {
    "deepseek": "DeepSeek",
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "openai-compatible": "OpenAI 兼容接口",
    "anthropic-compatible": "Anthropic 兼容接口",
    "ollama": "Ollama（本地）",
}

_LINE = re.compile(
    r"^(?P<prefix>[ \t]*(?:export[ \t]+)?)"
    r"(?P<key>[A-Za-z_][A-Za-z0-9_]*)[ \t]*=[ \t]*(?P<value>.*)$"
)
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_REDACT = re.compile(r"\b(?:sk|pk|dsk)-[A-Za-z0-9_-]{8,}\b")
_MAX_CONNECTION_TIMEOUT = 30.0


class SettingsError(ValueError):
    """A user-facing settings problem that never contains the API key."""


def provider_options() -> list[dict]:
    """Describe providers from the single source of truth in ``config.py``."""
    options = []
    for key, profile in PROVIDERS.items():
        options.append(
            {
                "key": key,
                "label": PROVIDER_LABELS.get(key, key),
                "protocol": profile.protocol,
                "default_model": DEFAULT_MODELS.get(key, ""),
                "default_base_url": profile.default_base_url or "",
                "requires_base_url": key.endswith("-compatible"),
                "requires_key": key != "ollama",
            }
        )
    return options


def _clean(value: str | None) -> str:
    return (value or "").strip()


def _merged_env(
    env_path: str | Path | None, environ: Mapping[str, str] | None
) -> dict[str, str]:
    merged: dict[str, str] = {}
    if env_path is not None:
        path = Path(env_path)
        if path.is_file():
            merged.update(parse_env(path.read_text(encoding="utf-8")))
    if environ is None:
        merged.update(os.environ)
    else:
        merged.update({str(key): str(value) for key, value in environ.items()})
    return merged


def _resolved_key(
    source: Mapping[str, str], provider: str, profile
) -> str:
    """Best-effort key lookup without raising; used for summaries."""
    if provider == "ollama":
        return "ollama"
    direct = _clean(source.get("NOVEL_LLM_API_KEY"))
    if direct:
        return direct
    key_env = _clean(source.get("NOVEL_LLM_API_KEY_ENV")) or (
        profile.default_api_key_env or ""
    )
    if key_env:
        return _clean(source.get(key_env))
    return ""


def read_settings(
    environ: Mapping[str, str] | None = None,
    *,
    data_path: str | Path | None = None,
    env_path: str | Path | None = ".env",
) -> dict:
    """Return a key-free summary for the settings dialog and health check."""
    source = _merged_env(env_path, environ)
    raw_provider = _clean(source.get("NOVEL_LLM_PROVIDER", "deepseek")).lower()
    from ..config import ALIASES  # local import avoids a public re-export

    provider = ALIASES.get(raw_provider, raw_provider)
    profile = PROVIDERS.get(provider)
    payload: dict = {
        "provider": provider or raw_provider,
        "model": _clean(source.get("NOVEL_LLM_MODEL")),
        "base_url": _clean(source.get("NOVEL_LLM_BASE_URL")),
        "key_configured": False,
        "providers": provider_options(),
        "data_path": str(data_path) if data_path is not None else None,
        "env_path": str(env_path) if env_path is not None else None,
        "error": None,
    }
    if profile is None:
        payload["error"] = f"未知的 AI 服务商：{raw_provider}"
        return payload

    try:
        config = LLMConfig.from_env(source, validate_key=False)
    except ConfigError as exc:
        payload["error"] = str(exc)
        return payload

    payload.update(
        {
            "provider": config.provider,
            "model": config.model,
            "base_url": config.base_url or "",
            "key_configured": bool(
                config.provider == "ollama"
                or _resolved_key(source, config.provider, profile)
            ),
        }
    )
    return payload


def _validate_text(value: str, label: str) -> str:
    cleaned = value.strip()
    if _CONTROL.search(cleaned):
        raise SettingsError(f"{label}不能包含换行或控制字符")
    return cleaned


def _validate_base_url(value: str, *, required: bool) -> str:
    base_url = _validate_text(value, "Base URL").rstrip("/")
    if not base_url:
        if required:
            raise SettingsError("这个服务商必须填写 Base URL")
        return ""
    parsed = urlparse(base_url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise SettingsError("Base URL 必须是完整的 http:// 或 https:// 地址")
    if any(char.isspace() for char in base_url):
        raise SettingsError("Base URL 不能包含空格")
    return base_url


def validate_settings(
    *,
    provider: str,
    model: str,
    base_url: str,
    api_key: str,
    environ: Mapping[str, str] | None = None,
    env_path: str | Path | None = None,
) -> LLMConfig:
    """Validate dialog values and return a ready-to-use config.

    A blank ``api_key`` reuses the current key only when the provider did not
    change, or when the new provider already has its own dedicated env var.
    This avoids silently sending a DeepSeek key to OpenAI after a switch.
    """
    source = _merged_env(env_path, environ)
    raw_provider = _clean(provider).lower()
    from ..config import ALIASES

    normalized = ALIASES.get(raw_provider, raw_provider)
    profile = PROVIDERS.get(normalized)
    if profile is None:
        raise SettingsError(f"未知的 AI 服务商：{raw_provider or '（空）'}")

    model_name = _validate_text(model, "模型名") or DEFAULT_MODELS.get(
        normalized, ""
    )
    if not model_name:
        raise SettingsError("请填写模型名，例如 deepseek-chat")

    base = _validate_base_url(
        base_url, required=normalized.endswith("-compatible")
    )
    cleaned_key = _validate_text(api_key, "API Key")

    old_provider = _clean(source.get("NOVEL_LLM_PROVIDER", "deepseek")).lower()
    old_provider = ALIASES.get(old_provider, old_provider)

    effective_key = cleaned_key
    if not effective_key and normalized != "ollama":
        if old_provider != normalized:
            # A direct NOVEL_LLM_API_KEY from the previous provider would shadow
            # any new provider-specific env var after a restart. Requiring a
            # fresh key keeps provider switches unambiguous.
            raise SettingsError("更换 AI 服务商后，请填写新的 API Key")
        effective_key = _resolved_key(source, normalized, profile)
        if not effective_key:
            raise SettingsError("请填写 API Key（当前没有已保存的 Key）")

    prepared = dict(source)
    prepared.update(
        {
            "NOVEL_LLM_PROVIDER": normalized,
            "NOVEL_LLM_MODEL": model_name,
            "NOVEL_LLM_BASE_URL": base,
            "NOVEL_LLM_API_KEY": effective_key or "ollama",
            "NOVEL_LLM_API_KEY_ENV": profile.default_api_key_env or "",
        }
    )
    try:
        return LLMConfig.from_env(prepared)
    except ConfigError as exc:
        raise SettingsError(str(exc)) from exc


def _env_value(value: str, label: str) -> str:
    """Format a value for the flat ``KEY=VALUE`` parser in envfile.py."""
    if _CONTROL.search(value):
        raise SettingsError(f"{label}不能包含换行或控制字符")
    if value and (" " in value or "\t" in value or "#" in value):
        if '"' in value or "'" in value:
            raise SettingsError(f"{label}包含无法安全保存的引号字符")
        return f'"{value}"'
    return value


def _update_env_text(text: str, updates: dict[str, str]) -> str:
    """Replace managed lines in place and append any missing keys."""
    remaining = dict(updates)
    managed = set(updates)
    written: set[str] = set()
    output: list[str] = []
    for line in text.splitlines():
        match = _LINE.match(line)
        if match is None:
            output.append(line)
            continue
        key = match.group("key")
        if key not in managed:
            output.append(line)
            continue
        if key in written:
            # Drop duplicate active keys so the last value cannot win later.
            continue
        output.append(f"{match.group('prefix')}{key}={remaining.pop(key)}")
        written.add(key)
    for key in MANAGED_KEYS:
        if key in remaining:
            output.append(f"{key}={remaining[key]}")
    if not output:
        output = ["# Local AI settings written by the web UI."]
    return "\n".join(output).rstrip("\n") + "\n"


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=".env.", dir=str(path.parent), text=True
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        if os.name != "nt":
            os.chmod(temp_name, 0o600)
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def save_settings(
    path: str | Path,
    *,
    provider: str,
    model: str,
    base_url: str,
    api_key: str,
    environ: Mapping[str, str] | None = None,
    data_path: str | Path | None = None,
) -> dict:
    """Write the four managed keys to ``path`` and update this process."""
    env_path = Path(path)
    config = validate_settings(
        provider=provider,
        model=model,
        base_url=base_url,
        api_key=api_key,
        environ=environ,
        env_path=env_path,
    )
    explicit_key = _clean(api_key)
    updates = {
        "NOVEL_LLM_PROVIDER": config.provider,
        "NOVEL_LLM_MODEL": config.model,
        "NOVEL_LLM_BASE_URL": _env_value(config.base_url or "", "Base URL"),
    }
    if explicit_key:
        updates["NOVEL_LLM_API_KEY"] = _env_value(explicit_key, "API Key")

    existing = (
        env_path.read_text(encoding="utf-8-sig")
        if env_path.is_file()
        else ""
    )
    _atomic_write(env_path, _update_env_text(existing, updates))

    process_updates = {
        "NOVEL_LLM_PROVIDER": config.provider,
        "NOVEL_LLM_MODEL": config.model,
        "NOVEL_LLM_BASE_URL": config.base_url or "",
        "NOVEL_LLM_API_KEY": config.resolve_api_key(),
        "NOVEL_LLM_API_KEY_ENV": PROVIDERS[config.provider].default_api_key_env
        or "",
    }
    os.environ.update(process_updates)

    return read_settings(
        environ=environ,
        data_path=data_path,
        env_path=env_path,
    )


def _redact(message: str, secret: str) -> str:
    if secret:
        message = message.replace(secret, "***")
    message = _REDACT.sub("***", message)
    return message[:400]


def test_connection(
    *,
    provider: str,
    model: str,
    base_url: str,
    api_key: str,
    environ: Mapping[str, str] | None = None,
    env_path: str | Path | None = None,
) -> dict:
    """Make one tiny request; never save and never echo the key."""
    secret = _clean(api_key)
    try:
        config = validate_settings(
            provider=provider,
            model=model,
            base_url=base_url,
            api_key=api_key,
            environ=environ,
            env_path=env_path,
        )
        secret = config.resolve_api_key()
        config = replace(
            config,
            timeout_seconds=min(
                config.timeout_seconds, _MAX_CONNECTION_TIMEOUT
            ),
        )
        LLMClient(config).ping()
    except SettingsError as exc:
        return {"ok": False, "message": _redact(str(exc), secret)}
    except (LLMError, ConfigError, OSError) as exc:
        return {"ok": False, "message": _redact(str(exc), secret)}
    return {
        "ok": True,
        "message": "连接成功",
        "provider": config.provider,
        "model": config.model,
    }


__all__ = [
    "MANAGED_KEYS",
    "SettingsError",
    "provider_options",
    "read_settings",
    "save_settings",
    "test_connection",
    "validate_settings",
]
