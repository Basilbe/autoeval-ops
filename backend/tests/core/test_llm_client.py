from autoeval_ops.core.llm_client import build_llm_client, EchoLLMClient


async def test_build_llm_client_returns_echo_without_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = build_llm_client("gpt-4")
    assert isinstance(client, EchoLLMClient)


async def test_echo_llm_client_returns_fixed_score():
    client = EchoLLMClient()
    result = await client.complete("anything")
    assert result == "50"