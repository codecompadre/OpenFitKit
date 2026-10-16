"""Coaching context and persistence behavior without a network connection."""

from copy import deepcopy

import pytest

from openfitkit.models import ChatRequest, Conversation, Message, Profile
from openfitkit.providers import ProviderError
from openfitkit.service import FitnessService, ServiceError, recent_context
from openfitkit.storage import Store, StoreError


class RecordingProvider:
    name = "test-provider"
    model = "test-model"

    def __init__(self, answer="A manageable next step.", failure=None):
        self.answer = answer
        self.failure = failure
        self.calls = []

    def generate(self, *, instructions, messages):
        self.calls.append((instructions, deepcopy(messages)))
        if self.failure is not None:
            raise self.failure
        return self.answer


def conversation(identifier="a" * 32, exchanges=1, *, provider="test-provider", model="test-model"):
    return Conversation(
        id=identifier,
        title="A saved conversation",
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
        provider=provider,
        model=model,
        messages=[
            message
            for number in range(exchanges)
            for message in (
                Message(role="user", content=f"Saved question {number}"),
                Message(role="assistant", content=f"Saved response {number}"),
            )
        ],
    )


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "data")


def test_new_chat_uses_explicit_profile_and_no_other_conversations(store):
    profile = Profile(name="Sam", goals="Walk regularly", limitations="Avoid jumping")
    store.save_profile(profile)
    old = conversation()
    old.messages[0].content = "PRIVATE OLD THREAD MARKER"
    store.save_conversation(old)
    provider = RecordingProvider()

    result = FitnessService(store, provider).reply(ChatRequest(message="Help me start a walking habit"))

    assert len(provider.calls) == 1
    instructions, messages = provider.calls[0]
    assert profile.model_dump_json() in instructions
    assert messages == [{"role": "user", "content": "Help me start a walking habit"}]
    assert "PRIVATE OLD THREAD MARKER" not in instructions
    assert "PRIVATE OLD THREAD MARKER" not in str(messages)
    assert result["conversation"]["id"] != old.id
    assert result["context"] == {"included_exchanges": 0, "available_exchanges": 0, "trimmed": False}
    assert store.memory_status() == {"conversations": 2, "messages": 4}
    assert store.get_conversation(old.id) == old


def test_followup_uses_only_selected_thread_and_current_profile(store):
    first, unrelated = conversation(), conversation("b" * 32)
    unrelated.messages[0].content = "UNRELATED THREAD"
    store.save_conversation(first)
    store.save_conversation(unrelated)
    store.save_profile(Profile(goals="Build a sleep routine"))
    provider = RecordingProvider(answer="  Keep the same bedtime this week.  ")

    result = FitnessService(store, provider).reply(ChatRequest(conversation_id=first.id, message="What next?"))

    assert len(provider.calls) == 1
    instructions, messages = provider.calls[0]
    assert "Build a sleep routine" in instructions
    assert messages == [message.model_dump() for message in first.messages] + [{"role": "user", "content": "What next?"}]
    assert "UNRELATED THREAD" not in str(provider.calls)
    saved = store.get_conversation(first.id)
    assert saved.created_at == first.created_at
    assert saved.title == first.title
    assert saved.messages[-1].content == "Keep the same bedtime this week."
    assert saved.model_dump() == result["conversation"]
    assert store.get_conversation(unrelated.id) == unrelated


def test_history_is_bounded_for_provider_but_preserved_in_storage(store):
    original = conversation(exchanges=9)
    store.save_conversation(original)
    provider = RecordingProvider()

    result = FitnessService(store, provider).reply(ChatRequest(conversation_id=original.id, message="Keep going"))

    assert len(provider.calls) == 1
    assert provider.calls[0][1] == [message.model_dump() for message in original.messages[-12:]] + [
        {"role": "user", "content": "Keep going"}
    ]
    assert result["context"] == {"included_exchanges": 6, "available_exchanges": 9, "trimmed": True}
    saved = store.get_conversation(original.id)
    assert saved.messages[:-2] == original.messages
    assert len(saved.messages) == 20


def test_context_character_budget_keeps_recent_complete_pairs(store):
    original = conversation(exchanges=6)
    for number, message in enumerate(original.messages):
        message.content = str(number) + "x" * (3000 - len(str(number)))
    store.save_conversation(original)
    provider = RecordingProvider()

    result = FitnessService(store, provider).reply(ChatRequest(conversation_id=original.id, message="Continue"))

    sent_history = provider.calls[0][1][:-1]
    assert sent_history == [message.model_dump() for message in original.messages[-8:]]
    assert sum(len(message["content"]) for message in sent_history) == 24000
    assert result["context"] == {"included_exchanges": 4, "available_exchanges": 6, "trimmed": True}
    assert store.get_conversation(original.id).messages[:-2] == original.messages


