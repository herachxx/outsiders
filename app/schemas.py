from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Language = Literal['ru', 'kk', 'uz', 'en', 'es', 'pt', 'lat', 'und']
Category = Literal['complaint.insult', 'complaint.cheat', 'complaint.dm', 'complaint.scam',
                   'complaint.rmt_ads', 'complaint.admin', 'complaint.other', 'complaint.invalid',
                   'report.question', 'report.help', 'report.complaint', 'report.account',
                   'report.payment', 'report.offtopic']


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class Message(StrictModel):
    role: Literal["player", "reported_player", "admin"]
    text: str = Field(max_length=20000)
    ts: str | None = None
    attachments: int = Field(default=0, ge=0)


class TriageRequest(StrictModel):
    kind: Literal["complaint", "report"]
    messages: list[Message] = Field(min_length=1, max_length=100)
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


class Citation(StrictModel):
    section_id: int
    ref: str = Field(min_length=1)
    rules_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    excerpt: str = Field(min_length=1)


class Extracted(StrictModel):
    nickname: str | None
    rule_refs: list[str]
    has_evidence: bool
    server: str | None = None
    claims: list[str]


class SubmissionExtracted(StrictModel):
    """The `extracted` object exactly as in the case PDF (no internal claims)."""
    nickname: str | None
    rule_refs: list[str]
    has_evidence: bool
    server: str | None = None


class Draft(StrictModel):
    lang: Language
    text: str
    cited: list[Citation]


class TriageResponse(StrictModel):
    lang: Language
    category: Category
    priority: Literal['p0', 'p1', 'p2', 'p3']
    is_spam_or_duplicate: bool
    extracted: Extracted
    draft_reply: Draft
    needs_human: bool
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    reasons: list[str]


class SubmissionDraft(StrictModel):
    lang: Language
    text: str
    cited: list[str]


class SubmissionResponse(TriageResponse):
    extracted: SubmissionExtracted
    draft_reply: SubmissionDraft
