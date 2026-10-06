"""Email templates (spec section 5). The owner writes them; the agent fills placeholders only.

Layout of the Templates folder (editable files, changed without the developer):

    Templates/
      preview_fr.html   preview_de.html   preview_lb.html      (or .txt for plain-text emails)
      quote_fr.html     quote_de.html     quote_lb.html
      signature.html    (or signature_fr.html … per language; .txt for plain text)

A template file starts with a "Subject:" line, a blank line, then the body. An .html file is sent
as an HTML email (the owner's signature block with logo, links and colours); a .txt file as text.

Supported placeholders (FR-23): {{company_name}}, {{contact_name}}, {{greeting}}, {{city}},
{{preview_link}}, {{signature}}, {{agency_name}}. {{greeting}} follows the time of day
("Bonjour" / "Bonsoir"). Any other {{placeholder}} left in the final text makes the draft fail.
"""
from __future__ import annotations

import html as htmllib
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

PLACEHOLDER = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")
LANGUAGES = ("fr", "de", "lb", "en")
COUNTRY_LANGUAGE = {"FR": "fr", "BE": "fr", "LU": "fr", "MC": "fr", "CH": "fr", "DE": "de", "AT": "de",
                    "GB": "en", "IE": "en", "US": "en"}

# Greeting by time of day: morning/afternoon, then evening from EVENING_HOUR on.
EVENING_HOUR = 18
GREETINGS = {
    "fr": {"day": "Bonjour", "evening": "Bonsoir"},
    "de": {"day": "Guten Tag", "evening": "Guten Abend"},
    "lb": {"day": "Moien", "evening": "Gudden Owend"},
    "en": {"day": "Hello", "evening": "Good evening"},
}


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
    html: bool = False


@dataclass
class RenderedEmail:
    subject: str
    body: str
    language: str
    template_file: str
    html: bool = False

    @property
    def body_type(self) -> str:
        return "HTML" if self.html else "Text"


def language_for_country(country: str | None, default: str = "fr", allowed: list[str] | None = None) -> str:
    """The template language for a company's country, restricted to the languages the owner supports."""
    lang = COUNTRY_LANGUAGE.get((country or "").upper(), default) if country else default
    if allowed and lang not in allowed:
        return default if default in allowed else allowed[0]
    return lang


def greeting(language: str, contact_name: str = "", *, now: datetime | None = None,
             timezone: str = "Europe/Luxembourg") -> str:
    """"Bonjour," before 18:00 local time, "Bonsoir," after; with the contact's name when known."""
    try:
        moment = now or datetime.now(ZoneInfo(timezone))
    except Exception:
        moment = now or datetime.now()
    words = GREETINGS.get(language, GREETINGS["fr"])
    word = words["evening"] if moment.hour >= EVENING_HOUR else words["day"]
    name = (contact_name or "").strip()
    return f"{word} {name}," if name else f"{word},"


def parse_template(text: str, email_type: str, language: str, path: Path | None = None,
                   html: bool | None = None) -> Template:
    lines = text.replace("\r\n", "\n").split("\n")
    if not lines or not lines[0].lower().startswith("subject:"):
        raise TemplateError(f"Template {path or email_type} must start with a 'Subject:' line.")
    subject = lines[0].split(":", 1)[1].strip()
    body = "\n".join(lines[1:]).lstrip("\n").rstrip() + "\n"
    found = set(PLACEHOLDER.findall(subject)) | set(PLACEHOLDER.findall(body))
    if html is None:
        html = bool(path and path.suffix.lower() == ".html")
    return Template(email_type=email_type, language=language, subject=subject, body=body,
                    path=path, placeholders=found, html=html)


