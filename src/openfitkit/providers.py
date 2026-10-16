"""One replaceable provider boundary, with a deliberately offline default."""

from typing import Protocol

import httpx

from .settings import Settings


class ProviderError(Exception):
    """A safe error message that may be shown to the user."""


class Provider(Protocol):
    name: str
    model: str

    def generate(self, *, instructions: str, messages: list[dict[str, str]]) -> str: ...


class DemoProvider:
    name = "demo"
    model = "offline-example"

    def generate(self, *, instructions: str, messages: list[dict[str, str]]) -> str:
        return (
            "Offline example\n\n"
            "This is a fixed demonstration, not personalized coaching. No AI request was sent.\n\n"
            "A small starting point\n\n"
            "- Choose comfortable movement you enjoy, such as an easy walk. Start with a manageable duration.\n"
            "- Build a regular sleep routine and include water with meals.\n"
            "- Track one habit this week and adjust gradually as you learn what works for you.\n\n"
            "To build your own experience, customize the coaching instructions, profile fields, "
            "and interface. Explicitly configure a live provider when you want generated replies."
        )


class OpenAICompatibleProvider:
    """A minimal adapter for two fixed endpoints; no automatic paid retries."""

    ENDPOINTS = {
        "openai": "https://api.openai.com/v1/chat/completions",
        "openrouter": "https://openrouter.ai/api/v1/chat/completions",
    }

    def __init__(self, settings: Settings, *, client: httpx.Client | None = None):
        if settings.provider not in self.ENDPOINTS:
            raise ValueError("Choose openai or openrouter for the live provider.")
        if not settings.model or not settings.api_key.strip():
            raise ValueError("Live coaching requires OPENFITKIT_MODEL and OPENFITKIT_API_KEY.")
        self.name, self.model = settings.provider, settings.model
        self._api_key = settings.api_key
        self._client = client

    def generate(self, *, instructions: str, messages: list[dict[str, str]]) -> str:
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": instructions}, *messages],
            "max_completion_tokens" if self.name == "openai" else "max_tokens": 1200,
        }
        try:
            if self._client is not None:
                response = self._request(self._client, payload)
            else:
                with httpx.Client(timeout=60, follow_redirects=False) as client:
                    response = self._request(client, payload)
        except httpx.TimeoutException:
            raise ProviderError("The AI request timed out. No automatic retry was made.") from None
        except httpx.HTTPError:
            raise ProviderError("Could not connect to the AI provider. No automatic retry was made.") from None
        if response.status_code in {401, 403}:
            raise ProviderError("The AI provider rejected the credentials or model access.")
        if response.status_code == 429:
            raise ProviderError("The AI provider reported a usage or rate limit. Check your provider account.")
        if response.status_code != 200:
            raise ProviderError("The AI provider could not complete the request. Check your provider account and model.")
        try:
            choice = response.json()["choices"][0]
            answer = choice["message"]["content"]
            if choice.get("finish_reason") != "stop" or not isinstance(answer, str) or not answer.strip() or len(answer) > 16000:
                raise ValueError
            return answer.strip()
        except (ValueError, KeyError, IndexError, TypeError):
            raise ProviderError("The AI provider returned an incomplete or unsupported reply. No automatic retry was made.") from None

    def _request(self, client: httpx.Client, payload: dict) -> httpx.Response:
        return client.post(
            self.ENDPOINTS[self.name],
            headers={"Authorization": f"Bearer {self._api_key}"},
            json=payload,
            timeout=60,
            follow_redirects=False,
        )


def build_provider(settings: Settings) -> Provider:
    return DemoProvider() if settings.provider == "demo" else OpenAICompatibleProvider(settings)
