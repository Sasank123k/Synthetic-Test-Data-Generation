"""
Abstract LLM Client — Provider-Agnostic Interface

Supports OpenAI (default) and Google Gemini via LangChain.
Swap providers by changing LLM_PROVIDER in .env — no code changes required.

Usage:
    from app.services.llm_client import get_llm, invoke_llm_json

    # Get the raw LangChain chat model
    llm = get_llm()

    # Convenience: invoke with strict JSON output
    result = await invoke_llm_json(
        system_prompt="You are a data engineering expert...",
        user_prompt="Generate a config for credit scoring...",
    )
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.language_models import BaseChatModel

from app.config import settings


def get_llm(temperature: float = 0.0) -> BaseChatModel:
    """
    Factory function returning a LangChain chat model based on the
    configured LLM_PROVIDER environment variable.

    Args:
        temperature: Sampling temperature. Default 0.0 for deterministic outputs.

    Returns:
        A LangChain BaseChatModel instance (OpenAI or Gemini).

    Raises:
        ValueError: If the configured provider is unsupported.
    """
    provider = settings.llm_provider.lower()

    if provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=settings.openai_model,
            temperature=temperature,
            api_key=settings.openai_api_key,
            model_kwargs={"response_format": {"type": "json_object"}},
        )

    elif provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=settings.gemini_model,
            temperature=temperature,
            google_api_key=settings.google_api_key,
            convert_system_message_to_human=True,
        )

    else:
        raise ValueError(
            f"Unsupported LLM provider: '{provider}'. "
            f"Set LLM_PROVIDER to 'openai' or 'gemini' in your .env file."
        )


async def invoke_llm_json(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.0,
) -> dict[str, Any]:
    """
    Invoke the configured LLM with a system + user prompt pair
    and parse the response as JSON.

    This is the primary interface used by the Actor-Critic pipeline.

    Args:
        system_prompt: The system-level instruction (e.g., schema constraints).
        user_prompt: The user's natural language request.
        temperature: Sampling temperature override.

    Returns:
        Parsed JSON dict from the LLM response.

    Raises:
        json.JSONDecodeError: If the LLM response is not valid JSON.
    """
    llm = get_llm(temperature=temperature)

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    response = await llm.ainvoke(messages)
    content = response.content

    # Strip markdown backticks if the LLM output them
    content = content.strip()
    if content.startswith("```json"):
        content = content[7:]
    elif content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    content = content.strip()

    # Parse the JSON response
    return json.loads(content)


async def invoke_llm_text(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.0,
) -> str:
    """
    Invoke the configured LLM and return raw text response.
    Used by the Critic step for free-form evaluation feedback.

    Args:
        system_prompt: The system-level instruction.
        user_prompt: The content to evaluate.
        temperature: Sampling temperature override.

    Returns:
        Raw text string from the LLM response.
    """
    # For text responses, create a separate LLM without JSON mode
    provider = settings.llm_provider.lower()

    if provider == "openai":
        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(
            model=settings.openai_model,
            temperature=temperature,
            api_key=settings.openai_api_key,
        )
    elif provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        llm = ChatGoogleGenerativeAI(
            model=settings.gemini_model,
            temperature=temperature,
            google_api_key=settings.google_api_key,
            convert_system_message_to_human=True,
        )
    else:
        raise ValueError(f"Unsupported LLM provider: '{provider}'.")

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    response = await llm.ainvoke(messages)
    return response.content
