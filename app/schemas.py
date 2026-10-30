from typing import Literal

from pydantic import BaseModel, Field, model_validator


class Message(BaseModel):
    role: Literal["player", "reported_player", "admin"]
    text: str = Field(max_length=20000)
    ts: str | None = None


class TriageRequest(BaseModel):
    kind: Literal["complaint", "report"]
    messages: list[Message] = Field(min_length=1)
    region: str | None = None
    server_lang: str | None = None
    rule_refs_raw: str | None = None
    images_count: int = Field(default=0, ge=0)
    reporter_hash: str | None = None
    reported_hash: str | None = None
    reported_nick: str | None = None

    @model_validator(mode="after")
    def require_player(self):
        if not any(message.role == "player" for message in self.messages):
            raise ValueError("At least one player message is required")
        return self
