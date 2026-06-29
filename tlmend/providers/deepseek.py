"""DeepSeek provider — thin wrapper around OpenAICompatProvider."""

from __future__ import annotations

from tlmend.providers.openai_compat import OpenAICompatProvider

_BASE_URL = "https://api.deepseek.com/v1"

# Pricing per million tokens (cache-miss input / output)
_MODELS: dict[str, tuple[float, float]] = {
    "deepseek-v4-flash": (0.14, 0.28),
    "deepseek-v4-pro":   (0.27, 1.10),
}


def DeepSeekProvider(
    api_key: str,
    model: str = "deepseek-v4-flash",
    thinking: bool = False,
) -> OpenAICompatProvider:
    in_price, out_price = _MODELS.get(model, (0.14, 0.28))
    extra_body: dict = {"thinking": {"type": "enabled" if thinking else "disabled"}}
    return OpenAICompatProvider(
        api_key=api_key,
        model=model,
        base_url=_BASE_URL,
        input_price_per_m=in_price,
        output_price_per_m=out_price,
        extra_body=extra_body,
    )
