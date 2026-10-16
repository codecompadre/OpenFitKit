"""A single-user SQLite example; replace this boundary for another datastore."""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import sqlite3

from .models import Conversation, Profile


class StoreError(Exception):
    """A storage failure safe to show without private record contents."""


class Store:
    def __init__(self, data_dir: str | Path):
        self.path = Path(data_dir).expanduser() / "openfitkit.sqlite3"

    @contextmanager
    def _connection(self):
        connection = None
        try:
            self.path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
            if self.path.is_symlink():
                raise StoreError("Choose a data directory containing a regular database file.")
            try:
                descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                pass
            else:
                os.close(descriptor)
            connection = sqlite3.connect(self.path, timeout=5)
            connection.row_factory = sqlite3.Row
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS profile (
                    id INTEGER PRIMARY KEY CHECK(id = 1), data TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    provider TEXT NOT NULL, model TEXT NOT NULL,
                    messages TEXT NOT NULL, message_count INTEGER NOT NULL
                );
            """)
            with connection:
                yield connection
        except (sqlite3.Error, OSError, ValueError):
            raise StoreError("Cannot read or save local data. Check the data directory and its permissions.") from None
        finally:
            if connection is not None:
                connection.close()

    def load_profile(self) -> Profile:
        with self._connection() as connection:
            row = connection.execute("SELECT data FROM profile WHERE id = 1").fetchone()
            return Profile.model_validate_json(row["data"]) if row else Profile()

    def save_profile(self, profile: Profile) -> Profile:
        with self._connection() as connection:
            connection.execute(
                "INSERT INTO profile (id, data) VALUES (1, ?) ON CONFLICT(id) DO UPDATE SET data = excluded.data",
                (profile.model_dump_json(),),
            )
        return profile

    def list_conversations(self) -> list[dict]:
        with self._connection() as connection:
            return [dict(row) for row in connection.execute(
                "SELECT id, title, created_at, updated_at, provider, model FROM conversations ORDER BY updated_at DESC"
            )]

    def get_conversation(self, identifier: str) -> Conversation:
        if not isinstance(identifier, str) or not re.fullmatch(r"[a-f0-9]{32}", identifier):
            raise StoreError("Choose a conversation listed in history.")
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM conversations WHERE id = ?", (identifier,)).fetchone()
            if row is None:
                raise StoreError("Conversation not found. Refresh history or start a new chat.")
            data = dict(row)
            data.pop("message_count")
            data["messages"] = json.loads(data["messages"])
            return Conversation.model_validate(data)

    def save_conversation(self, conversation: Conversation) -> None:
        values = conversation.model_dump()
        values["message_count"] = len(values["messages"])
        values["messages"] = json.dumps(values["messages"], ensure_ascii=False)
        with self._connection() as connection:
            connection.execute("""
                INSERT INTO conversations (id, title, created_at, updated_at, provider, model, messages, message_count)
                VALUES (:id, :title, :created_at, :updated_at, :provider, :model, :messages, :message_count)
                ON CONFLICT(id) DO UPDATE SET updated_at = excluded.updated_at,
                    messages = excluded.messages, message_count = excluded.message_count
            """, values)

    def memory_status(self) -> dict:
        with self._connection() as connection:
            row = connection.execute("SELECT COUNT(*) AS conversations, COALESCE(SUM(message_count), 0) AS messages FROM conversations").fetchone()
            return dict(row)

    def reset(self, scope: str) -> None:
        if scope not in ("history", "all"):
            raise StoreError("Choose history or all for a memory reset.")
        with self._connection() as connection:
            connection.execute("DELETE FROM conversations")
            if scope == "all":
                connection.execute("DELETE FROM profile")
