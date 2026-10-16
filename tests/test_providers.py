import json

import httpx
import pytest

from openfitkit.providers import DemoProvider, OpenAICompatibleProvider, ProviderError, build_provider
from openfitkit.settings import Settings


def live_settings(provider="openai"):
    return Settings(provider=provider, model="example/model:latest", api_key="private-test-key")


def completion(answer="A manageable first step.", finish_reason="stop"):
    return {"choices": [{"finish_reason": finish_reason, "message": {"role": "assistant", "content": answer}}]}


def test_demo_is_static_offline_even_when_keys_exist(monkeypatch):
    monkeypatch.setenv("OPENFITKIT_API_KEY", "private-test-key")
    monkeypatch.setattr(httpx.Client, "post", lambda *args, **kwargs: pytest.fail("Unexpected network request"))
    provider = build_provider(Settings.from_env())
    assert isinstance(provider, DemoProvider)
    answer = provider.generate(instructions="Be helpful", messages=[{"role": "user", "content": "Build a plan"}])
    assert "fixed demonstration" in answer
    assert "not personalized coaching" in answer
    assert "No AI request was sent" in answer
    assert provider.generate(instructions="Different", messages=[]) == answer


@pytest.mark.parametrize("provider", ["openai", "openrouter"])
def test_live_payload_uses_fixed_endpoint_and_output_limit(provider):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=completion())

    with httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
        adapter = OpenAICompatibleProvider(live_settings(provider), client=client)
        answer = adapter.generate(instructions="Fitness only", messages=[{"role": "user", "content": "Hello"}])
    assert answer == "A manageable first step."
    assert len(calls) == 1
    request = calls[0]
    assert str(request.url) == OpenAICompatibleProvider.ENDPOINTS[provider]
    assert request.headers["Authorization"] == "Bearer private-test-key"
    payload = json.loads(request.content)
    assert payload["model"] == "example/model:latest"
    assert payload["messages"] == [{"role": "system", "content": "Fitness only"}, {"role": "user", "content": "Hello"}]
    assert payload["max_completion_tokens" if provider == "openai" else "max_tokens"] == 1200
    assert request.extensions["timeout"]["read"] == 60


@pytest.mark.parametrize("settings", [Settings(provider="openai"), Settings(provider="openai", model="model"), Settings(provider="openrouter", api_key="test")])
def test_missing_live_configuration_fails_before_requests(settings):
    with pytest.raises(ValueError, match="requires OPENFITKIT_MODEL and OPENFITKIT_API_KEY"):
        build_provider(settings)


@pytest.mark.parametrize("status", [301, 401, 403, 429, 500])
def test_http_failures_are_safe_and_never_retry_or_follow_redirects(status):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, text="private-test-key and sensitive athlete content", headers={"Location": "https://untrusted.example"})

    with httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
        adapter = OpenAICompatibleProvider(live_settings(), client=client)
        with pytest.raises(ProviderError) as error:
            adapter.generate(instructions="Fitness", messages=[])
    assert len(calls) == 1
    assert "private-test-key" not in str(error.value)
    assert "sensitive athlete" not in str(error.value)
    assert "untrusted" not in str(error.value)


@pytest.mark.parametrize("body", [
    {}, {"choices": []}, {"choices": [None]}, {"choices": [{"message": None}]},
    completion(""), completion("  "), completion("x" * 16001), completion(None),
    completion("truncated", "length"), completion("blocked", "content_filter"),
    completion("tool call", "tool_calls"),
])
def test_incomplete_or_unsupported_replies_do_not_become_coaching_answers(body):
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=body))) as client:
        adapter = OpenAICompatibleProvider(live_settings(), client=client)
        with pytest.raises(ProviderError, match="incomplete or unsupported"):
            adapter.generate(instructions="Fitness", messages=[])


def test_non_json_response_is_a_safe_error():
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, text="secret provider error"))) as client:
        adapter = OpenAICompatibleProvider(live_settings(), client=client)
        with pytest.raises(ProviderError) as error:
            adapter.generate(instructions="Fitness", messages=[])
    assert "secret provider error" not in str(error.value)


@pytest.mark.parametrize("error_type", [httpx.ConnectError, httpx.ReadTimeout])
def test_connection_errors_are_sanitized_without_retry(error_type):
    calls = []

    def handler(request):
        calls.append(request)
        raise error_type("private-test-key and user data", request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        adapter = OpenAICompatibleProvider(live_settings(), client=client)
        with pytest.raises(ProviderError) as error:
            adapter.generate(instructions="Fitness", messages=[])
    assert len(calls) == 1
    assert "private-test-key" not in str(error.value)
    assert "No automatic retry" in str(error.value)
