"""Minimal synchronous LLM client.

Supports the two wire protocols used by the configured providers:

* ``anthropic``: POST ``{base_url}/v1/messages``
* ``openai``:    POST ``{base_url}/chat/completions``

The client is intentionally small and dependency-free. It never logs the
payload or the API key.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from .config import LLMConfig

# Structured and revision calls run on thinking models. A small cap can be
# consumed entirely by reasoning blocks, leaving no text/JSON output.
DEFAULT_LLM_MAX_TOKENS = 16_384
MAX_RETRY_MAX_TOKENS = 65_536


class LLMError(RuntimeError):
    """Raised when the LLM endpoint fails or returns an unusable response."""


class LLMThinkingOnlyError(LLMError):
    """The response spent its whole output budget on thinking blocks."""


class LLMClient:
    def __init__(self, config: LLMConfig):
        self.config = config
        self._api_key = config.resolve_api_key()

    @property
    def endpoint(self) -> str:
        if not self.config.base_url:
            raise LLMError(
                f"provider {self.config.provider!r} requires a base URL"
            )
        base = self.config.base_url.rstrip("/")
        if self.config.protocol == "anthropic":
            return f"{base}/v1/messages"
        return f"{base}/chat/completions"

    def complete(
        self,
        prompt: str,
        *,
        system: str = "",
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        limit = self.config.max_tokens if max_tokens is None else max_tokens
        payload, headers = self._build_request(
            prompt,
            system=system,
            temperature=temperature,
            max_tokens=limit,
        )
        try:
            return self._parse_response(self._post(payload, headers))
        except LLMThinkingOnlyError:
            # Thinking-only output usually means the reasoning blocks ate the
            # output budget. Retry once with a larger cap before failing the
            # chapter and sending it to human review.
            retry_limit = min(
                max(limit * 2, DEFAULT_LLM_MAX_TOKENS), MAX_RETRY_MAX_TOKENS
            )
            if retry_limit <= limit:
                raise
            payload, headers = self._build_request(
                prompt,
                system=system,
                temperature=temperature,
                max_tokens=retry_limit,
            )
            return self._parse_response(self._post(payload, headers))

    def ping(self) -> None:
        """Check credentials with one tiny request.

        Any HTTP 2xx is treated as success. The body is deliberately not
        parsed: a thinking model may return only reasoning blocks even for a
        two-token prompt, and the settings dialog still wants to know that the
        endpoint accepted the key.
        """
        payload, headers = self._build_request(
            "Hi",
            system="",
            temperature=0.0,
            max_tokens=16,
        )
        self._post(payload, headers)

    def _post(self, payload: dict, headers: dict[str, str]) -> str:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self.endpoint,
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                request, timeout=self.config.timeout_seconds
            ) as response:
                return response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:500]
            raise LLMError(f"LLM HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise LLMError(f"LLM connection failed: {exc.reason}") from exc
        except OSError as exc:
            raise LLMError(f"LLM connection failed: {exc}") from exc

    def _build_request(
        self,
        prompt: str,
        *,
        system: str,
        temperature: float | None,
        max_tokens: int | None,
    ) -> tuple[dict, dict[str, str]]:
        temp = self.config.temperature if temperature is None else temperature
        limit = self.config.max_tokens if max_tokens is None else max_tokens
        if self.config.protocol == "anthropic":
            payload: dict = {
                "model": self.config.model,
                "max_tokens": limit,
                "temperature": temp,
                "messages": [{"role": "user", "content": prompt}],
            }
            if system:
                payload["system"] = system
            headers = {
                "content-type": "application/json",
                "x-api-key": self._api_key,
                "anthropic-version": "2023-06-01",
            }
            return payload, headers

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload = {
            "model": self.config.model,
            "messages": messages,
            "temperature": temp,
            "max_tokens": limit,
        }
        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {self._api_key}",
        }
        return payload, headers

    def _parse_response(self, raw: str) -> str:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LLMError("LLM returned non-JSON response") from exc

        if self.config.protocol == "anthropic":
            blocks = data.get("content")
            if not isinstance(blocks, list):
                raise LLMError("LLM response is missing content blocks")
            text = "".join(
                block.get("text", "")
                for block in blocks
                if isinstance(block, dict) and block.get("type") == "text"
            )
        else:
            choices = data.get("choices")
            if not isinstance(choices, list) or not choices:
                raise LLMError("LLM response is missing choices")
            message = choices[0].get("message", {})
            text = message.get("content", "")

        if not isinstance(text, str) or not text.strip():
            has_thinking = (
                self.config.protocol == "anthropic"
                and isinstance(data.get("content"), list)
                and any(
                    isinstance(block, dict) and block.get("type") == "thinking"
                    for block in data["content"]
                )
            )
            if has_thinking:
                raise LLMThinkingOnlyError(
                    "LLM returned only thinking blocks; increase max_tokens "
                    "or disable thinking"
                )
            raise LLMError("LLM returned an empty response")
        return text
