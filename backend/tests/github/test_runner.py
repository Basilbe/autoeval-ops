from autoeval_ops.github.runner import PromptRunner


class FakeLLMClient:
    def __init__(self, response: str = "a generated answer"):
        self.response = response
        self.received_prompts: list[str] = []

    async def complete(self, prompt: str) -> str:
        self.received_prompts.append(prompt)
        return self.response


async def test_runner_renders_prompt_template_per_case():
    client = FakeLLMClient()
    runner = PromptRunner(client)
    cases = [{"input": "hello"}, {"input": "world"}]
    await runner.run("Echo: {text}", cases)
    assert client.received_prompts == ["Echo: hello", "Echo: world"]


async def test_runner_produces_pipeline_shaped_output():
    client = FakeLLMClient(response="generated")
    runner = PromptRunner(client)
    cases = [{"input": "x", "expected": "y", "context": "z"}]
    results = await runner.run("{text}", cases)
    assert results[0]["output"] == "generated"
    assert results[0]["expected"] == "y"
    assert results[0]["context"] == "z"
    assert results[0]["latency_ms"] >= 0


async def test_runner_defaults_missing_optional_fields():
    client = FakeLLMClient()
    runner = PromptRunner(client)
    results = await runner.run("{text}", [{"input": "only input"}])
    assert results[0]["expected"] == ""
    assert results[0]["context"] == ""


async def test_runner_handles_empty_test_case_list():
    client = FakeLLMClient()
    runner = PromptRunner(client)
    results = await runner.run("{text}", [])
    assert results == []