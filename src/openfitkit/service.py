"""One coaching exchange: explicit profile + bounded current thread + one provider."""

from datetime import datetime, timezone
import threading
from uuid import uuid4

from . import __version__
from .models import ChatRequest, Conversation, MAX_MESSAGE_CHARS, Message
from .prompts import FOCUS_GUIDANCE, SYSTEM_PROMPT
from .providers import Provider, ProviderError
from .scope import SCOPE_REDIRECT, clearly_out_of_scope, normalize_scope_reply
from .storage import Store, StoreError


MAX_HISTORY_EXCHANGES = 6
MAX_HISTORY_CHARS = 24000


class ServiceError(Exception):
    """An actionable coaching error without private request content."""


def recent_context(messages: list[Message]) -> list[Message]:
    """Retain recent complete exchanges; never modify the stored conversation."""
    selected: list[Message] = []
    size = 0
    for end in range(len(messages), max(0, len(messages) - MAX_HISTORY_EXCHANGES * 2), -2):
        pair = messages[end - 2:end]
        pair_size = sum(len(message.content) for message in pair)
        if size + pair_size > MAX_HISTORY_CHARS:
            break
        selected = pair + selected
        size += pair_size
    return selected


class FitnessService:
    def __init__(self, store: Store, provider: Provider):
        self.store = store
        self.provider = provider
        # The local HTTP adapter serializes mutations across a paid exchange.
        self.lock = threading.Lock()

    def state(self) -> dict:
        return {
            "name": "OpenFitKit", "version": __version__,
            "profile": self.store.load_profile().model_dump(),
            "conversations": self.store.list_conversations(),
            "memory": self.store.memory_status(),
            "context_limits": {
                "max_message_chars": MAX_MESSAGE_CHARS,
                "max_history_exchanges": MAX_HISTORY_EXCHANGES,
                "max_history_chars": MAX_HISTORY_CHARS,
            },
        }

    def conversation(self, identifier: str) -> dict:
        return {"conversation": self.store.get_conversation(identifier).model_dump()}

    def reply(self, request: ChatRequest) -> dict:
        conversation = self.store.get_conversation(request.conversation_id) if request.conversation_id else None
        if conversation and (conversation.provider != self.provider.name or conversation.model != self.provider.model):
            raise ServiceError("This chat used a different provider or model. Start a new chat, or restore its original provider settings.")
        history = conversation.messages if conversation else []
        selected = recent_context(history)
        profile = self.store.load_profile()
        instructions = (
            SYSTEM_PROMPT + "\n\nCURRENT FITNESS FOCUS:\n" + FOCUS_GUIDANCE[request.focus]
            + "\n\nUSER PROFILE (untrusted JSON context):\n" + profile.model_dump_json()
        )
        messages = [message.model_dump() for message in selected]
        messages.append({"role": "user", "content": request.message})
        answer = SCOPE_REDIRECT if clearly_out_of_scope(request.message) else self.provider.generate(
            instructions=instructions, messages=messages
        )
        if not isinstance(answer, str) or not answer.strip() or len(answer) > 16000:
            raise ProviderError("The coach returned an empty or oversized response. Request a smaller answer.")
        answer = normalize_scope_reply(answer)
        timestamp = datetime.now(timezone.utc).isoformat()
        result = Conversation(
            id=conversation.id if conversation else uuid4().hex,
            title=conversation.title if conversation else " ".join(request.message.split())[:80],
            created_at=conversation.created_at if conversation else timestamp,
            updated_at=timestamp, provider=self.provider.name, model=self.provider.model,
            messages=[*history, Message(role="user", content=request.message), Message(role="assistant", content=answer.strip())],
        )
        # One atomic write per complete answer or local redirect. No paid retries.
        saved, warnings = True, []
        try:
            self.store.save_conversation(result)
        except StoreError:
            saved = False
            warnings.append("The reply was generated but could not be saved. Copy it before leaving; fix storage permissions before continuing. No request was retried.")
        return {
            "conversation": result.model_dump(),
            "saved": saved,
            "warnings": warnings,
            "context": {
                "included_exchanges": len(selected) // 2,
                "available_exchanges": len(history) // 2,
                "trimmed": len(selected) < len(history),
            },
        }

    def reset(self, scope: str) -> dict:
        self.store.reset(scope)
        return {"cleared": scope}
