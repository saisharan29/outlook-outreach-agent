"""The request pipeline (spec section 3), run by rules in the spec's order.

One company goes through: identify → registry/research → WhatsApp → file → template → draft →
report. Anything uncertain becomes a question back to the owner and the pipeline stops for that
company (section 8). A batch runs every company and returns one combined report; a failure in
one company never stops the others.
"""
from __future__ import annotations

import traceback

import re

from ..registry import now_iso
from .context import Context
from .intent import parse, resolve_answer
from .models import CompanyReport, CompanyRequest, Intent, Question, Session
from .report import HELP_TEXT, render_batch
from .tools import ToolError, Tools, owner_typed_emails


CANCEL = re.compile(r"^\s*(?:cancel|annule[rz]?|forget it|laisse tomber|stop all|clear)\s*\.?\s*$", re.I)


class Pipeline:
    def __init__(self, ctx: Context, llm=None):
        self.ctx = ctx
        self.llm = llm

    # --- chat entry point ------------------------------------------------------------------
    def handle(self, text: str, session: Session) -> str:
        """One owner message in, one reply out. Keeps the pending questions in the session."""
        for e in owner_typed_emails(text):
            self.ctx.owner_supplied_recipients.add(e)
        session.reports = []
        if session.pending and CANCEL.match(text):
            n = len(session.pending)
            for q in session.pending:
                self.ctx.registry.log(company=q.request.name, email_type=q.request.email_type, result="cancelled",
                                      detail=f"owner cancelled: {q.kind}")
            session.pending.clear()
            return f"Cancelled {n} pending question{'s' if n > 1 else ''}. Nothing was created."
        if session.pending:
            q = session.pending[0]
            outcome = resolve_answer(text, q)
            if outcome is None:
                session.pending.pop(0)
                self.ctx.registry.log(company=q.request.name, email_type=q.request.email_type, result="cancelled",
                                      detail=f"owner answered no to: {q.kind}")
                reply = f"Stopped for {q.request.label}; no draft created."
                return reply + self._next_question(session)
            if outcome != "unrelated":
                session.pending.pop(0)
                reports = [self.run_company(outcome)]
                self._queue_questions(reports, session)
                session.reports = reports
                return render_batch(reports) + self._next_question(session, skip_first_if_in=reports)
            # Fall through: the owner started a new request instead; the question stays pending.
        intent = parse(text, self.llm)
        if intent.kind == "help":
            return HELP_TEXT
        if intent.kind == "status":
            return self.status_text()
        if intent.kind == "do_not_contact":
            return self._do_not_contact(intent)
        if intent.kind != "draft" or not intent.companies:
            return ("I did not understand which company you mean. Write for example: "
                    "\"Preview email for Boulangerie Martin, Lyon\" or \"Quote email for Garage Dupont\"."
                    + ("\n\n(A question is still waiting: " + session.pending[0].text + ")" if session.pending else ""))
        reports = self.run_batch(intent.companies)
        self._queue_questions(reports, session)
        session.reports = reports
        return render_batch(reports) + self._next_question(session, skip_first_if_in=reports)

    def _queue_questions(self, reports: list[CompanyReport], session: Session) -> None:
        for r in reports:
            if r.question:
                session.pending.append(r.question)

    def _next_question(self, session: Session, skip_first_if_in: list[CompanyReport] | None = None) -> str:
        if not session.pending:
            return ""
        q = session.pending[0]
        if skip_first_if_in and any(r.question is q for r in skip_first_if_in):
            return ""     # already printed inside the report
        from .report import render_question
        return "\n\nStill waiting for your answer:\n" + render_question(q)

    def _do_not_contact(self, intent: Intent) -> str:
        out = []
        tools = Tools(self.ctx)
        for req in intent.companies:
            res = tools.registry_write(company=req.name, city=req.city, aliases=[], do_not_contact=True,
                                       reason="the owner asked", contact_name="", contact_role="", owner_email="")
            out.append(f"{res['company']['name']} is now marked do-not-contact. No draft will be created for it.")
        return "\n".join(out) or "Which company should I stop contacting?"

    # --- the work ---------------------------------------------------------------------------
    def run_batch(self, requests: list[CompanyRequest]) -> list[CompanyReport]:
        reports = []
        for req in requests:
            try:
                reports.append(self.run_company(req))
            except Exception as exc:   # one company failing never stops the batch (section 8)
                self.ctx.registry.log(company=req.name, email_type=req.email_type, result="failed",
                                      detail=f"{type(exc).__name__}: {exc}")
                reports.append(CompanyReport(request=req, status="failed",
                                             message=f"Unexpected error: {type(exc).__name__}: {exc}",
                                             attention=[traceback.format_exc().strip().splitlines()[-1]]))
        return reports

    def run_company(self, req: CompanyRequest) -> CompanyReport:
        tools = Tools(self.ctx)
        r = CompanyReport(request=req)
        log = self.ctx.registry.log

        # FR-04: the email type is never assumed.
        if req.email_type not in ("preview", "quote"):
            r.status, r.question = "question", Question(
                kind="email_type", request=req, options=[],
                text=f"Which email for {req.label}: the website preview (with the video) or the quote (with the PDF)?")
            return r

        # 1. Identity (FR-06) — registry first, then the web.
        ident = tools.identify_company(req.name, req.city, req.website)
        if ident["status"] == "ambiguous":
            cands = ident["candidates"]
            if req.chosen_candidate is not None and 0 <= req.chosen_candidate < len(cands):
                c = cands[req.chosen_candidate]
                ident = {"status": "identified", "from_registry": ident["from_registry"], "do_not_contact": False,
                         "do_not_contact_reason": "", "company": {**c, "address": c.get("address", "")}}
                if ident["from_registry"]:
                    row = self.ctx.registry.get(c["name"], c.get("city", ""))
                    if row:
                        ident["do_not_contact"], ident["do_not_contact_reason"] = row.do_not_contact, row.do_not_contact_reason
            else:
                r.status, r.question = "question", Question(
                    kind="choose_company", request=req,
                    text=f"Several companies match \"{req.name}\". Which one?",
                    options=[" — ".join(x for x in (c.get("name", ""), c.get("city", ""), c.get("website", "")) if x)
                             for c in cands])
                log(company=req.name, email_type=req.email_type, result="question", detail="ambiguous company")
                return r
        if ident["status"] == "not_found":
            if req.owner_email:
                ident = {"status": "identified", "from_registry": False, "do_not_contact": False, "do_not_contact_reason": "",
                         "company": {"name": req.name, "city": req.city, "website": req.website,
                                     "country": self.ctx.settings.DEFAULT_COUNTRY, "address": "",
                                     "source": "the owner's message (address given by hand)"}}
            else:
                r.status = "no_draft"
                r.message = ident.get("note", "Company not identified.")
                r.attention.append(f"I could not identify {req.label} on the web. Give me its website "
                                   f"(site: …) or its email address (email: …) and I will continue.")
                log(company=req.name, email_type=req.email_type, result="no_draft", detail="company not identified")
                return r
        company = ident["company"]
        r.company = company
        if req.contact_name:
            company["contact_name"] = req.contact_name
        if ident.get("do_not_contact"):
            r.status = "refused"
            r.message = (f"{company['name']} is marked do-not-contact"
                         f"{' (' + ident.get('do_not_contact_reason', '') + ')' if ident.get('do_not_contact_reason') else ''}. "
                         "Nothing was created.")
            log(company=company["name"], email_type=req.email_type, result="refused", detail="do-not-contact")
            return r

        # 2–4. Contact details (registry or research), FR-07 to FR-13.
        if req.owner_email:
            self.ctx.owner_supplied_recipients.add(req.owner_email)
            r.email = {"address": req.owner_email, "source": "given by you in the chat", "where": "owner",
                       "confidence": "high", "contact_name": req.contact_name, "contact_role": "", "found_at": now_iso()}
            reg = self.ctx.registry.get(company["name"], company.get("city", "")) or \
                (self.ctx.registry.find(company["name"], company.get("city") or None) or [None])[0]
            if reg and reg.phone:
                from .tools import _phone_dict
                r.phone = _phone_dict(reg.phone, reg.phone_source, "registry", reg.phone_confidence, reg.phone_found_at,
                                      self.ctx.settings.DEFAULT_COUNTRY)
            r.sources = ["your message"]
        else:
            found = tools.find_contacts(company, force_refresh=req.force_refresh)
            r.sources = found.get("sources_checked", [])
            r.attention += [n for n in found.get("notes", []) if "failed" in n.lower() or "rejected" in n.lower()]
            r.email, r.phone = found.get("email"), found.get("phone")
            if r.email and r.email.get("contact_name") and not req.contact_name:
                company["contact_name"] = r.email["contact_name"]
            if found.get("alternatives"):
                r.attention.append("Other addresses seen: " + "; ".join(
                    f"{a['address']} ({a['where']}, {a['confidence']})" for a in found["alternatives"][:3]))
        # 5. WhatsApp (FR-14 to FR-16)
        if r.phone:
            r.whatsapp = tools.check_whatsapp(r.phone["e164"])
            row = self.ctx.registry.get(company["name"], company.get("city", ""))
            if row:
                row.whatsapp_status, row.whatsapp_checked_at = r.whatsapp["status"], r.whatsapp["checked_at"]
                self.ctx.registry.upsert(row)
        if not r.email:
            r.status = "no_draft"
            r.message = "No email address found, so no draft was created."
            r.attention.append("Give me the address yourself (email: …) and I will create the draft; or correct the website.")
            log(company=company["name"], email_type=req.email_type, result="no_draft",
                detail=f"no email; sources: {', '.join(r.sources)}")
            return r
        if r.email.get("confidence") == "low":
            r.attention.append(f"VERIFY RECIPIENT: {r.email['address']} is a low-confidence match ({r.email.get('source', '')}).")

        # 6. File (FR-17 to FR-20)
        ff = tools.find_file(company["name"], req.email_type, company.get("city", "") or req.city)
        if ff["status"] == "ambiguous":
            if req.chosen_file and req.chosen_file in ff["candidates"]:
                from ..naming import parse_filename
                chosen = parse_filename(req.chosen_file)
                ff = tools.find_file(chosen.company, req.email_type, chosen.city)   # exact company + city of that file
                ff["note"] = "chosen by you"
            else:
                r.status, r.question = "question", Question(
                    kind="choose_file", request=req, options=ff["candidates"],
                    text=f"Several {req.email_type} files could belong to {company['name']}. Which one?",
                    details=["I never pick between two different companies myself."])
                log(company=company["name"], email_type=req.email_type, result="question", detail="ambiguous file")
                return r
        if ff["status"] == "none" or not ff.get("file"):
            r.status = "no_draft"
            closest = ff.get("candidates") or []
            r.message = f"No {req.email_type} file for {company['name']} in the {ff['folder']} folder; no draft created."
            r.attention.append(("Closest file names: " + ", ".join(closest)) if closest else
                               f"Add a file named like {_example_name(company, req.email_type)} to {ff['folder']}.")
            log(company=company["name"], email_type=req.email_type, recipient=r.email["address"], result="no_draft",
                detail=f"no file; closest: {', '.join(closest)}")
            return r
        r.file = {**ff["file"], "note": ff.get("note", "")}
        if ff.get("note") and "Unexpected extension" in ff["note"]:
            r.attention.append(ff["note"])

        # 7–8. Template and draft (FR-21 to FR-25)
        try:
            res = tools.create_draft(recipient=r.email["address"], template=req.email_type,
                                     variables={"company_name": company["name"],
                                                "contact_name": company.get("contact_name", "") or r.email.get("contact_name", ""),
                                                "city": company.get("city", "") or req.city,
                                                "country": company.get("country", ""), "language": req.language},
                                     attachment=r.file["name"], confirm_duplicate=req.confirm_duplicate)
        except ToolError as exc:
            r.status = "refused"
            r.message = str(exc)
            return r
        if res["status"] == "needs_confirmation":
            r.status, r.question = "question", Question(
                kind="confirm_duplicate", request=req, options=[],
                text=f"A {req.email_type} email for {company['name']} already exists. Create another one?",
                details=[f"- {e}" for e in res["existing"]])
            log(company=company["name"], email_type=req.email_type, recipient=r.email["address"], result="question",
                detail="duplicate warning")
            return r
        r.status, r.draft = "draft_created", res
        r.attention += res.get("attention", [])
        if res.get("existing"):
            r.attention.append("Created on your confirmation although an earlier email existed: " + "; ".join(res["existing"]))
        return r

    # --- status ----------------------------------------------------------------------------
    def status_text(self) -> str:
        s = self.ctx.settings
        g = self.ctx.graph
        outlook = (f"connected as {g.account()}" if g is not None and g.connected() else
                   "NOT connected (sign in with Microsoft)" if s.microsoft_configured() or g is not None else
                   "not configured (MS_CLIENT_ID / MS_CLIENT_SECRET missing)")
        avail = self.ctx.templates.available()
        lines = [f"Outlook: {outlook}",
                 f"Files: {self.ctx.files.source} — {s.AGENCY_ROOT} ({_count(self.ctx, s.VIDEOS_FOLDER)} videos, "
                 f"{_count(self.ctx, s.QUOTES_FOLDER)} quotes named by the convention)",
                 f"Templates: preview {avail['preview'] or 'MISSING'}, quote {avail['quote'] or 'MISSING'}",
                 f"Research: {'Claude ' + s.LLM_MODEL if s.ANTHROPIC_API_KEY else 'no API key (owner enters addresses by hand)'}"
                 f"{', search ' + s.SEARCH_PROVIDER if s.SEARCH_PROVIDER != 'anthropic' else ''}"
                 f"{', Google Places' if s.GOOGLE_PLACES_API_KEY else ''}",
                 f"WhatsApp: {'validator configured' if s.WHATSAPP_VALIDATOR_URL else 'wa.me link + mobile/landline hint'}",
                 f"Registry: {len(self.ctx.registry.all_companies())} companies; attachment limit {s.MAX_ATTACHMENT_MB} MB; "
                 f"contacts re-checked after {s.REGISTRY_MAX_AGE_DAYS} days", "", "Last actions:"]
        for a in self.ctx.registry.actions(10):
            lines.append(f"- {a.at[:16]} {a.company} {a.email_type} {a.recipient} {a.file} → {a.result}"
                         + (f" ({a.detail[:80]})" if a.detail else ""))
        return "\n".join(lines)


def _count(ctx: Context, folder: str) -> int:
    from ..naming import parse_filename
    return sum(1 for f in ctx.files.list_files(folder) if parse_filename(f.name))


def _example_name(company: dict, email_type: str) -> str:
    from ..naming import normalize
    name = "".join(w.capitalize() for w in (company.get("name") or "Company").split())
    city = "".join(w.capitalize() for w in (company.get("city") or "City").split())
    ext = "mp4" if email_type == "preview" else "pdf"
    return f"{name}_{city}_{email_type}_YYYY-MM-DD.{ext}"
