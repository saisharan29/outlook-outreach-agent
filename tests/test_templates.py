import pytest

from outreach.templates import (TemplateError, TemplateStore, build_variables, language_for_country, parse_template,
                                render)


def test_parse_requires_subject():
    with pytest.raises(TemplateError):
        parse_template("no subject line\nbody", "preview", "fr")
    t = parse_template("Subject: Hi {{company_name}}\n\nBody {{greeting}} {{signature}}", "preview", "fr")
    assert t.subject == "Hi {{company_name}}" and t.placeholders == {"company_name", "greeting", "signature"}


def test_greeting_fallback_and_named():
    assert build_variables(company_name="X", language="fr")["greeting"] == "Bonjour,"
    assert build_variables(company_name="X", language="en", contact_name="Jane Doe")["greeting"] == "Hello Jane Doe,"


def test_render_fills_everything_and_refuses_unknown_placeholder():
    t = parse_template("Subject: {{company_name}}\n\n{{greeting}}\n{{signature}}\n{{weird}}", "quote", "en")
    with pytest.raises(TemplateError, match="weird"):
        render(t, build_variables(company_name="Acme", language="en", signature="Sig"))


def test_render_refuses_missing_required_values():
    t = parse_template("Subject: {{company_name}}\n\n{{preview_link}}", "preview", "en")
    with pytest.raises(TemplateError, match="preview_link"):
        render(t, build_variables(company_name="Acme", language="en", signature="Sig"))


def test_language_from_country():
    assert language_for_country("FR") == "fr" and language_for_country("BE") == "fr"
    assert language_for_country("DE") == "en" and language_for_country(None, "fr") == "fr"


def test_store_reads_fresh_on_every_call(tmp_path):
    (tmp_path / "quote_fr.txt").write_text("Subject: A\n\nold {{signature}}\n", encoding="utf-8")
    (tmp_path / "signature.txt").write_text("Me", encoding="utf-8")
    store = TemplateStore(tmp_path)
    assert "old" in store.load("quote", "fr").body
    (tmp_path / "quote_fr.txt").write_text("Subject: A\n\nnew {{signature}}\n", encoding="utf-8")
    assert "new" in store.load("quote", "fr").body
    assert store.signature("fr") == "Me" and store.available() == {"preview": [], "quote": ["fr"]}
    with pytest.raises(TemplateError, match="missing"):
        store.load("preview", "en")
