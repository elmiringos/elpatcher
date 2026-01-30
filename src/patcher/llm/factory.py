"""Factory for creating LLM providers using LangChain."""

import os
from typing import Literal

from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI

from patcher.llm.provider import LLMProvider


ProviderType = Literal["claude", "openai"]


class LLMConfigError(Exception):
    """Raised when LLM configuration is invalid."""

    pass


def get_provider(
    provider_name: ProviderType | None = None,
    api_key: str | None = None,
    model: str | None = None,
    api_url: str | None = None,
    temperature: float = 0.7,
    max_tokens: int | None = None,
) -> LLMProvider:
    """Factory function to get the appropriate LLM provider.

    Args:
        provider_name: Provider type ('claude' or 'openai'). Defaults to LLM_PROVIDER env var.
        api_key: API key. Defaults to provider-specific env var.
        model: Model name. Defaults to provider-specific env var or default.
        api_url: Custom API URL. Defaults to LLM_API_URL env var.
        temperature: Default temperature for the model.
        max_tokens: Default max tokens for the model.

    Returns:
        Configured LLMProvider instance

    Raises:
        LLMConfigError: If configuration is invalid or missing
    """
    provider_name = provider_name or os.getenv("LLM_PROVIDER", "claude")  # type: ignore[assignment]
    api_url = api_url or os.getenv("LLM_API_URL")

    if provider_name == "openai":
        return _create_openai_provider(api_key, model, api_url, temperature, max_tokens)
    elif provider_name == "claude":
        return _create_claude_provider(api_key, model, api_url, temperature, max_tokens)
    else:
        raise LLMConfigError(
            f"Unknown provider: {provider_name}. Supported: 'claude', 'openai'"
        )


def _create_openai_provider(
    api_key: str | None,
    model: str | None,
    api_url: str | None,
    temperature: float,
    max_tokens: int | None,
) -> LLMProvider:
    """Create OpenAI provider."""
    api_key = api_key or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise LLMConfigError(
            "OpenAI API key not found. Set OPENAI_API_KEY environment variable."
        )

    model = model or os.getenv("OPENAI_MODEL", "gpt-4o")

    kwargs: dict = {
        "api_key": api_key,
        "model": model,
        "temperature": temperature,
    }

    if api_url:
        kwargs["base_url"] = api_url

    if max_tokens:
        kwargs["max_tokens"] = max_tokens

    chat_model = ChatOpenAI(**kwargs)
    return LLMProvider(model=chat_model, model_name=model)


def _create_claude_provider(
    api_key: str | None,
    model: str | None,
    api_url: str | None,
    temperature: float,
    max_tokens: int | None,
) -> LLMProvider:
    """Create Claude/Anthropic provider."""
    api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise LLMConfigError(
            "Anthropic API key not found. Set ANTHROPIC_API_KEY environment variable."
        )

    model = model or os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")

    kwargs: dict = {
        "api_key": api_key,
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens or 4096,
    }

    if api_url:
        kwargs["base_url"] = api_url

    chat_model = ChatAnthropic(**kwargs)
    return LLMProvider(model=chat_model, model_name=model)


def get_model(
    provider_name: ProviderType | None = None,
    api_key: str | None = None,
    model: str | None = None,
    **kwargs,
):
    """Get raw LangChain model without wrapper.

    Useful for direct LangChain integrations.

    Args:
        provider_name: Provider type
        api_key: API key
        model: Model name
        **kwargs: Additional model kwargs

    Returns:
        LangChain chat model instance
    """
    provider_name = provider_name or os.getenv("LLM_PROVIDER", "claude")  # type: ignore[assignment]

    if provider_name == "openai":
        api_key = api_key or os.getenv("OPENAI_API_KEY")
        model = model or os.getenv("OPENAI_MODEL", "gpt-4o")
        return ChatOpenAI(api_key=api_key, model=model, **kwargs)

    elif provider_name == "claude":
        api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        model = model or os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
        return ChatAnthropic(api_key=api_key, model=model, max_tokens=4096, **kwargs)

    raise LLMConfigError(f"Unknown provider: {provider_name}")
