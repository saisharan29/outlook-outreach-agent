"""The chat report (FR-26, FR-27): what was found, where, what was attached, what needs attention."""
from __future__ import annotations

from .models import CompanyReport, Question

STATUS_LABEL = {
    "draft_created": "draft created in Outlook",
    "question": "waiting for your answer",
    "no_draft": "no draft created",
    "refused": "refused",
    "failed": "failed",
}
STATUS_ICON = {"draft_created": "[OK]", "question": "[?]", "no_draft": "[NO DRAFT]", "refused": "[REFUSED]", "failed": "[FAILED]"}


def _conf(c: str) -> str:
    return {"high": "high confidence", "medium": "medium confidence", "low": "LOW confidence"}.get(c or "", c or "")


def render_question(q: Question) -> str:
    lines = [q.text]
    for i, opt in enumerate(q.options, 1):
        lines.append(f"{i}. {opt}")
    lines += q.details
    if q.kind in ("choose_company", "choose_file", "choose_email"):
        lines.append("Reply with the number (or 'no' to stop).")
    elif q.kind == "confirm_duplicate":
        lines.append("Reply 'yes' to create another one anyway, or 'no'.")
    elif q.kind == "email_type":
        lines.append("Reply 'preview' or 'quote' (devis).")
    return "\n".join(lines)


def render_company(r: CompanyReport) -> str:
    lines = [f"### {STATUS_ICON.get(r.status, '')} {r.request.label} — {STATUS_LABEL.get(r.status, r.status)}"]
    if r.company:
        bits = [r.company.get("name", "")]
        if r.company.get("city"):
            bits.append(r.company["city"])
        if r.company.get("website"):
            bits.append(r.company["website"])
        lines.append(f"- Company: {' · '.join(b for b in bits if b)} (identified via {r.company.get('source', '?')})")
    if r.email:
        who = f" — {r.email['contact_name']}{', ' + r.email['contact_role'] if r.email.get('contact_role') else ''}" \
            if r.email.get("contact_name") else ""
        lines.append(f"- Recipient: {r.email['address']}{who} ({_conf(r.email.get('confidence'))}; "
                     f"{r.email.get('where', '')}: {r.email.get('source', '')}; found {str(r.email.get('found_at', ''))[:10]})")
    elif r.status != "question":
        lines.append("- Recipient: none found")
    if r.phone:
        wa = ""
        if r.whatsapp:
            wa = f" — WhatsApp: {r.whatsapp['label']} ({r.whatsapp['hint']}) {r.whatsapp['link']}"
        lines.append(f"- Phone: {r.phone.get('international', r.phone.get('e164', ''))} ({r.phone.get('kind', '')}; "
                     f"{_conf(r.phone.get('confidence'))}; {r.phone.get('where', '')}: {r.phone.get('source', '')}){wa}")
    elif r.status != "question":
        lines.append("- Phone: none found")
    if r.file:
        mode = {"attached": "attached", "link": "sharing link inserted (file above the size limit)"}.get(
            (r.draft or {}).get("attachment_mode", ""), "found")
        extra = f"; {r.file['note']}" if r.file.get("note") else ""
        lines.append(f"- File: {r.file['name']} ({r.file.get('size_mb', '?')} MB, {mode}{extra})")
    if r.draft:
        link = f" — open: {r.draft['web_link']}" if r.draft.get("web_link") else ""
        lines.append(f"- Draft: in Outlook Drafts, subject \"{r.draft['subject']}\", template {r.draft.get('template_file', '')}{link}")
    if r.message:
        lines.append(f"- {r.message}")
    if r.sources:
        shown = r.sources[:8]
        more = f" (+{len(r.sources) - 8} more)" if len(r.sources) > 8 else ""
        lines.append(f"- Sources checked: {', '.join(shown)}{more}")
    if r.question:
        lines.append("")
        lines.append(render_question(r.question))
    if r.attention:
        lines.append("")
        lines.append("**Needs your attention**")
        lines += [f"- {a}" for a in r.attention]
    return "\n".join(lines)


def render_batch(reports: list[CompanyReport]) -> str:
    if not reports:
        return "Nothing to do."
    if len(reports) == 1:
        return render_company(reports[0])
    counts: dict[str, int] = {}
    for r in reports:
        counts[r.status] = counts.get(r.status, 0) + 1
    summary = ", ".join(f"{n} {STATUS_LABEL[s]}" for s, n in counts.items())
    parts = [f"## {len(reports)} companies — {summary}"]
    parts += [render_company(r) for r in reports]
    pending = [r for r in reports if r.status == "question"]
    if len(pending) > 1:
        parts.append("")
        parts.append(f"{len(pending)} questions are waiting; answer the first one and I will ask the next.")
    return "\n\n".join(parts)


HELP_TEXT = """I turn one message into a reviewed Outlook draft. I never send anything.

Examples:
- Preview email for Boulangerie Martin, Lyon
- Quote email for Garage Dupont (site: garage-dupont.fr)
- Devis pour Garage Dupont; Boulangerie Martin, Lyon; Fleuriste Rose, Nantes   (batch)
- Preview email for Café Léon, Lyon, email: leon@cafeleon.fr   (you give the address yourself)
- Preview email for Boulangerie Martin, Lyon, in English
- Do not contact Garage Dupont

Files must follow the naming convention: CompanyName_City_preview_YYYY-MM-DD.mp4 and
CompanyName_City_quote_YYYY-MM-DD.pdf, in the Videos and Quotes folders.
Type 'status' for the connection state and the last actions."""


def question_to_dict(q: Question) -> dict:
    return {"kind": q.kind, "text": q.text, "options": q.options, "details": q.details,
            "company": q.request.label, "email_type": q.request.email_type}


def report_to_dict(r: CompanyReport) -> dict:
    return {"company_label": r.request.label, "email_type": r.request.email_type, "status": r.status,
            "status_label": STATUS_LABEL.get(r.status, r.status), "company": r.company, "email": r.email,
            "phone": r.phone, "whatsapp": r.whatsapp, "file": r.file, "draft": r.draft, "sources": r.sources,
            "attention": r.attention, "message": r.message,
            "question": question_to_dict(r.question) if r.question else None}
