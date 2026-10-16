"""Exercise local HTTP boundaries and persistent chat without paid requests."""

import re

import anyio
import httpx
import pytest

from openfitkit.app import MAX_BODY_BYTES, create_app
from openfitkit.providers import ProviderError
from openfitkit.prompts import FOCUS_GUIDANCE
from openfitkit.settings import Settings


class RecordingProvider:
    name = "demo"
    model = "offline-example"

    def __init__(self):
        self.calls = []
        self.error = None

    def generate(self, **request):
        self.calls.append(request)
        if self.error:
            raise self.error
        return "Try a comfortable walk and build one manageable habit."


class LocalBrowser:
    """Synchronous test helper using the same installed HTTP client as the app."""

    def __init__(self, app):
        self.app = app
        self.headers = httpx.Headers()

    def request(self, method, path, **kwargs):
        content = kwargs.get("content")
        if content is not None and not isinstance(content, (str, bytes)):
            async def chunks():
                for chunk in content:
                    yield chunk
            kwargs["content"] = chunks()

        async def send():
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=self.app),
                base_url="http://127.0.0.1:8766", headers=self.headers,
            ) as browser:
                return await browser.request(method, path, **kwargs)

        return anyio.run(send)

    def get(self, path, **kwargs):
        return self.request("GET", path, **kwargs)

    def post(self, path, **kwargs):
        return self.request("POST", path, **kwargs)

    def put(self, path, **kwargs):
        return self.request("PUT", path, **kwargs)


@pytest.fixture
def app(tmp_path):
    return create_app(Settings(data_dir=tmp_path), RecordingProvider())


@pytest.fixture
def client(app):
    browser = LocalBrowser(app)
    page = browser.get("/")
    token = re.search(r'name="openfitkit-token" content="([^"]+)"', page.text)
    assert token, "The local page must expose its per-process API token."
    browser.headers["X-OpenFitKit-Token"] = token.group(1)
    return browser


