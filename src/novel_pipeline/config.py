"""Environment-driven LLM configuration.

Secrets are never hardcoded. ``LLMConfig`` stores the *name* of the env var
that holds the key and resolves the value only when a client is built.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field


class ConfigError(ValueError):
    """Raised when the LLM configuration is invalid or incomplete."""


@dataclass(frozen=True)
class ProviderProfile:
    protocol: str  # "openai" | "anthropic"
    default_base_url: str | None
    default_api_key_env: str | None


PROVIDERS: dict[str, ProviderProfile] = {
    "deepseek": ProviderProfile(
        "openai", "https://api.deepseek.com", "DEEPSEEK_API_KEY"
    ),
    "openai": ProviderProfile(
        "openai", "https://api.openai.com/v1", "OPENAI_API_KEY"
    ),
    "anthropic": ProviderProfile(
        "anthropic", "https://api.anthropic.com", "ANTHROPIC_API_KEY"
    ),
    # Compatible endpoints require an explicit base URL and model.
    "openai-compatible": ProviderProfile("openai", None, "OPENAI_API_KEY"),
    "anthropic-compatible": ProviderProfile("anthropic", None, "ANTHROPIC_API_KEY"),
    "ollama": ProviderProfile("openai", "http://localhost:11434/v1", None),
}

ALIASES = {"claude": "anthropic", "gpt": "openai"}

DEFAULT_MODELS = {
    "deepseek": "deepseek-chat",
    "openai": "gpt-4o-mini",
    "anthropic": "claude-sonnet-5",
}


def _text(
    env: Mapping[str, str], key: str, default: str | None = None
) -> str | None:
    value = env.get(key)
    if value is None or not value.strip():
        return default
    return value.strip()


def _number(
    env: Mapping[str, str],
    key: str,
    default,
    *,
    cast,
    minimum,
    maximum,
):
    raw = env.get(key)
    if raw is None or not raw.strip():
        return default
    try:
        value = cast(raw)
    except ValueError as exc:
        raise ConfigError(f"{key} must be a number, got {raw!r}") from exc
    if not minimum <= value <= maximum:
        raise ConfigError(
            f"{key} must be between {minimum} and {maximum}, got {value}"
        )
    return value


@dataclass(frozen=True)
class LLMConfig:
    provider: str
    model: str
    base_url: str | None
    api_key_env: str | None
    api_key: str | None = field(default=None, repr=False, compare=False)
    temperature: float = 0.8
    max_tokens: int = 4096
    timeout_seconds: float = 120.0

    @property
    def protocol(self) -> str:
        """Wire protocol the client should use: ``openai`` or ``anthropic``."""
        return PROVIDERS[self.provider].protocol

    def resolve_api_key(self, env: Mapping[str, str] | None = None) -> str:
        if self.provider == "ollama":
            return "ollama"
        if self.api_key:
            return self.api_key
        source = os.environ if env is None else env
        if not self.api_key_env:
            raise ConfigError(
                f"provider {self.provider!r} has no configured API key source"
            )
        value = source.get(self.api_key_env, "").strip()
        if not value:
            raise ConfigError(
                f"API key for provider {self.provider!r} is missing: "
                f"set {self.api_key_env} (or NOVEL_LLM_API_KEY)"
            )
        return value

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
        *,
        validate_key: bool = True,
    ) -> LLMConfig:
        source = os.environ if env is None else env
        raw_provider = (
            _text(source, "NOVEL_LLM_PROVIDER", "deepseek") or "deepseek"
        ).lower()
        provider = ALIASES.get(raw_provider, raw_provider)
        profile = PROVIDERS.get(provider)
        if profile is None:
            raise ConfigError(
                f"unknown provider {raw_provider!r}; choose from "
                f"{', '.join(sorted(PROVIDERS))}"
            )

        model = _text(source, "NOVEL_LLM_MODEL", DEFAULT_MODELS.get(provider))
        if not model:
            raise ConfigError(f"NOVEL_LLM_MODEL is required for provider {provider!r}")

        base_url = _text(source, "NOVEL_LLM_BASE_URL", profile.default_base_url)
        if base_url:
            base_url = base_url.rstrip("/")
        if provider.endswith("-compatible") and not base_url:
            raise ConfigError(f"provider {provider!r} requires NOVEL_LLM_BASE_URL")

        api_key_env = _text(
            source, "NOVEL_LLM_API_KEY_ENV", profile.default_api_key_env
        )
        direct_key = _text(source, "NOVEL_LLM_API_KEY")
        if provider != "ollama" and not direct_key and not api_key_env:
            raise ConfigError(
                f"provider {provider!r} requires NOVEL_LLM_API_KEY "
                "or NOVEL_LLM_API_KEY_ENV"
            )

        cfg = cls(
            provider=provider,
            model=model,
            base_url=base_url,
            api_key_env=api_key_env,
            api_key=direct_key,
            temperature=_number(
                source, "NOVEL_LLM_TEMPERATURE", 0.8,
                cast=float, minimum=0.0, maximum=2.0,
            ),
            max_tokens=_number(
                source, "NOVEL_LLM_MAX_TOKENS", 4096,
                cast=int, minimum=1, maximum=200_000,
            ),
            timeout_seconds=_number(
                source, "NOVEL_LLM_TIMEOUT", 120.0,
                cast=float, minimum=1.0, maximum=3600.0,
            ),
        )
        if validate_key and provider != "ollama":
            cfg.resolve_api_key(source)
        return cfg

    def to_storyagents_env(
        self, env: Mapping[str, str] | None = None
    ) -> dict[str, str]:
        """Map this config to env vars consumed by Mo-Shen / StoryAgents."""
        key = self.resolve_api_key(env)
        out: dict[str, str] = {
            "STORYAGENTS_DEEP_THINK_LLM": self.model,
            "STORYAGENTS_QUICK_THINK_LLM": self.model,
        }
        if self.provider == "deepseek":
            out.update(
                {
                    "STORYAGENTS_LLM_PROVIDER": "deepseek",
                    "DEEPSEEK_API_KEY": key,
                }
            )
            if self.base_url:
                out["STORYAGENTS_LLM_BACKEND_URL"] = self.base_url
        elif self.provider in ("anthropic", "anthropic-compatible"):
            out.update(
                {
                    "STORYAGENTS_LLM_PROVIDER": "anthropic",
                    "ANTHROPIC_API_KEY": key,
                }
            )
            if self.base_url:
                # AgentScope's Anthropic client reads ANTHROPIC_BASE_URL.
                out["ANTHROPIC_BASE_URL"] = self.base_url
        elif self.provider in ("openai", "openai-compatible", "ollama"):
            out.update(
                {
                    "STORYAGENTS_LLM_PROVIDER": "openai",
                    "OPENAI_API_KEY": key or "ollama",
                }
            )
            if self.base_url:
                out["STORYAGENTS_LLM_BACKEND_URL"] = self.base_url
        else:  # pragma: no cover - PROVIDERS is a closed set
            raise ConfigError(f"unsupported provider {self.provider!r}")
        return out
