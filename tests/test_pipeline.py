import json

import pytest

from outreach.agent.models import CompanyRequest, Session
from outreach.agent.pipeline import Pipeline
from outreach.agent.tools import TOOL_NAMES, ToolError, Tools
from outreach.registry import Company


def drafts(ctx):
    return ctx.graph.drafts


def test_preview_request_creates_a_correct_draft(ctx):
    r = Pipeline(ctx).run_company(CompanyRequest(name="Boulangerie Martin", city="Lyon", email_type="preview"))
    assert r.status == "draft_created"
    d = drafts(ctx)[0]
    assert d["to"] == "contact@boulangerie-martin.example"
    assert d["subject"] == "Votre nouveau site web — Boulangerie Martin"
    assert "Bonjour Jean Martin," in d["body"] and "{{" not in d["body"] and "Sai Sharan" in d["body"]
    assert d["attachments"][0]["name"].startswith("BoulangerieMartin_Lyon_preview_") and d["attachments"][0]["name"] != "BoulangerieMartin_Lyon_preview_2026-09-20.mp4"
    assert r.whatsapp["link"] == "https://wa.me/33612345678" and r.phone["international"] == "+33 6 12 34 56 78"
    row = ctx.registry.get("Boulangerie Martin", "Lyon")
    assert row.preview_drafted_at and row.whatsapp_status == "unverified"
    assert ctx.registry.actions()[0].result == "draft_created"


def test_quote_request_uses_pdf_and_quote_template(ctx):
    r = Pipeline(ctx).run_company(CompanyRequest(name="Garage Dupont", email_type="quote"))
    assert r.status == "draft_created" and drafts(ctx)[0]["attachments"][0]["name"].endswith("quote_2026-10-03.pdf")
    assert drafts(ctx)[0]["subject"].startswith("Devis") and "Bonjour," in drafts(ctx)[0]["body"]


def test_language_override_and_country(ctx):
    Pipeline(ctx).run_company(CompanyRequest(name="Garage Dupont", email_type="quote", language="en"))
    assert drafts(ctx)[0]["subject"].startswith("Quote for")


def test_missing_email_type_asks(ctx):
    r = Pipeline(ctx).run_company(CompanyRequest(name="Garage Dupont"))
    assert r.status == "question" and r.question.kind == "email_type" and not drafts(ctx)


def test_duplicate_warns_then_creates_on_confirmation(ctx):
    p, s = Pipeline(ctx), Session()
    assert "draft created" in p.handle("Preview email for Boulangerie Martin, Lyon", s)
    reply = p.handle("Preview email for Boulangerie Martin, Lyon", s)
    assert "already exists" in reply and len(drafts(ctx)) == 1 and s.pending[0].kind == "confirm_duplicate"
    p.handle("no", s)
    assert len(drafts(ctx)) == 1 and not s.pending
    p.handle("Preview email for Boulangerie Martin, Lyon", s)
    p.handle("yes", s)
    assert len(drafts(ctx)) == 2 and not s.pending
    # A quote after a preview is not a duplicate (same type only).
    assert "draft created" in p.handle("Quote email for Boulangerie Martin, Lyon", s)


def test_ambiguous_company_asks_then_proceeds(ctx):
    ctx.registry.upsert(Company(name="Boulangerie Martin", city="Paris", email="paris@martin.example",
                                email_source="https://x", email_confidence="high", email_found_at="2026-10-01T00:00:00+00:00"))
    p, s = Pipeline(ctx), Session()
    reply = p.handle("Quote email for Boulangerie Martin", s)
    assert "Which one?" in reply and "1. " in reply and s.pending[0].kind == "choose_company" and not drafts(ctx)
    reply = p.handle("1", s)
    assert "draft created" in reply and drafts(ctx)[0]["to"] == "contact@boulangerie-martin.example"


