"""Shared LLM client used by both the CLI (Phase 1) and the GitHub
orchestrator (Phase 2) - one implementation of 'talk to the real model, or
fall back to a placeholder' instead of two.

Phase 6 adds GeminiLLMClient alongside OpenAILLMClient. Google AI
Studio's free tier is rate-limited rather than metered, which is a
better fit for a portfolio demo evaluated occasionally than paying per
call to OpenAI - build_llm_client checks GOOGLE_API_KEY first for that
reason. Both clients implement the same LLMClient protocol, so nothing
downstream (the pipeline, the orchestrator, the CLI) needs to know or
care which provider is actually in use.
"""
from __future__ import annotations
import os
from typing import Protocol


class LLMClient(Protocol):
    async def complete(self, prompt: str) -> str: ...


class EchoLLMClient:
    """Fallback used when no API key is set, so callers still run
    end-to-end for local demos without hitting a real API."""

    async def complete(self, prompt: str) -> str:
        return "50"


class GeminiLLMClient:  # pragma: no cover - requires a real GOOGLE_API_KEY
    """Google AI Studio's Gemini API. Free tier, no card required -
    rate-limited (requests per minute/day) rather than billed per call."""

    def __init__(self, model: str, api_key: str):
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel(model)

    async def complete(self, prompt: str) -> str:
        response = await self._model.generate_content_async(prompt)
        return response.text or ""


class OpenAILLMClient:  # pragma: no cover - requires a real OPENAI_API_KEY
    def __init__(self, model: str, api_key: str):
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model

    async def complete(self, prompt: str) -> str:
        resp = await self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=256,
        )
        return resp.choices[0].message.content or ""


def build_llm_client(model: str) -> LLMClient:
    """GOOGLE_API_KEY is checked first - see the module docstring for why.
    OPENAI_API_KEY still works if that's what's configured instead."""
    google_key = os.environ.get("GOOGLE_API_KEY")
    if google_key:  # pragma: no cover - requires a real GOOGLE_API_KEY
        return GeminiLLMClient(model=model, api_key=google_key)

    openai_key = os.environ.get("OPENAI_API_KEY")
    if openai_key:  # pragma: no cover - requires a real OPENAI_API_KEY
        return OpenAILLMClient(model=model, api_key=openai_key)

    return EchoLLMClient()