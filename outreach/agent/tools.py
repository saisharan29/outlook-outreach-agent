"""The agent's tools (section 6): exactly these, nothing broader, and no send_email.

    identify_company(name, city?, website?)
    find_contacts(company)
    check_whatsapp(phone)
    find_file(company, type)
    create_draft(recipient, template, variables, attachment)
    registry_read / registry_write

Every guardrail of section 8 is enforced inside the tool, not in the prompt: a recipient must
have a source, a file must belong to the company, no placeholder may remain, a duplicate needs a
confirmation, a do-not-contact company is refused, a draft is reported only when Graph confirmed it.
"""
from __future__ import annotations

import mimetypes
import re
from dataclasses import asdict, dataclass
from typing import Any

from ..contacts.phone import parse_phone
from ..contacts.validation import check_email
from ..contacts.whatsapp import check_whatsapp as _check_whatsapp
from ..naming import match_files, normalize, parse_filename
from ..registry import Company, now_iso
from ..research.identify import Candidate
from ..templates import TemplateError, build_variables, language_for_country, render
from .context import Context

OPT_OUT_WORDS = ("désinscri", "desinscri", "ne plus recevoir", "plus de message", "opt out", "opt-out",
                 "unsubscribe", "stop", "ne souhaitez plus", "no longer wish")


class ToolError(ValueError):
    """A refusal the tool explains; the caller reports it, never works around it."""


# ---------------------------------------------------------------------------------------------
# Tool schemas (strict) — what the model sees in AGENT_MODE=agent
# ---------------------------------------------------------------------------------------------
def _obj(props: dict, required: list[str]) -> dict:
    return {"type": "object", "properties": props, "required": required, "additionalProperties": False}


COMPANY_SCHEMA = _obj({"name": {"type": "string"}, "city": {"type": "string"}, "website": {"type": "string"},
                       "country": {"type": "string"}}, ["name", "city", "website", "country"])

TOOL_SCHEMAS: list[dict] = [
    {"name": "identify_company", "strict": True,
     "description": "Confirm which company the owner means: registry first, then the web. Returns one identified "
                    "company, or several candidates (then ask the owner which one), or not_found. Also says whether "
                    "the company is marked do-not-contact.",
     "input_schema": _obj({"name": {"type": "string"}, "city": {"type": "string", "description": "empty when unknown"},
                           "website": {"type": "string", "description": "empty when unknown"}}, ["name", "city", "website"])},
    {"name": "find_contacts", "strict": True,
     "description": "Email and phone for an identified company, each with source URL, date and confidence. Reuses "
                    "recent registry details unless force_refresh. Never invents an address.",
     "input_schema": _obj({"company": COMPANY_SCHEMA, "force_refresh": {"type": "boolean"}}, ["company", "force_refresh"])},
    {"name": "check_whatsapp", "strict": True,
     "description": "WhatsApp status for a phone number: yes, no or unverified, with the wa.me link and the mobile/landline hint.",
     "input_schema": _obj({"phone": {"type": "string"}}, ["phone"])},
    {"name": "find_file", "strict": True,
     "description": "The preview video (type=preview) or quote PDF (type=quote) for a company from the owner's folders. "
                    "Returns match, none (with the closest names) or ambiguous (several companies could match: ask).",
     "input_schema": _obj({"company": {"type": "string"}, "type": {"type": "string", "enum": ["preview", "quote"]},
                           "city": {"type": "string"}}, ["company", "type", "city"])},
    {"name": "create_draft", "strict": True,
     "description": "Create the Outlook draft (never sends). Refuses when the recipient has no source, the file is "
                    "another company's, a placeholder is unfilled, the domain cannot receive mail, or the company is "
                    "do-not-contact. Returns needs_confirmation when a draft or sent email of this type already exists; "
                    "call again with confirm_duplicate=true only after the owner said yes.",
     "input_schema": _obj({"recipient": {"type": "string"}, "template": {"type": "string", "enum": ["preview", "quote"]},
                           "variables": _obj({"company_name": {"type": "string"}, "contact_name": {"type": "string"},
                                              "city": {"type": "string"}, "country": {"type": "string"},
                                              "language": {"type": "string", "enum": ["", "fr", "en"]}},
                                             ["company_name", "contact_name", "city", "country", "language"]),
                           "attachment": {"type": "string", "description": "file name from find_file"},
                           "confirm_duplicate": {"type": "boolean"}},
                          ["recipient", "template", "variables", "attachment", "confirm_duplicate"])},
    {"name": "registry_read", "strict": True,
     "description": "The registry row for a company (contact details with sources, drafts already created, do-not-contact) and the recent action log.",
     "input_schema": _obj({"company": {"type": "string"}, "city": {"type": "string"}}, ["company", "city"])},
    {"name": "registry_write", "strict": True,
     "description": "Update a registry row: aliases, do_not_contact (with reason), contact name/role, or an email the "
                    "OWNER gave in the chat (source 'owner').",
     "input_schema": _obj({"company": {"type": "string"}, "city": {"type": "string"},
                           "aliases": {"type": "array", "items": {"type": "string"}},
                           "do_not_contact": {"type": "boolean"}, "reason": {"type": "string"},
                           "contact_name": {"type": "string"}, "contact_role": {"type": "string"},
                           "owner_email": {"type": "string", "description": "an address the owner typed, else empty"}},
                          ["company", "city", "aliases", "do_not_contact", "reason", "contact_name", "contact_role", "owner_email"])},
]
TOOL_NAMES = {t["name"] for t in TOOL_SCHEMAS}
assert "send_email" not in TOOL_NAMES