def test_ambiguous_files_never_picked(ctx, agency):
    (agency / "Videos" / "PizzaRoma_Lyon_preview_2026-10-02.mp4").write_bytes(b"\0")
    (agency / "Videos" / "PizzaRoma_Paris_preview_2026-10-02.mp4").write_bytes(b"\0")
    req = CompanyRequest(name="Pizza Roma", email_type="preview", owner_email="pizza@roma.example")
    r = Pipeline(ctx).run_company(req)
    assert r.status == "question" and r.question.kind == "choose_file" and len(r.question.options) == 2 and not drafts(ctx)
    req.chosen_file = "PizzaRoma_Lyon_preview_2026-10-02.mp4"
    r2 = Pipeline(ctx).run_company(req)
    assert r2.status == "draft_created" and drafts(ctx)[0]["attachments"][0]["name"] == "PizzaRoma_Lyon_preview_2026-10-02.mp4"


def test_registry_city_resolves_file_ambiguity(ctx, agency):
    (agency / "Videos" / "GarageDupont_Lyon_preview_2026-10-02.mp4").write_bytes(b"\0")
    r = Pipeline(ctx).run_company(CompanyRequest(name="Garage Dupont", email_type="preview"))
    assert r.status == "draft_created" and drafts(ctx)[0]["attachments"][0]["name"].startswith("GarageDupont_Villeurbanne")


def test_missing_file_means_no_draft_and_a_clear_message(ctx, agency):
    for f in (agency / "Quotes").glob("GarageDupont*"):
        f.unlink()
    r = Pipeline(ctx).run_company(CompanyRequest(name="Garage Dupont", email_type="quote"))
    assert r.status == "no_draft" and "No quote file" in r.message and not drafts(ctx)
    assert ctx.registry.actions()[0].result == "no_draft"


def test_do_not_contact_is_refused(ctx):
    p, s = Pipeline(ctx), Session()
    assert "do-not-contact" in p.handle("Do not contact Garage Dupont", s)
    r = p.run_company(CompanyRequest(name="Garage Dupont", email_type="quote"))
    assert r.status == "refused" and "do-not-contact" in r.message and not drafts(ctx)


def test_owner_supplied_email_phase_one(ctx, agency):
    (agency / "Videos" / "CafeLeon_Lyon_preview_2026-10-04.mp4").write_bytes(b"\0" * 10)
    p, s = Pipeline(ctx), Session()
    reply = p.handle("Preview email for Café Léon, Lyon, email: leon@cafeleon.example", s)
    assert "draft created" in reply and drafts(ctx)[0]["to"] == "leon@cafeleon.example"
    assert ctx.registry.get("Café Léon", "Lyon").email_source == "owner"


def test_no_email_found_means_no_draft_with_sources(ctx):
    r = Pipeline(ctx).run_company(CompanyRequest(name="Unknown Shop", city="Nowhere", email_type="preview"))
    assert r.status == "no_draft" and not drafts(ctx) and r.attention


def test_recipient_without_source_is_refused(ctx):
    t = Tools(ctx)
    with pytest.raises(ToolError, match="no source"):
        t.create_draft(recipient="guess@boulangerie-martin.example", template="preview",
                       variables={"company_name": "Boulangerie Martin", "city": "Lyon", "contact_name": "", "country": "FR", "language": ""},
                       attachment="BoulangerieMartin_Lyon_preview_2026-09-20.mp4")


def test_file_of_another_company_is_refused(ctx):
    t = Tools(ctx)
    with pytest.raises(ToolError, match="never attached to another"):
        t.create_draft(recipient="contact@boulangerie-martin.example", template="preview",
                       variables={"company_name": "Boulangerie Martin", "city": "Lyon", "contact_name": "", "country": "FR", "language": ""},
                       attachment="GarageDupont_Villeurbanne_preview_2026-10-01.mp4")
    assert not drafts(ctx)


def test_unfilled_placeholder_blocks_the_draft(ctx, agency):
    (agency / "Templates" / "quote_fr.txt").write_text("Subject: x\n\n{{greeting}} {{mystery}}\n", encoding="utf-8")
    r = Pipeline(ctx).run_company(CompanyRequest(name="Garage Dupont", email_type="quote"))
    assert r.status == "refused" and "Unknown placeholder" in r.message and not drafts(ctx)