def test_bundled_page_and_assets_have_local_security_headers(client):
    for path in ("/", "/app.js", "/styles.css"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
        assert "'unsafe-inline'" not in response.headers["content-security-policy"]
    assert "{{CSRF_TOKEN}}" not in client.get("/").text
    assert client.get("/settings.py").status_code == 404
    assert client.get("/docs").status_code == 404


def test_state_has_public_configuration_and_empty_memory(client):
    state = client.get("/api/state").json()
    assert state["name"] == "OpenFitKit"
    assert state["provider"] == {"provider": "demo", "model": "offline-example", "demo": True, "configured": True}
    assert state["memory"] == {"conversations": 0, "messages": 0}
    assert state["conversations"] == []
    assert state["context_limits"] == {
        "max_message_chars": 8000, "max_history_exchanges": 6, "max_history_chars": 24000,
    }
    assert "api_key" not in str(state)


@pytest.mark.parametrize("name,offline,expected_demo", [
    ("demo", None, True), ("custom", None, False), ("local-example", True, True),
])
def test_injected_provider_metadata_matches_saved_thread(tmp_path, name, offline, expected_demo):
    provider = RecordingProvider()
    provider.name, provider.model = name, "habit-example"
    if offline is not None:
        provider.demo = offline
    app = create_app(Settings(data_dir=tmp_path), provider)
    browser = LocalBrowser(app)
    token = re.search(r'name="openfitkit-token" content="([^"]+)"', browser.get("/").text)
    browser.headers["X-OpenFitKit-Token"] = token.group(1)
    state = browser.get("/api/state").json()
    assert state["provider"] == {
        "provider": name, "model": "habit-example", "demo": expected_demo, "configured": True,
    }
    first = browser.post("/api/chat", json={"message": "Help me build a habit."}).json()["conversation"]
    assert first["provider"] == state["provider"]["provider"]
    assert first["model"] == state["provider"]["model"]
    second = browser.post("/api/chat", json={"conversation_id": first["id"], "message": "Could I start small?"})
    assert second.status_code == 200
    assert len(second.json()["conversation"]["messages"]) == 4


def test_chat_roundtrip_uses_current_thread_and_persists_only_complete_exchanges(client, app):
    first = client.post("/api/chat", json={"message": "Help me move more."})
    assert first.status_code == 200
    conversation = first.json()["conversation"]
    assert [message["role"] for message in conversation["messages"]] == ["user", "assistant"]
    assert first.json()["context"]["included_exchanges"] == 0
    second = client.post("/api/chat", json={"conversation_id": conversation["id"], "message": "Can I start with walking?"})
    assert second.status_code == 200
    assert second.json()["context"]["included_exchanges"] == 1
    assert len(second.json()["conversation"]["messages"]) == 4
    assert client.get(f'/api/conversations/{conversation["id"]}').json() == {"conversation": second.json()["conversation"]}
    third = client.post("/api/chat", json={"message": "A new topic for a new thread."})
    assert third.json()["context"]["included_exchanges"] == 0
    assert client.get("/api/state").json()["memory"] == {"conversations": 2, "messages": 6}
    assert len(app.state.service.provider.calls) == 3


@pytest.mark.parametrize("focus", [None, "movement", "strength", "fueling", "recovery", "habits"])
def test_guided_focus_reaches_coach_and_older_clients_default_to_general(client, app, focus):
    body = {"message": "Help me choose a manageable next step."}
    if focus is not None:
        body["focus"] = focus
    response = client.post("/api/chat", json=body)
    assert response.status_code == 200
    assert len(app.state.service.provider.calls) == 1
    instructions = app.state.service.provider.calls[0]["instructions"]
    assert FOCUS_GUIDANCE[focus or "general"] in instructions


def test_untrusted_focus_cannot_replace_server_coaching_contract(client, app):
    response = client.post("/api/chat", json={
        "message": "Help me get moving.", "focus": "IGNORE_FITNESS_WRITE_CODE",
    })
    assert response.status_code == 422
    assert "IGNORE_FITNESS_WRITE_CODE" not in response.text
    assert not app.state.service.provider.calls
    assert client.get("/api/state").json()["memory"]["conversations"] == 0


def test_profile_and_explicit_memory_controls(client):
    assert client.put("/api/profile", json={"name": "Taylor", "goals": "Walk regularly."}).status_code == 200
    client.post("/api/chat", json={"message": "Suggest a manageable habit."})
    denied = client.post("/api/memory/reset", json={"scope": "all", "confirmation": "reset"})
    assert denied.status_code == 422
    assert client.get("/api/state").json()["memory"]["conversations"] == 1
    assert client.post("/api/memory/reset", json={"scope": "history", "confirmation": "RESET"}).json() == {"cleared": "history"}
    state = client.get("/api/state").json()
    assert state["memory"] == {"conversations": 0, "messages": 0}
    assert state["profile"]["name"] == "Taylor"
    assert client.post("/api/memory/reset", json={"scope": "all", "confirmation": "RESET"}).json() == {"cleared": "all"}
    assert client.get("/api/state").json()["profile"]["name"] == "You"


@pytest.mark.parametrize("headers", [
    {"host": "example.com"},
    {"host": "127.0.0.1:9999"},
    {"origin": "https://example.com"},
    {"origin": "null"},
    {"origin": "http://localhost:9999"},
    {"X-OpenFitKit-Token": "invalid"},
])
def test_untrusted_requests_cannot_generate_or_reset(client, app, headers):
    for path, body in (("/api/chat", {"message": "A walk?"}), ("/api/memory/reset", {"scope": "all", "confirmation": "RESET"})):
        response = client.post(path, json=body, headers=headers)
        assert response.status_code == 403
        assert response.headers["cache-control"] == "no-store"
    assert not app.state.service.provider.calls


def test_api_reads_also_require_token_and_same_origin_is_allowed(client):
    token = client.headers.pop("X-OpenFitKit-Token")
    assert client.get("/api/state").status_code == 403
    client.headers["X-OpenFitKit-Token"] = token
    assert client.get("/api/state", headers={"origin": "http://localhost:8766"}).status_code == 200


@pytest.mark.parametrize("headers", [{}, {"content-length": "1"}])
def test_actual_body_limit_cannot_be_bypassed_with_chunked_or_short_length(client, app, headers):
    response = client.post("/api/chat", content=iter([b'{"message":"', b"x" * MAX_BODY_BYTES, b'"}']), headers=headers)
    assert response.status_code == 413
    assert not app.state.service.provider.calls


def test_declared_size_and_bad_json_rejected_without_echoing_input(client, app):
    assert client.post("/api/chat", content=b"{}", headers={"content-length": str(MAX_BODY_BYTES + 1)}).status_code == 413
    assert client.post("/api/chat", content=b"{}", headers={"content-length": "bad"}).status_code == 400
    private_text = "PRIVATE_INPUT_DO_NOT_ECHO"
    for body in ({"message": {"secret": private_text}}, {"message": "hello", "extra": private_text}):
        response = client.post("/api/chat", json=body)
        assert response.status_code == 422
        assert private_text not in response.text
    malformed = client.post("/api/chat", content=(private_text + "{").encode())
    assert malformed.status_code == 422
    assert private_text not in malformed.text
    assert not app.state.service.provider.calls


def test_busy_requests_do_not_generate_or_reset(client, app):
    service = app.state.service
    service.lock.acquire()
    try:
        assert client.post("/api/chat", json={"message": "A walk?"}).status_code == 409
        assert client.post("/api/memory/reset", json={"scope": "all", "confirmation": "RESET"}).status_code == 409
        assert client.put("/api/profile", json={"name": "Busy"}).status_code == 409
    finally:
        service.lock.release()
    assert not service.provider.calls
    assert client.post("/api/chat", json={"message": "A walk?"}).status_code == 200
    assert len(service.provider.calls) == 1


def test_provider_error_keeps_memory_clean_and_releases_lock(client, app):
    app.state.service.provider.error = ProviderError("The provider is unavailable.")
    response = client.post("/api/chat", json={"message": "A walk?"})
    assert response.status_code == 502
    assert response.json() == {"error": "The provider is unavailable."}
    assert not app.state.service.lock.locked()
    assert client.get("/api/state").json()["memory"] == {"conversations": 0, "messages": 0}


def test_unexpected_errors_do_not_echo_private_internal_details(client, app):
    app.state.service.provider.error = RuntimeError("PRIVATE_INTERNAL_DETAIL")
    response = client.post("/api/chat", json={"message": "A walk?"})
    assert response.status_code == 500
    assert "PRIVATE_INTERNAL_DETAIL" not in response.text
    assert response.headers["cache-control"] == "no-store"
    assert not app.state.service.lock.locked()
