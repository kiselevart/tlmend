"""OpenAI-compatible provider (DeepSeek, local Ollama, etc.) via httpx."""

from __future__ import annotations

import httpx

from tlmend.models import CompletionResult
from tlmend.providers.base import Message


class OpenAICompatProvider:
    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        input_price_per_m: float = 1.0,
        output_price_per_m: float = 2.0,
        extra_body: dict | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._in_price = input_price_per_m
        self._out_price = output_price_per_m
        self._extra_body = extra_body or {}
        self._client = httpx.AsyncClient(timeout=120)

    async def complete(
        self,
        messages: list[Message],
        *,
        prompt_version: str,
    ) -> CompletionResult:
        payload: dict = {
            "model": self._model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            **self._extra_body,
        }
        response = await self._client.post(
            f"{self._base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "content-type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()
        data = response.json()

        choice = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        cost = (prompt_tokens * self._in_price + completion_tokens * self._out_price) / 1_000_000

        return CompletionResult(
            text=choice,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            model=self._model,
            prompt_version=prompt_version,
            cost_usd=cost,
        )

    async def aclose(self) -> None:
        await self._client.aclose()
