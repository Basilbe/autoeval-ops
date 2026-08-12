"""Shared LLM client used by both the CLI (Phase 1) and the GitHub
orchestrator (Phase 2) — one implementation of 'talk to the real model, or
fall back to a placeholder' instead of two."""
from __future__ import annotations
import os
from typing import Protocol


class LLMClient(Protocol):
    async def complete(self, prompt: str) -> str: ...


class EchoLLMClient:
    """Fallback used when no OPENAI_API_KEY is set, so callers still run
    end-to-end for local demos without hitting a real API."""

    async def complete(self, prompt: str) -> str:
        return "50"


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
    api_key = os.environ.get("OPENAI_API_KEY")
    if api_key:  # pragma: no cover - requires a real OPENAI_API_KEY
        return OpenAILLMClient(model=model, api_key=api_key)
    return EchoLLMClient()