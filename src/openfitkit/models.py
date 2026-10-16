"""Small domain models: extend these when your own app needs more context."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


MAX_MESSAGE_CHARS = 8000


class Profile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(default="You", max_length=80)
    goals: str = Field(default="", max_length=2000)
    experience: Literal["unspecified", "beginner", "intermediate", "experienced"] = "unspecified"
    days_per_week: int | None = Field(default=None, ge=1, le=7, strict=True)
    minutes_per_session: int | None = Field(default=None, ge=5, le=180, strict=True)
    equipment: str = Field(default="", max_length=2000)
    limitations: str = Field(default="", max_length=2000)
    dietary_preferences: str = Field(default="", max_length=2000)


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=24000)


class Conversation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-f0-9]{32}$")
    title: str
    created_at: str
    updated_at: str
    provider: str
    model: str
    messages: list[Message]

    @model_validator(mode="after")
    def complete_exchanges(self) -> "Conversation":
        if not self.messages or len(self.messages) % 2:
            raise ValueError("Conversations contain complete user and assistant exchanges.")
        for index, message in enumerate(self.messages):
            if message.role != ("user" if index % 2 == 0 else "assistant"):
                raise ValueError("Conversation messages must alternate user and assistant.")
        return self


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    focus: Literal["general", "movement", "strength", "fueling", "recovery", "habits"] = "general"
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)

    @field_validator("message")
    @classmethod
    def meaningful_text(cls, value: str) -> str:
        if not value.strip() or "\x00" in value:
            raise ValueError("Enter a fitness or healthy lifestyle message.")
        return value.strip()


class ResetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: Literal["history", "all"]
    confirmation: Literal["RESET"]
