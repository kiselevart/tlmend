"""Build provider instances from config + environment variables."""

from __future__ import annotations

import os

from tlmend.providers.anthropic import AnthropicProvider
from tlmend.providers.base import Provider
from tlmend.providers.deepseek import DeepSeekProvider
from tlmend.providers.openai_compat import OpenAICompatProvider

_ENV_KEYS: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "openai": "OPENAI_API_KEY",
    "openai-compat": "OPENAI_API_KEY",
}


def build_provider(config: dict[str, str]) -> Provider:
    """Instantiate a provider from a config section dict.

    Reads API keys from environment variables. Raises ``KeyError`` if the
    required env var is not set.
    """
    provider_name = config.get("provider", "anthropic")
    model = config.get("model", "")
    env_var = _ENV_KEYS.get(provider_name, f"{provider_name.upper()}_API_KEY")
    api_key = os.environ.get(env_var, "")

    match provider_name:
        case "anthropic":
            return AnthropicProvider(api_key=api_key, model=model)
        case "deepseek":
            return DeepSeekProvider(api_key=api_key, model=model)
        case "openai" | "openai-compat":
            base_url = config.get("base_url", "https://api.openai.com/v1")
            return OpenAICompatProvider(api_key=api_key, model=model, base_url=base_url)
        case _:
            raise ValueError(f"Unknown provider: {provider_name!r}")
