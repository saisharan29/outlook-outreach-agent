from datetime import datetime, timedelta, timezone

from outreach.registry import Company, Registry


def test_upsert_find_aliases_and_city(tmp_path):
    r = Registry(tmp_path / "r.sqlite")
    r.upsert(Company(name="Boulangerie Martin", city="Lyon", aliases=["Martin"], email="a@b.fr"))
    r.upsert(Company(name="Boulangerie Martin", city="Paris"))
    assert len(r.find("boulangerie martin")) == 2
    assert r.find("martin", "Lyon")[0].email == "a@b.fr"
    assert r.get("Boulangerie Martin", "Paris").city == "Paris"
    r.upsert(Company(name="Boulangerie Martin", city="Lyon", aliases=["Martin"], email="new@b.fr"))
    assert r.get("Boulangerie Martin", "Lyon").email == "new@b.fr" and len(r.all_companies()) == 2


def test_contact_recency(tmp_path):
    old = (datetime.now(timezone.utc) - timedelta(days=120)).isoformat()
    c = Company(name="X", email="x@y.fr", email_found_at=old)
    assert not c.contact_is_recent(90) and c.contact_is_recent(365)
    assert not Company(name="Y").contact_is_recent(90)


def test_do_not_contact_log_and_export(tmp_path):
    r = Registry(tmp_path / "r.sqlite")
    r.set_do_not_contact("Garage Dupont", reason="asked by phone")
    assert r.get("Garage Dupont").do_not_contact
    r.log(company="Garage Dupont", email_type="quote", recipient="a@b.fr", file="f.pdf", result="refused")
    assert r.actions()[0].result == "refused"
    comp, acts = r.export_csv(tmp_path)
    assert "Garage Dupont" in comp.read_text() and "refused" in acts.read_text()