class TemplateStore:
    """Reads templates fresh from disk on every call, so an edit takes effect on the next draft.
    An .html file wins over a .txt file of the same name."""

    def __init__(self, folder: Path, languages: list[str] | None = None):
        self.folder = Path(folder)
        self.languages = languages or list(LANGUAGES)

    def _find(self, stem: str) -> Path | None:
        for ext in (".html", ".txt"):
            p = self.folder / f"{stem}{ext}"
            if p.exists():
                return p
        return None

    def available(self) -> dict[str, list[str]]:
        return {t: [lang for lang in self.languages if self._find(f"{t}_{lang}")] for t in ("preview", "quote")}

    def load(self, email_type: str, language: str) -> Template:
        if email_type not in ("preview", "quote"):
            raise TemplateError(f"Unknown email type '{email_type}'.")
        path = self._find(f"{email_type}_{language}")
        if not path:
            raise TemplateError(f"Template missing: {email_type}_{language}.html (or .txt) in {self.folder}.")
        return parse_template(path.read_text(encoding="utf-8"), email_type, language, path)

    def signature(self, language: str, html: bool = False) -> str:
        """The signature in the form the template needs: HTML for an .html template (a .txt
        signature is converted), text for a .txt template (an .html signature is flattened)."""
        for stem in (f"signature_{language}", "signature"):
            p = self._find(stem)
            if p:
                raw = p.read_text(encoding="utf-8").strip()
                is_html = p.suffix.lower() == ".html"
                if html and not is_html:
                    return htmllib.escape(raw).replace("\n", "<br>")
                if not html and is_html:
                    return html_to_text(raw)
                return raw
        return ""


def html_to_text(raw: str) -> str:
    raw = re.sub(r"<(style|script).*?</\1>", "", raw, flags=re.S | re.I)
    raw = re.sub(r"<br\s*/?>|</p>|</div>|</tr>|</li>", "\n", raw, flags=re.I)
    text = htmllib.unescape(re.sub(r"<[^>]+>", "", raw))
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def build_variables(*, company_name: str, language: str, contact_name: str | None = None,
                    city: str | None = None, preview_link: str | None = None,
                    signature: str = "", agency_name: str = "", timezone: str = "Europe/Luxembourg",
                    now: datetime | None = None) -> dict[str, str]:
    return {
        "company_name": company_name,
        "contact_name": contact_name.strip() if contact_name else "",
        "greeting": greeting(language, contact_name or "", now=now, timezone=timezone),
        "city": city or "",
        "preview_link": preview_link or "",
        "signature": signature,
        "agency_name": agency_name,
    }


# Values that are already HTML and must not be escaped inside an .html template.
RAW_HTML_KEYS = {"signature"}


def render(template: Template, variables: dict[str, str]) -> RenderedEmail:
    """Fill placeholders. Empty optional values are an error only when the template uses them
    and nothing sensible exists — {{contact_name}} is the exception handled by {{greeting}}.
    In an HTML template every value is escaped except the signature (HTML by nature) and links."""
    def sub(text: str, escape: bool) -> str:
        def repl(m: re.Match) -> str:
            key = m.group(1)
            if key not in variables:
                raise TemplateError(f"Unknown placeholder {{{{{key}}}}} in template {template.path or template.email_type}.")
            value = variables[key]
            if escape and key not in RAW_HTML_KEYS:
                if key == "preview_link" and value.startswith("http"):
                    return f'<a href="{htmllib.escape(value, quote=True)}">{htmllib.escape(value)}</a>'
                return htmllib.escape(value)
            return value
        return PLACEHOLDER.sub(repl, text)

    subject = sub(template.subject, escape=False)
    body = sub(template.body, escape=template.html)
    leftover = PLACEHOLDER.findall(subject + body)
    if leftover:
        raise TemplateError(f"Unfilled placeholders remain: {', '.join(sorted(set(leftover)))}")
    # Required values the owner's template relies on must not be blank ({{preview_link}} is empty
    # when the video is attached, so it is optional).
    for key in ("signature", "company_name"):
        if key in template.placeholders and not variables.get(key):
            raise TemplateError(f"Template uses {{{{{key}}}}} but no value is available.")
    return RenderedEmail(subject=subject.strip(), body=body, language=template.language,
                         template_file=template.path.name if template.path else template.email_type,
                         html=template.html)
