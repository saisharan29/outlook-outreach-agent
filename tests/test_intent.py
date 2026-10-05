import pytest

from outreach.agent.intent import parse_regex, resolve_answer
from outreach.agent.models import CompanyRequest, Question


@pytest.mark.parametrize("text,etype,name,city", [
    ("Preview email for Boulangerie Martin, Lyon", "preview", "Boulangerie Martin", "Lyon"),
    ("Quote email for Garage Dupont", "quote", "Garage Dupont", ""),
    ("Devis pour Garage Dupont", "quote", "Garage Dupont", ""),
    ("Email d'aperçu pour la Boulangerie Martin à Lyon", "preview", "Boulangerie Martin", "Lyon"),
    ("Fais un devis pour Fleuriste Rose (Nantes)", "quote", "Fleuriste Rose", "Nantes"),
    ("preview Café Léon, Lyon", "preview", "Café Léon", "Lyon"),
    ("Create a quote email for Pizza Roma in Marseille", "quote", "Pizza Roma", "Marseille"),
    ("Mail de devis : Garage Dupont, Villeurbanne", "quote", "Garage Dupont", "Villeurbanne"),
])
def test_single_requests(text, etype, name, city):
    i = parse_regex(text)
    assert i.kind == "draft" and i.email_type == etype
    assert i.companies[0].name == name and i.companies[0].city == city


def test_missing_type_is_not_assumed():
    i = parse_regex("Email for Garage Dupont")
    assert i.kind == "draft" and i.email_type == "" and i.companies[0].name == "Garage Dupont"


def test_batch_and_extras():
    i = parse_regex("Devis pour Garage Dupont; Boulangerie Martin, Lyon; Fleuriste Rose, Nantes, site: fleuriste-rose.fr")
    assert [c.name for c in i.companies] == ["Garage Dupont", "Boulangerie Martin", "Fleuriste Rose"]
    assert i.companies[2].website == "fleuriste-rose.fr" and i.companies[1].city == "Lyon"
    j = parse_regex("Preview email for Café Léon, Lyon, email: leon@cafeleon.fr, in English")
    assert j.companies[0].owner_email == "leon@cafeleon.fr" and j.language == "en" and j.companies[0].city == "Lyon"
    k = parse_regex("preview email for A Co, Lyon and B Co, Paris")
    assert [c.name for c in k.companies] == ["A Co", "B Co"]


def test_do_not_contact_help_status():
    assert parse_regex("Do not contact Garage Dupont").kind == "do_not_contact"
    assert parse_regex("Ne plus contacter Garage Dupont").companies[0].name == "Garage Dupont"
    assert parse_regex("help").kind == "help" and parse_regex("status").kind == "status"
    assert parse_regex("   ").kind == "unknown"


def test_resolve_answers():
    req = CompanyRequest(name="X", email_type="preview")
    q = Question(kind="confirm_duplicate", text="?", options=[], request=req)
    assert resolve_answer("oui", q).confirm_duplicate and resolve_answer("no", q) is None
    assert resolve_answer("Preview email for Y", q) == "unrelated"
    q2 = Question(kind="choose_company", text="?", options=["A — Lyon", "B — Paris"], request=CompanyRequest(name="X", email_type="quote"))
    assert resolve_answer("2", q2).chosen_candidate == 1 and resolve_answer("paris", q2).chosen_candidate == 1
    assert resolve_answer("9", q2) == "unrelated"
    q3 = Question(kind="email_type", text="?", options=[], request=CompanyRequest(name="X"))
    assert resolve_answer("devis", q3).email_type == "quote"
    q4 = Question(kind="choose_file", text="?", options=["A_B_preview_2026-01-01.mp4"], request=CompanyRequest(name="X", email_type="preview"))
    assert resolve_answer("1", q4).chosen_file == "A_B_preview_2026-01-01.mp4"
