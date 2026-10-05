"""Email templates (spec section 5). The owner writes them; the agent fills placeholders only.

Layout of the Templates folder (editable text files, changed without the developer):

    Templates/
      preview_fr.txt      preview_en.txt
      quote_fr.txt        quote_en.txt
      signature_fr.txt    signature_en.txt     (signature.txt as a fallback for both)

A template file starts with a "Subject:" line, a blank line, then the body.

Supported placeholders (FR-23): {{company_name}}, {{contact_name}}, {{greeting}}, {{city}},
{{preview_link}}, {{signature}}, {{agency_name}}. Any other {{placeholder}} left in the final
text makes the draft fail — no unfilled placeholder may remain.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

PLACEHOLDER = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")
LANGUAGES = ("fr", "en")
FRENCH_COUNTRIES = {"FR", "BE", "CH", "LU", "MC", "CA-QC"}

NEUTRAL_GREETING = {"fr": "Bonjour,", "en": "Hello,"}
NAMED_GREETING = {"fr": "Bonjour {name},", "en": "Hello {name},"}


class TemplateError(ValueError):
    pass


@dataclass
class Template:
    email_type: str
    language: str
    subject: str
    body: str
    path: Path | None = None
    placeholders: set[str] = field(default_factory=set)


@dataclass
class RenderedEmail:
    subject: str
    body: str
    language: str
    template_file: str


def language_for_country(country: str | None, default: str = "fr") -> str:
    if not country:
        return default
    return "fr" if country.upper() in FRENCH_COUNTRIES else "en"


def parse_template(text: str, email_type: str, language: str, path: Path | None = None) -> Template:
    lines = text.replace("\r\n", "\n").split("\n")
    if not lines or not lines[0].lower().startswith("subject:"):
        raise TemplateError(f"Template {path or email_type} must start with a 'Subject:' line.")
    subject = lines[0].split(":", 1)[1].strip()
    body = "\n".join(lines[1:]).lstrip("\n").rstrip() + "\n"
    found = set(PLACEHOLDER.findall(subject)) | set(PLACEHOLDER.findall(body))
    return Template(email_type=email_type, language=language, subject=subject, body=body,
                    path=path, placeholders=found)


class TemplateStore:
    """Reads templates fresh from disk on every call, so an edit takes effect on the next draft."""

    def __init__(self, folder: Path):
        self.folder = Path(folder)

    def available(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for t in ("preview", "quote"):
            out[t] = [lang for lang in LANGUAGES if (self.folder / f"{t}_{lang}.txt").exists()]
        return out

    def load(self, email_type: str, language: str) -> Template:
        if email_type not in ("preview", "quote"):
            raise TemplateError(f"Unknown email type '{email_type}'.")
        path = self.folder / f"{email_type}_{language}.txt"
        if not path.exists():
            raise TemplateError(f"Template missing: {path.name} (expected in {self.folder}).")
        return parse_template(path.read_text(encoding="utf-8"), email_type, language, path)

    def signature(self, language: str) -> str:
        for name in (f"signature_{language}.txt", "signature.txt"):
            p = self.folder / name
            if p.exists():
                return p.read_text(encoding="utf-8").strip()
        return ""


def build_variables(*, company_name: str, language: str, contact_name: str | None = None,
                    city: str | None = None, preview_link: str | None = None,
                    signature: str = "", agency_name: str = "") -> dict[str, str]:
    greeting = (NAMED_GREETING[language].format(name=contact_name.strip())
                if contact_name and contact_name.strip() else NEUTRAL_GREETING[language])
    return {
        "company_name": company_name,
        "contact_name": contact_name.strip() if contact_name else "",
        "greeting": greeting,
        "city": city or "",
        "preview_link": preview_link or "",
        "signature": signature,
        "agency_name": agency_name,
    }


def render(template: Template, variables: dict[str, str]) -> RenderedEmail:
    """Fill placeholders. Empty optional values are an error only when the template uses them
    and nothing sensible exists — {{contact_name}} is the exception handled by {{greeting}}."""
    def sub(text: str) -> str:
        def repl(m: re.Match) -> str:
            key = m.group(1)
            if key not in variables:
                raise TemplateError(f"Unknown placeholder {{{{{key}}}}} in template {template.path or template.email_type}.")
            return variables[key]
        return PLACEHOLDER.sub(repl, text)

    subject = sub(template.subject)
    body = sub(template.body)
    leftover = PLACEHOLDER.findall(subject + body)
    if leftover:
        raise TemplateError(f"Unfilled placeholders remain: {', '.join(sorted(set(leftover)))}")
    # Required values the owner's template relies on must not be blank.
    for key in ("preview_link", "signature", "company_name"):
        if key in template.placeholders and not variables.get(key):
            raise TemplateError(f"Template uses {{{{{key}}}}} but no value is available.")
    return RenderedEmail(subject=subject.strip(), body=body, language=template.language,
                         template_file=template.path.name if template.path else template.email_type)
