"""Durable local data, transactional resets, and bounded record identity."""

import os
import sqlite3
import stat

import pytest
from pydantic import ValidationError

from openfitkit.models import Conversation, Message, Profile
from openfitkit.storage import Store, StoreError


def make_conversation(identifier="c" * 32, *, updated="2026-01-01T00:00:00+00:00"):
    return Conversation(
        id=identifier, title="A walking habit", provider="demo", model="offline-example",
        created_at="2026-01-01T00:00:00+00:00", updated_at=updated,
        messages=[Message(role="user", content="How can I start?"), Message(role="assistant", content="Try a short walk.")],
    )


def test_new_store_instance_reads_profile_and_complete_conversations(tmp_path):
    directory = tmp_path / "data"
    first = Store(directory)
    profile = Profile(name="Taylor", goals="More energy", days_per_week=3)
    conversation = make_conversation()
    first.save_profile(profile)
    first.save_conversation(conversation)

    reopened = Store(directory)
    assert reopened.load_profile() == profile
    assert reopened.get_conversation(conversation.id) == conversation
    assert reopened.memory_status() == {"conversations": 1, "messages": 2}
    summary = reopened.list_conversations()
    assert len(summary) == 1 and summary[0]["id"] == conversation.id
    assert "messages" not in summary[0]


def test_saving_followup_updates_existing_thread_and_memory_count(tmp_path):
    store = Store(tmp_path)
    conversation = make_conversation()
    store.save_conversation(conversation)
    conversation.messages.extend([
        Message(role="user", content="And tomorrow?"), Message(role="assistant", content="See how you recover."),
    ])
    conversation.updated_at = "2026-01-02T00:00:00+00:00"
    store.save_conversation(conversation)

    assert store.get_conversation(conversation.id) == conversation
    assert store.memory_status() == {"conversations": 1, "messages": 4}
    assert len(store.list_conversations()) == 1


def test_history_lists_newest_update_first(tmp_path):
    store = Store(tmp_path)
    older = make_conversation("a" * 32)
    newer = make_conversation("b" * 32, updated="2026-01-03T00:00:00+00:00")
    store.save_conversation(newer)
    store.save_conversation(older)

    assert [entry["id"] for entry in store.list_conversations()] == [newer.id, older.id]


def test_history_reset_preserves_profile_and_all_reset_removes_it(tmp_path):
    store = Store(tmp_path)
    profile = Profile(name="Casey", limitations="Avoid jumping")
    store.save_profile(profile)
    store.save_conversation(make_conversation())

    store.reset("history")
    assert store.list_conversations() == []
    assert store.load_profile() == profile

    store.save_conversation(make_conversation())
    store.reset("all")
    reopened = Store(tmp_path)
    assert reopened.load_profile() == Profile()
    assert reopened.memory_status() == {"conversations": 0, "messages": 0}


def test_all_reset_rolls_back_history_if_profile_delete_fails(tmp_path):
    store = Store(tmp_path)
    profile = Profile(goals="A regular routine")
    conversation = make_conversation()
    store.save_profile(profile)
    store.save_conversation(conversation)
    with sqlite3.connect(store.path) as connection:
        connection.execute("""
            CREATE TRIGGER simulate_failed_profile_delete BEFORE DELETE ON profile
            BEGIN SELECT RAISE(ABORT, 'simulated disk failure'); END
        """)

    with pytest.raises(StoreError):
        store.reset("all")

    assert store.load_profile() == profile
    assert store.get_conversation(conversation.id) == conversation
    assert store.memory_status() == {"conversations": 1, "messages": 2}


def test_invalid_reset_does_not_remove_data(tmp_path):
    store = Store(tmp_path)
    conversation = make_conversation()
    store.save_conversation(conversation)

    with pytest.raises(StoreError):
        store.reset("everything")

    assert store.get_conversation(conversation.id) == conversation


@pytest.mark.skipif(os.name != "posix", reason="POSIX file mode behavior")
def test_new_data_directory_and_database_are_private(tmp_path):
    store = Store(tmp_path / "private-data")
    store.load_profile()

    assert stat.S_IMODE(store.path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(store.path.stat().st_mode) == 0o600


@pytest.mark.parametrize("identifier", [
    "../outside.txt", "../../another.sqlite3", "/tmp/other.sqlite3", "a" * 31,
    "A" * 32, "g" * 32, "a" * 32 + "' OR 1=1 --", None,
])
def test_untrusted_conversation_id_cannot_resolve_files_or_create_database(tmp_path, identifier):
    outside = tmp_path / "outside.txt"
    outside.write_text("private unrelated content", encoding="utf-8")
    store = Store(tmp_path / "not-created")

    with pytest.raises(StoreError, match="Choose a conversation listed in history"):
        store.get_conversation(identifier)

    assert not store.path.exists()
    assert outside.read_text(encoding="utf-8") == "private unrelated content"


def test_unknown_valid_identifier_has_actionable_error(tmp_path):
    store = Store(tmp_path)

    with pytest.raises(StoreError, match="Conversation not found"):
        store.get_conversation("f" * 32)


def test_database_symlink_is_rejected_without_modifying_target(tmp_path):
    target = tmp_path / "unrelated-file"
    target.write_text("leave this file unchanged", encoding="utf-8")
    directory = tmp_path / "data"
    directory.mkdir()
    (directory / "openfitkit.sqlite3").symlink_to(target)

    with pytest.raises(StoreError, match="regular database file"):
        Store(directory).load_profile()

    assert target.read_text(encoding="utf-8") == "leave this file unchanged"


def test_corrupt_database_returns_safe_storage_error(tmp_path):
    store = Store(tmp_path)
    store.path.write_bytes(b"private text that is not a SQLite database")

    with pytest.raises(StoreError) as caught:
        store.load_profile()

    assert "private text" not in str(caught.value)
    assert "data directory" in str(caught.value)


@pytest.mark.parametrize("messages", [
    [],
    [Message(role="user", content="Question without response")],
    [Message(role="assistant", content="Wrong first role"), Message(role="user", content="Wrong second role")],
    [Message(role="user", content="Question"), Message(role="user", content="Not an answer")],
    [Message(role="user", content="Question"), Message(role="assistant", content="Answer"), Message(role="user", content="Incomplete")],
])
def test_conversation_model_rejects_incomplete_or_misordered_exchanges(messages):
    data = make_conversation().model_dump()
    data["messages"] = messages

    with pytest.raises(ValidationError):
        Conversation.model_validate(data)
