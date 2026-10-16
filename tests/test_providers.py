import json

import httpx
import pytest

from openfitkit.providers import DemoProvider, OpenRouterProvider, ProviderError, build_provider
from openfitkit.settings import Settings


def live_settings():
    return Settings(provider="openrouter", model="example/model:latest", api_key="private-test-key")


def completion(answer="A manageable first step.", finish_reason="stop"):
    return {"choices": [{"finish_reason": finish_reason, "message": {"role": "assistant", "content": answer}}]}


def test_demo_is_static_offline_even_when_keys_exist(monkeypatch):
    monkeypatch.delenv("OPENFITKIT_PROVIDER", raising=False)
    monkeypatch.setenv("OPENFITKIT_API_KEY", "private-test-key")
    monkeypatch.setenv("OPENROUTER_API_KEY", "private-router-key")
    monkeypatch.setattr(httpx.Client, "post", lambda *args, **kwargs: pytest.fail("Unexpected network request"))
    provider = build_provider(Settings.from_env())
    assert isinstance(provider, DemoProvider)
    answer = provider.generate(instructions="Be helpful", messages=[{"role": "user", "content": "Build a plan"}])
    assert "fixed demonstration" in answer
    assert "not personalized coaching" in answer
    assert "No AI request was sent" in answer
    assert provider.generate(instructions="Different", messages=[]) == answer


def test_live_payload_uses_only_openrouter_with_one_request_and_output_limit():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=completion())

    with httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
        adapter = OpenRouterProvider(live_settings(), client=client)
        answer = adapter.generate(instructions="Fitness only", messages=[{"role": "user", "content": "Hello"}])
    assert answer == "A manageable first step."
    assert adapter.name == "openrouter"
    assert len(calls) == 1
    request = calls[0]
    assert str(request.url) == "https://openrouter.ai/api/v1/chat/completions"
    assert request.headers["Authorization"] == "Bearer private-test-key"
    payload = json.loads(request.content)
    assert payload["model"] == "example/model:latest"
    assert payload["messages"] == [{"role": "system", "content": "Fitness only"}, {"role": "user", "content": "Hello"}]
    assert payload["max_tokens"] == 1200
    assert set(payload) == {"model", "messages", "max_tokens"}
    assert request.extensions["timeout"]["read"] == 60


def test_build_provider_selects_openrouter_only():
    assert isinstance(build_provider(live_settings()), OpenRouterProvider)


@pytest.mark.parametrize("standard_key, expected_key", [
    ("private-router-key", "private-router-key"),
    ("", "private-legacy-key"),
])
def test_selected_environment_key_is_used_only_for_gateway_request(monkeypatch, standard_key, expected_key):
    monkeypatch.setenv("OPENFITKIT_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENFITKIT_MODEL", "vendor/model:free")
    monkeypatch.setenv("OPENROUTER_API_KEY", standard_key)
    monkeypatch.setenv("OPENFITKIT_API_KEY", "private-legacy-key")
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=completion())

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        adapter = OpenRouterProvider(Settings.from_env(), client=client)
        adapter.generate(instructions="Fitness", messages=[])
    assert len(calls) == 1
    assert str(calls[0].url) == "https://openrouter.ai/api/v1/chat/completions"
    assert calls[0].headers["Authorization"] == f"Bearer {expected_key}"
    assert json.loads(calls[0].content)["model"] == "vendor/model:free"


def test_old_direct_provider_never_sends_a_request(monkeypatch):
    monkeypatch.setenv("OPENFITKIT_PROVIDER", "openai")
    monkeypatch.setenv("OPENFITKIT_MODEL", "old-model")
    monkeypatch.setenv("OPENFITKIT_API_KEY", "private-old-key")
    monkeypatch.setattr(httpx.Client, "post", lambda *args, **kwargs: pytest.fail("Unexpected direct API request"))
    with pytest.raises(ValueError, match="OPENFITKIT_PROVIDER=openrouter"):
        build_provider(Settings.from_env())


@pytest.mark.parametrize("model", ["", "bare-model", "https://untrusted.example/model"])
def test_missing_or_invalid_model_fails_before_requests(monkeypatch, model):
    monkeypatch.setattr(httpx.Client, "post", lambda *args, **kwargs: pytest.fail("Unexpected network request"))
    with pytest.raises(ValueError, match="OPENFITKIT_MODEL"):
        build_provider(Settings(provider="openrouter", model=model, api_key="test"))


@pytest.mark.parametrize("key", ["", "  ", "private-key\ninvalid", "private-key\u00e9"])
def test_missing_or_invalid_key_fails_before_requests_without_exposing_it(monkeypatch, key):
    monkeypatch.setattr(httpx.Client, "post", lambda *args, **kwargs: pytest.fail("Unexpected network request"))
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY") as error:
        build_provider(Settings(provider="openrouter", model="vendor/model", api_key=key))
    if key.strip():
        assert key not in str(error.value)


def test_live_adapter_rejects_demo_configuration():
    with pytest.raises(ValueError, match="OPENFITKIT_PROVIDER=openrouter"):
        OpenRouterProvider(Settings())


def test_owned_http_client_preserves_tls_timeout_and_no_redirects(monkeypatch):
    real_client = httpx.Client
    configuration = []
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=completion())

    def factory(**kwargs):
        configuration.append(kwargs)
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(httpx, "Client", factory)
    assert build_provider(live_settings()).generate(instructions="Fitness", messages=[]) == "A manageable first step."
    assert configuration == [{"timeout": 60, "follow_redirects": False, "verify": True}]
    assert len(calls) == 1


@pytest.mark.parametrize("status", [301, 401, 403, 429, 500])
def test_http_failures_are_safe_and_never_retry_or_follow_redirects(status):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, text="private-test-key and sensitive athlete content", headers={"Location": "https://untrusted.example"})

    with httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
        adapter = OpenRouterProvider(live_settings(), client=client)
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
        adapter = OpenRouterProvider(live_settings(), client=client)
        with pytest.raises(ProviderError, match="incomplete or unsupported"):
            adapter.generate(instructions="Fitness", messages=[])


def test_non_json_response_is_a_safe_error():
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, text="secret provider error"))) as client:
        adapter = OpenRouterProvider(live_settings(), client=client)
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
        adapter = OpenRouterProvider(live_settings(), client=client)
        with pytest.raises(ProviderError) as error:
            adapter.generate(instructions="Fitness", messages=[])
    assert len(calls) == 1
    assert "private-test-key" not in str(error.value)
    assert "No automatic retry" in str(error.value)
