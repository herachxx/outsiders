"""Source-backed observations, never proof that an allegation is true."""
from dataclasses import dataclass
from typing import Literal

from .schemas import TriageRequest


@dataclass(frozen=True)
class Fact:
    kind: Literal['claim', 'reported_player_statement', 'metadata']
    source: str
    value: str | int
    start: int | None = None
    end: int | None = None


def extract_facts(payload: dict | TriageRequest) -> list[Fact]:
    request = payload if isinstance(payload, TriageRequest) else TriageRequest.model_validate(payload)
    facts = [Fact('metadata', 'images_count', request.images_count)]
    for index, message in enumerate(request.messages):
        if message.role == 'admin':
            break
        if message.text.strip():
            kind = 'claim' if message.role == 'player' else 'reported_player_statement'
            start = len(message.text) - len(message.text.lstrip())
            end = len(message.text.rstrip())
            facts.append(Fact(kind, f'messages[{index}].text', message.text[start:end], start, end))
        if message.attachments:
            facts.append(Fact('metadata', f'messages[{index}].attachments', message.attachments))
    return facts