def test_owner_edits_template_and_next_draft_uses_it(ctx, agency):
    p = Pipeline(ctx)
    p.run_company(CompanyRequest(name="Garage Dupont", email_type="quote"))
    (agency / "Templates" / "quote_fr.txt").write_text("Subject: Nouveau devis {{company_name}}\n\n{{greeting}}\nTexte neuf.\n{{signature}}\nRépondez stop pour ne plus recevoir.\n", encoding="utf-8")
    p.run_company(CompanyRequest(name="Garage Dupont", email_type="quote", confirm_duplicate=True))
    assert drafts(ctx)[1]["subject"] == "Nouveau devis Garage Dupont" and "Texte neuf" in drafts(ctx)[1]["body"]


def test_attachment_failure_removes_the_draft(ctx):
    ctx.graph.fail_next = "attach"
    r = Pipeline(ctx).run_company(CompanyRequest(name="Garage Dupont", email_type="quote"))
    assert r.status == "refused" and "removed" in r.message and not drafts(ctx)
    assert ctx.registry.actions()[0].result == "failed"


def test_outlook_down_is_reported_not_claimed(ctx):
    ctx.graph.fail_next = "create"
    r = Pipeline(ctx).run_company(CompanyRequest(name="Garage Dupont", email_type="quote"))
    assert r.status == "refused" and "did not create" in r.message and not drafts(ctx)


def test_large_video_links_or_refuses(ctx, agency, monkeypatch):
    big = agency / "Videos" / f"GarageDupont_Villeurbanne_preview_2026-10-09.mp4"
    big.write_bytes(b"\0" * 1024)
    monkeypatch.setattr(ctx.settings, "MAX_ATTACHMENT_MB", 0)
    r = Pipeline(ctx).run_company(CompanyRequest(name="Garage Dupont", email_type="preview"))
    assert r.status == "refused" and "no sharing link" in r.message
    monkeypatch.setattr(ctx.files, "share_link", lambda f: "https://1drv.ms/v/abc")
    r2 = Pipeline(ctx).run_company(CompanyRequest(name="Garage Dupont", email_type="preview"))
    assert r2.status == "draft_created" and r2.draft["attachment_mode"] == "link"
    assert "https://1drv.ms/v/abc" in drafts(ctx)[0]["body"] and drafts(ctx)[0]["attachments"] == []
    assert any("sharing link" in a for a in r2.attention)


def test_low_confidence_recipient_is_flagged(ctx):
    ctx.registry.upsert(Company(name="Fleuriste Rose", city="Nantes", email="rose@orange.example", email_source="https://dir",
                                email_confidence="low", email_found_at="2099-01-01T00:00:00+00:00"))
    r = Pipeline(ctx).run_company(CompanyRequest(name="Fleuriste Rose", email_type="preview"))
    assert any("VERIFY RECIPIENT" in a for a in r.attention)


def test_batch_continues_after_failure_and_returns_one_report(ctx, monkeypatch):
    p = Pipeline(ctx)
    orig = p.run_company

    def boom(req):
        if req.name == "Garage Dupont":
            raise RuntimeError("kaboom")
        return orig(req)
    monkeypatch.setattr(p, "run_company", boom)
    reply = p.handle("Quote email for Garage Dupont; Boulangerie Martin, Lyon; Fleuriste Rose, Nantes", Session())
    assert reply.startswith("## 3 companies") and "failed" in reply and "draft created" in reply and "no draft" in reply
    assert len(drafts(ctx)) == 1


def test_every_action_is_logged(ctx):
    p, s = Pipeline(ctx), Session()
    p.handle("Quote email for Garage Dupont", s)
    p.handle("Quote email for Garage Dupont", s)
    results = [a.result for a in ctx.registry.actions()]
    assert results[:2] == ["question", "draft_created"]


def test_there_is_no_send_tool():
    assert "send_email" not in TOOL_NAMES and not any("send" in n for n in TOOL_NAMES)


def test_status_text(ctx):
    txt = Pipeline(ctx).status_text()
    assert "Outlook: connected" in txt and "3 videos" in txt and "preview ['fr', 'en']" in txt