# ---------------------------------------------------------------------------------------------
# Implementations
# ---------------------------------------------------------------------------------------------
@dataclass
class ToolCall:
    name: str
    input: dict
    output: dict


class Tools:
    def __init__(self, ctx: Context):
        self.ctx = ctx
        self.calls: list[ToolCall] = []

    def execute(self, name: str, args: dict) -> dict:
        if name not in TOOL_NAMES:
            raise ToolError(f"Unknown tool {name}. There is no such tool (and no send tool).")
        fn = getattr(self, name)
        out = fn(**args)
        self.calls.append(ToolCall(name, args, out))
        return out

    # --- identify_company ----------------------------------------------------------
    def identify_company(self, name: str, city: str = "", website: str = "") -> dict:
        name = (name or "").strip()
        if not name:
            raise ToolError("A company name is required.")
        rows = self.ctx.registry.find(name, city or None)
        if len(rows) == 1 or (rows and city):
            r = rows[0]
            return {"status": "identified", "from_registry": True, "do_not_contact": r.do_not_contact,
                    "do_not_contact_reason": r.do_not_contact_reason,
                    "company": {"name": r.name, "city": r.city, "website": r.website, "country": r.country or
                                self.ctx.settings.DEFAULT_COUNTRY, "address": "", "source": "client registry"}}
        if len(rows) > 1:
            return {"status": "ambiguous", "from_registry": True, "candidates": [
                {"name": r.name, "city": r.city, "website": r.website, "country": r.country, "source": "client registry"}
                for r in rows]}
        try:
            cands = self.ctx.researcher.identify(name, city, website)
        except Exception as exc:
            return {"status": "not_found", "from_registry": False, "candidates": [],
                    "note": f"Research failed: {type(exc).__name__}: {exc}"}
        if not cands:
            return {"status": "not_found", "from_registry": False, "candidates": [],
                    "note": "No company found on the web with this name and city."}
        if len(cands) > 1 and not website:
            return {"status": "ambiguous", "from_registry": False, "candidates": [asdict(c) for c in cands]}
        c = cands[0]
        return {"status": "identified", "from_registry": False, "do_not_contact": False, "do_not_contact_reason": "",
                "company": {"name": c.name or name, "city": c.city or city, "website": c.website,
                            "country": c.country or self.ctx.settings.DEFAULT_COUNTRY, "address": c.address,
                            "source": c.source}}

    # --- find_contacts ------------------------------------------------------------------
    def find_contacts(self, company: dict, force_refresh: bool = False) -> dict:
        name, city = company.get("name", "").strip(), company.get("city", "").strip()
        website, country = company.get("website", ""), company.get("country", "") or self.ctx.settings.DEFAULT_COUNTRY
        row = self.ctx.registry.get(name, city) or (self.ctx.registry.find(name, city or None) or [None])[0]
        max_age = self.ctx.settings.REGISTRY_MAX_AGE_DAYS
        if row and not force_refresh and (row.email or row.phone) and row.contact_is_recent(max_age):
            return {"from_registry": True, "sources_checked": ["client registry"], "notes": [
                f"Contact details reused from the registry (found {row.email_found_at or row.phone_found_at}, "
                f"younger than {max_age} days)."],
                "email": _email_dict(row.email, row.email_source, "registry", row.email_confidence,
                                     row.contact_name, row.contact_role, None, row.email_found_at) if row.email else None,
                "phone": _phone_dict(row.phone, row.phone_source, "registry", row.phone_confidence, row.phone_found_at,
                                     self.ctx.settings.DEFAULT_COUNTRY) if row.phone else None,
                "alternatives": []}
        cand = Candidate(name=name, website=website or (row.website if row else ""), city=city or (row.city if row else ""),
                         country=country)
        try:
            res = self.ctx.researcher.find_contacts(cand)
        except Exception as exc:
            return {"from_registry": False, "email": None, "phone": None, "alternatives": [],
                    "sources_checked": [], "notes": [f"Research failed: {type(exc).__name__}: {exc}"]}
        best, phone = res.best_email, res.best_phone
        stamp = now_iso()
        out = {"from_registry": False, "sources_checked": res.sources_checked, "notes": list(res.notes),
               "email": None, "phone": None,
               "alternatives": [_email_dict(e.email, e.source_url, e.where, e.confidence, e.contact_name,
                                            e.contact_role, e.mx_ok, stamp) for e in res.emails if e is not best][:5]}
        if best:
            out["email"] = _email_dict(best.email, best.source_url, best.where, best.confidence, best.contact_name,
                                       best.contact_role, best.mx_ok, stamp)
        if phone:
            out["phone"] = _phone_dict(phone.phone.e164, phone.source_url, phone.where, phone.confidence, stamp,
                                       self.ctx.settings.DEFAULT_COUNTRY)
        dead = [e.email for e in res.emails if e.mx_ok is False]
        if dead:
            out["notes"].append(f"Rejected (domain cannot receive mail): {', '.join(dead)}")
        if row and row.email and not best:
            out["notes"].append(f"Previous registry address {row.email} not confirmed by this research; kept as alternative.")
            out["alternatives"].insert(0, _email_dict(row.email, row.email_source, "registry (stale)", "low",
                                                      row.contact_name, row.contact_role, None, row.email_found_at))
        # Persist what was found (section 7: the agent updates the registry after researching).
        c = row or Company(name=name, city=city)
        c.name = c.name or name
        c.website, c.country = c.website or cand.website, c.country or country
        if best:
            c.email, c.email_source, c.email_confidence, c.email_found_at = best.email, best.source_url, best.confidence, stamp
            if best.contact_name:
                c.contact_name, c.contact_role = best.contact_name, best.contact_role
        if phone:
            c.phone, c.phone_source, c.phone_confidence, c.phone_found_at = phone.phone.e164, phone.source_url, phone.confidence, stamp
        self.ctx.registry.upsert(c)
        return out

    # --- check_whatsapp ---------------------------------------------------------------------
    def check_whatsapp(self, phone: str) -> dict:
        p = parse_phone(phone, self.ctx.settings.DEFAULT_COUNTRY)
        if not p:
            raise ToolError(f"'{phone}' is not a valid phone number.")
        s = self.ctx.settings
        st = _check_whatsapp(p, validator_url=s.WHATSAPP_VALIDATOR_URL, validator_key=s.WHATSAPP_VALIDATOR_KEY)
        return {"phone": p.international, "e164": p.e164, "kind": p.kind, "status": st.status, "label": st.label,
                "hint": st.hint, "link": st.link, "method": st.method, "checked_at": now_iso()}

    # --- find_file ----------------------------------------------------------------------------
    def find_file(self, company: str, type: str, city: str = "") -> dict:
        if type not in ("preview", "quote"):
            raise ToolError("type must be 'preview' or 'quote'.")
        folder = self.ctx.settings.VIDEOS_FOLDER if type == "preview" else self.ctx.settings.QUOTES_FOLDER
        files = {f.name: f for f in self.ctx.files.list_files(folder)}
        aliases = []
        for r in self.ctx.registry.find(company, city or None):
            aliases += r.aliases + [r.name]
        m = match_files(list(files), company, type, city or None, aliases)
        limit = self.ctx.settings.max_attachment_bytes
        out: dict[str, Any] = {"status": m.status, "note": m.note, "folder": folder, "type": type,
                               "versions": [v.filename for v in (m.versions or [])],
                               "candidates": [c.filename for c in (m.candidates or [])], "file": None}
        if m.chosen:
            f = files[m.chosen.filename]
            out["file"] = {"name": f.name, "size": f.size, "size_mb": round(f.size / 1048576, 1) if f.size >= 104858 else "<0.1",
                           "too_large": type == "preview" and f.size > limit, "date": str(m.chosen.date or ""),
                           "city": m.chosen.city, "limit_mb": self.ctx.settings.MAX_ATTACHMENT_MB}
        return out

    # --- create_draft ---------------------------------------------------------------------------
    def create_draft(self, recipient: str, template: str, variables: dict, attachment: str,
                     confirm_duplicate: bool = False) -> dict:
        s, reg = self.ctx.settings, self.ctx.registry
        recipient = (recipient or "").strip().lower()
        company_name = (variables.get("company_name") or "").strip()
        city = (variables.get("city") or "").strip()
        if template not in ("preview", "quote"):
            raise ToolError("template must be 'preview' or 'quote'.")
        if not company_name:
            raise ToolError("variables.company_name is required.")
        row = reg.get(company_name, city) or (reg.find(company_name, city or None) or [None])[0]
        # 1. do-not-contact
        if row and row.do_not_contact:
            raise ToolError(f"{row.name} is marked do-not-contact ({row.do_not_contact_reason or 'asked to stop'}). No draft.")
        # 2. the recipient must have a source: research, the registry, or the owner's own words
        known = {row.email.lower()} if row and row.email else set()
        known |= {e.lower() for e in self.ctx.owner_supplied_recipients}
        for call in self.calls:
            if call.name == "find_contacts" and call.output.get("email"):
                known.add(call.output["email"]["address"].lower())
                known |= {a["address"].lower() for a in call.output.get("alternatives", [])}
        if recipient not in known:
            raise ToolError(f"Recipient {recipient or '(empty)'} has no source: it was neither found by research "
                            "nor given by the owner. The agent never invents an address.")
        chk = check_email(recipient, dns_check=self.ctx.researcher.dns_check)
        if not chk.syntax_ok:
            raise ToolError(f"Recipient {recipient} is not a valid address ({chk.detail}).")
        if chk.mx_ok is False:
            raise ToolError(f"Recipient domain {chk.domain} cannot receive mail ({chk.detail}). Address not used.")
        # 3. the attachment must belong to this company
        if not attachment:
            raise ToolError("An attachment is required (the preview video or the quote PDF).")
        parsed = parse_filename(attachment)
        aliases = (row.aliases + [row.name]) if row else []
        keys = {normalize(company_name)} | {normalize(a) for a in aliases}
        if not parsed or parsed.company_key not in keys or parsed.type != template:
            raise ToolError(f"File {attachment} does not belong to {company_name} as a {template} file. "
                            "A file of one company is never attached to another company's email.")
        if city and parsed.city_key != normalize(city):
            raise ToolError(f"File {attachment} is for city '{parsed.city}', not '{city}'.")
        folder = s.VIDEOS_FOLDER if template == "preview" else s.QUOTES_FOLDER
        file = next((f for f in self.ctx.files.list_files(folder) if f.name == attachment), None)
        if not file:
            raise ToolError(f"File {attachment} is no longer in the {folder} folder.")
        # 4. template and language (needed to recognise a same-type duplicate by its subject)
        country = (variables.get("country") or (row.country if row else "") or s.DEFAULT_COUNTRY)
        language = (variables.get("language") or "").lower() or language_for_country(country, s.DEFAULT_LANGUAGE, s.languages)
        if language not in s.languages:
            raise ToolError(f"Language '{language}' is not one the owner writes in ({', '.join(s.languages)}). "
                            "Say for example 'en français', 'auf Deutsch' or 'op Lëtzebuergesch'.")
        try:
            tpl = self.ctx.templates.load(template, language)
        except TemplateError as exc:
            raise ToolError(str(exc))
        # 5. duplicates (FR-24): registry first, then Outlook Drafts and Sent Items, same type only
        existing = []
        if row:
            stamp = row.preview_drafted_at if template == "preview" else row.quote_drafted_at
            if stamp:
                existing.append(f"registry: {template} draft created {stamp[:10]} with "
                                f"{row.preview_file if template == 'preview' else row.quote_file}")
        graph = self.ctx.graph
        if graph is None:
            raise ToolError("Outlook is not connected: no draft can be created. Sign in with Microsoft first.")
        probe_subject = _subject_key(_render_subject(tpl, row.name if row else company_name))
        try:
            for folder_name, label in (("drafts", "Outlook Drafts"), ("sentitems", "Outlook Sent Items")):
                for m in graph.find_messages_to(recipient, folder_name):
                    if _subject_key(m.get("subject", "")) == probe_subject:
                        existing.append(f"{label}: \"{m.get('subject', '')}\"")
        except Exception as exc:
            existing.append(f"could not check Outlook for duplicates ({type(exc).__name__})")
        if existing and not confirm_duplicate:
            return {"status": "needs_confirmation", "reason": "An email of this type to this company already exists.",
                    "existing": existing, "draft_id": "", "web_link": ""}
        signature = self.ctx.templates.signature(language, html=tpl.html)
        if not signature:
            raise ToolError("No signature file (Templates/signature.html or signature.txt). The draft needs the owner's signature.")
        attachment_mode, preview_link, attention = "attached", "", []
        if template == "preview" and file.size > s.max_attachment_bytes:
            link = self.ctx.files.share_link(file)
            if not link:
                raise ToolError(f"Video {file.name} is {file.size / 1048576:.0f} MB, above the {s.MAX_ATTACHMENT_MB} MB limit, "
                                "and no sharing link could be created. Compress the video or share it manually.")
            attachment_mode, preview_link = "link", link
            attention.append(f"Video above {s.MAX_ATTACHMENT_MB} MB: a sharing link was inserted instead of the file.")
        contact_name = (variables.get("contact_name") or (row.contact_name if row else "") or "").strip()
        vars_ = build_variables(company_name=row.name if row else company_name, language=language,
                                contact_name=contact_name, city=city or (row.city if row else ""),
                                preview_link=preview_link, signature=signature, agency_name=self.ctx.agency_name,
                                timezone=s.TIMEZONE)
        if "preview_link" in tpl.placeholders and not preview_link:
            vars_["preview_link"] = ""
        try:
            email = render(tpl, vars_)
        except TemplateError as exc:
            raise ToolError(str(exc))
        body = email.body
        if "signature" not in tpl.placeholders:
            body = body.rstrip("\n") + ("<br><br>" if tpl.html else "\n\n") + signature + "\n"
        if attachment_mode == "link" and "preview_link" not in tpl.placeholders:
            label = {"fr": "Vidéo", "de": "Video", "lb": "Video", "en": "Video"}.get(language, "Video")
            body = body.rstrip("\n") + (f'<br><br>{label} : <a href="{preview_link}">{preview_link}</a>' if tpl.html
                                         else f"\n\n{label} : {preview_link}") + "\n"
        if not any(w in body.lower() for w in OPT_OUT_WORDS):
            attention.append("The template has no opt-out sentence (section 9 of the spec asks for one).")
        # 6. the draft, then the attachment; a failed attachment deletes the draft (never half a draft)
        cc = [a for a in s.cc_list if a.lower() != recipient]
        try:
            draft = graph.create_draft(to=recipient, subject=email.subject, body=body, body_type=email.body_type,
                                       to_name=contact_name, cc=cc)
        except Exception as exc:
            reg.log(company=company_name, email_type=template, recipient=recipient, file=attachment,
                    result="failed", detail=f"draft not created: {exc}")
            raise ToolError(f"Outlook did not create the draft: {exc}")
        if attachment_mode == "attached":
            try:
                content = self.ctx.files.read(file)
                ctype = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
                graph.attach(draft.draft_id, file.name, content, ctype)
            except Exception as exc:
                try:
                    graph.delete_draft(draft.draft_id)
                except Exception:
                    attention.append("The draft without its attachment could not be deleted: remove it by hand.")
                reg.log(company=company_name, email_type=template, recipient=recipient, file=attachment,
                        result="failed", detail=f"attachment failed, draft removed: {exc}")
                raise ToolError(f"The attachment could not be added ({exc}); the draft was removed.")
        # 7. registry + log
        c = row or Company(name=company_name, city=city, country=country)
        if template == "preview":
            c.preview_drafted_at, c.preview_file = now_iso(), attachment
        else:
            c.quote_drafted_at, c.quote_file = now_iso(), attachment
        if contact_name and not c.contact_name:
            c.contact_name = contact_name
        if recipient in {e.lower() for e in self.ctx.owner_supplied_recipients} and not c.email:
            c.email, c.email_source, c.email_confidence, c.email_found_at = recipient, "owner", "high", now_iso()
        reg.upsert(c)
        reg.log(company=c.name, email_type=template, recipient=recipient, file=attachment, result="draft_created",
                detail=f"draft {draft.draft_id}; attachment {attachment_mode}; template {email.template_file}")
        return {"status": "created", "draft_id": draft.draft_id, "web_link": draft.web_link, "subject": email.subject,
                "recipient": recipient, "cc": cc, "attachment": attachment, "attachment_mode": attachment_mode,
                "template_file": email.template_file, "language": language, "format": email.body_type,
                "attention": attention, "existing": existing}

    # --- registry ---------------------------------------------------------------------------------
    def registry_read(self, company: str, city: str = "") -> dict:
        rows = self.ctx.registry.find(company, city or None)
        return {"companies": [r.to_dict() for r in rows],
                "recent_actions": [a.__dict__ for a in self.ctx.registry.actions(20)
                                   if normalize(a.company) in {r.key for r in rows}]}

    def registry_write(self, company: str, city: str = "", aliases: list[str] | None = None,
                       do_not_contact: bool | None = None, reason: str = "", contact_name: str = "",
                       contact_role: str = "", owner_email: str = "") -> dict:
        rows = self.ctx.registry.find(company, city or None)
        c = rows[0] if len(rows) == 1 else (self.ctx.registry.get(company, city) or Company(name=company, city=city))
        if aliases:
            c.aliases = sorted(set(c.aliases) | {a.strip() for a in aliases if a.strip()})
        if do_not_contact is not None:
            c.do_not_contact = do_not_contact
            c.do_not_contact_reason = reason if do_not_contact else ""
        if contact_name:
            c.contact_name = contact_name
        if contact_role:
            c.contact_role = contact_role
        if owner_email:
            owner_email = owner_email.strip().lower()
            if owner_email not in {e.lower() for e in self.ctx.owner_supplied_recipients}:
                raise ToolError("owner_email must be an address the owner typed in the chat.")
            c.email, c.email_source, c.email_confidence, c.email_found_at = owner_email, "owner", "high", now_iso()
        self.ctx.registry.upsert(c)
        self.ctx.registry.log(company=c.name, result="registry_updated",
                              detail=f"do_not_contact={c.do_not_contact} aliases={c.aliases} email={c.email}")
        return {"ok": True, "company": c.to_dict()}


def _render_subject(tpl, company_name: str) -> str:
    from ..templates import PLACEHOLDER
    return PLACEHOLDER.sub(lambda m: company_name if m.group(1) == "company_name" else "", tpl.subject)


def _subject_key(subject: str) -> str:
    return normalize(re.sub(r"^\s*(re|tr|fwd?)\s*:\s*", "", subject or "", flags=re.I))


def _email_dict(address, source, where, confidence, name, role, mx_ok, found_at) -> dict:
    return {"address": address, "source": source, "where": where, "confidence": confidence or "medium",
            "contact_name": name or "", "contact_role": role or "", "mx_ok": mx_ok, "found_at": found_at}


def _phone_dict(e164, source, where, confidence, found_at, region) -> dict:
    p = parse_phone(e164, region)
    return {"e164": e164, "international": p.international if p else e164, "kind": p.kind if p else "unknown",
            "source": source, "where": where, "confidence": confidence or "medium", "found_at": found_at}


def owner_typed_emails(text: str) -> list[str]:
    return [e.lower() for e in re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text or "")]
