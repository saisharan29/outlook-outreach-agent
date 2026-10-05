"""Shared shapes: what the owner asked, what the agent must ask back, what it reports."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CompanyRequest:
    name: str
    city: str = ""
    website: str = ""
    contact_name: str = ""
    email_type: str = ""            # "preview" | "quote" | "" (then the agent asks, FR-04)
    language: str = ""              # "fr" | "en" | "" (then from the country)
    owner_email: str = ""           # an address the owner typed (phase 1, FR-13 exception)
    confirm_duplicate: bool = False
    chosen_candidate: int | None = None
    chosen_file: str = ""
    force_refresh: bool = False

    @property
    def label(self) -> str:
        return f"{self.name} ({self.city})" if self.city else self.name


@dataclass
class Intent:
    kind: str                       # "draft" | "do_not_contact" | "answer" | "help" | "status" | "unknown"
    companies: list[CompanyRequest] = field(default_factory=list)
    email_type: str = ""
    language: str = ""
    raw: str = ""
    answer: str = ""                # the owner's reply to a pending question
    notes: list[str] = field(default_factory=list)
    parser: str = "regex"


@dataclass
class Question:
    kind: str                       # "choose_company" | "choose_file" | "confirm_duplicate" | "email_type" | "choose_email"
    text: str
    options: list[str]
    request: CompanyRequest
    details: list[str] = field(default_factory=list)


@dataclass
class CompanyReport:
    request: CompanyRequest
    status: str = "no_draft"        # "draft_created" | "question" | "no_draft" | "refused" | "failed"
    company: dict | None = None
    email: dict | None = None
    phone: dict | None = None
    whatsapp: dict | None = None
    file: dict | None = None
    draft: dict | None = None
    sources: list[str] = field(default_factory=list)
    attention: list[str] = field(default_factory=list)
    question: Question | None = None
    message: str = ""


@dataclass
class Session:
    pending: list[Question] = field(default_factory=list)
    history: list[dict] = field(default_factory=list)      # AGENT_MODE=agent conversation
    reports: list[CompanyReport] = field(default_factory=list)
    messages: list[dict] = field(default_factory=list)     # what the chat page shows after a reload
