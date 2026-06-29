"""Anthropic provider (claude-* models) via httpx."""

from __future__ import annotations

import httpx

from tlmend.models import CompletionResult
from tlmend.providers.base import Message

# Pricing per million tokens (update as models change)
_PRICING: dict[str, tuple[float, float]] = {
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5-20251001": (0.8, 4.0),
    "claude-opus-4-8": (15.0, 75.0),
}

_BASE_URL = "https://api.anthropic.com/v1/messages"


class AnthropicProvider:
    def __init__(self, api_key: str, model: str = "claude-sonnet-4-6") -> None:
        self._api_key = api_key
        self._model = model
        self._client = httpx.AsyncClient(timeout=120)

    async def complete(
        self,
        messages: list[Message],
        *,
        prompt_version: str,
    ) -> CompletionResult:
        system_msgs = [m for m in messages if m.role == "system"]
        user_msgs = [{"role": m.role, "content": m.content} for m in messages if m.role != "system"]
        system_text = "\n\n".join(m.content for m in system_msgs)

        payload: dict = {
            "model": self._model,
            "max_tokens": 8192,
            "messages": user_msgs,
        }
        if system_text:
            payload["system"] = system_text

        response = await self._client.post(
            _BASE_URL,
            headers={
                "x-api-key": self._api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()
        data = response.json()

        prompt_tokens: int = data["usage"]["input_tokens"]
        completion_tokens: int = data["usage"]["output_tokens"]
        text: str = data["content"][0]["text"]

        in_price, out_price = _PRICING.get(self._model, (3.0, 15.0))
        cost = (prompt_tokens * in_price + completion_tokens * out_price) / 1_000_000

        return CompletionResult(
            text=text,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            model=self._model,
            prompt_version=prompt_version,
            cost_usd=cost,
        )

    async def aclose(self) -> None:
        await self._client.aclose()