def test_recent_context_never_splits_or_skips_a_recent_exchange():
    history = [
        Message(role="user", content="old"), Message(role="assistant", content="old answer"),
        Message(role="user", content="u" * 12000), Message(role="assistant", content="a" * 12001),
    ]
    original = deepcopy(history)

    assert recent_context(history) == []
    assert history == original
    assert recent_context([]) == []


@pytest.mark.parametrize("existing", [False, True])
def test_failed_generation_never_saves_a_partial_exchange(store, existing):
    original = conversation()
    if existing:
        store.save_conversation(original)
    before = store.memory_status()
    provider = RecordingProvider(failure=ProviderError("Simulated provider failure"))
    service = FitnessService(store, provider)

    with pytest.raises(ProviderError, match="Simulated provider failure"):
        service.reply(ChatRequest(conversation_id=original.id if existing else None, message="A new question"))

    assert len(provider.calls) == 1
    assert store.memory_status() == before
    if existing:
        assert store.get_conversation(original.id) == original


@pytest.mark.parametrize("answer", ["", "   ", None, "x" * 16001])
def test_invalid_provider_response_does_not_create_history(store, answer):
    provider = RecordingProvider(answer=answer)

    with pytest.raises(ProviderError):
        FitnessService(store, provider).reply(ChatRequest(message="Suggest an easy walk"))

    assert len(provider.calls) == 1
    assert store.memory_status() == {"conversations": 0, "messages": 0}


@pytest.mark.parametrize("changed", [{"provider": "other-provider"}, {"model": "other-model"}])
def test_provider_or_model_mismatch_is_rejected_before_paid_call(store, changed):
    original = conversation(**changed)
    store.save_conversation(original)
    provider = RecordingProvider()

    with pytest.raises(ServiceError, match="different provider or model"):
        FitnessService(store, provider).reply(ChatRequest(conversation_id=original.id, message="Continue"))

    assert provider.calls == []
    assert store.get_conversation(original.id) == original


def test_save_happens_only_after_a_complete_provider_answer(store, monkeypatch):
    provider = RecordingProvider()
    original_save = store.save_conversation
    observed = []

    def check_complete(conversation):
        assert len(provider.calls) == 1
        assert [(message.role, message.content) for message in conversation.messages] == [
            ("user", "A small step"), ("assistant", provider.answer)
        ]
        observed.append(conversation.id)
        original_save(conversation)

    monkeypatch.setattr(store, "save_conversation", check_complete)
    result = FitnessService(store, provider).reply(ChatRequest(message="A small step"))

    assert observed == [result["conversation"]["id"]]


@pytest.mark.parametrize("existing", [False, True])
def test_save_failure_returns_generated_answer_without_paid_retry(store, monkeypatch, existing):
    provider = RecordingProvider(answer="Keep this answer available even if storage fails.")
    original = conversation()
    if existing:
        store.save_conversation(original)
    before = store.memory_status()

    def unavailable(_conversation):
        raise StoreError("Simulated disk failure")

    monkeypatch.setattr(store, "save_conversation", unavailable)
    result = FitnessService(store, provider).reply(ChatRequest(
        conversation_id=original.id if existing else None, message="Help me build a habit"
    ))

    assert len(provider.calls) == 1
    assert result["saved"] is False
    assert result["warnings"] and all(isinstance(warning, str) for warning in result["warnings"])
    assert result["conversation"]["messages"][-1]["content"] == provider.answer
    assert result["context"]["included_exchanges"] == (1 if existing else 0)
    assert store.memory_status() == before
    if existing:
        assert store.get_conversation(original.id) == original


def test_service_reset_scopes_and_reported_memory(store):
    profile = Profile(name="Alex", goals="Move each day")
    store.save_profile(profile)
    store.save_conversation(conversation())
    service = FitnessService(store, RecordingProvider())
    assert service.state()["memory"] == {"conversations": 1, "messages": 2}

    assert service.reset("history") == {"cleared": "history"}
    assert service.state()["memory"] == {"conversations": 0, "messages": 0}
    assert service.state()["profile"] == profile.model_dump()
    assert service.reset("all") == {"cleared": "all"}
    assert service.state()["profile"] == Profile().model_dump()
