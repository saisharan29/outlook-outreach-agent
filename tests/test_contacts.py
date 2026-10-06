import httpx

from outreach.contacts import validation
from outreach.contacts.phone import parse_phone
from outreach.contacts.validation import check_email, is_junk, syntax_ok
from outreach.contacts.whatsapp import check_whatsapp, heuristic


def test_phone_international_format_and_kind():
    p = parse_phone("06 12 34 56 78", "FR")
    assert p.e164 == "+33612345678" and p.international == "+33 6 12 34 56 78" and p.kind == "mobile"
    assert parse_phone("04 72 00 00 00", "FR").kind == "landline"
    assert parse_phone("+44 20 7946 0958", "FR").country == "GB"
    assert parse_phone("12345", "FR") is None
    # Luxembourg: 621 / 661 / 691 are mobiles, 2x / 4x are landlines
    lu = parse_phone("691 817 815", "LU")
    assert lu.e164 == "+352691817815" and lu.kind == "mobile" and lu.international == "+352 691 817 815"
    assert parse_phone("661 123 456", "LU").kind == "mobile" and parse_phone("621 123 456", "LU").kind == "mobile"
    assert parse_phone("26 12 34 56", "LU").kind == "landline"


def test_email_syntax_and_junk():
    assert syntax_ok("contact@boulangerie-martin.fr") and not syntax_ok("not-an-email") and not syntax_ok("a..b@x.fr")
    assert is_junk("noreply@x.fr") and is_junk("logo@2x.png") and is_junk("user@example.com")
    assert not is_junk("jean.martin@boulangerie.fr")


def test_check_email_uses_mx(monkeypatch):
    monkeypatch.setattr(validation, "domain_accepts_mail", lambda d: (False, "domain does not exist"))
    c = check_email("x@dead.invalid")
    assert c.syntax_ok and c.mx_ok is False and not c.deliverable
    monkeypatch.setattr(validation, "domain_accepts_mail", lambda d: (True, "MX: mx.x"))
    assert check_email("x@live.fr").deliverable
    assert check_email("x@live.fr", dns_check=False).mx_ok is None


def test_whatsapp_heuristic_and_link():
    st = heuristic(parse_phone("06 12 34 56 78", "FR"))
    assert st.status == "unverified" and "likely" in st.hint and st.link == "https://wa.me/33612345678"
    land = heuristic(parse_phone("04 72 00 00 00", "FR"))
    assert "unlikely" in land.hint and land.label == "could not verify"


def test_whatsapp_validator_option_a():
    def handler(request):
        assert request.headers["Authorization"] == "Bearer k"
        return httpx.Response(200, json={"whatsapp": request.url.params["phone"] == "33612345678"})
    client = httpx.Client(transport=httpx.MockTransport(handler))
    yes = check_whatsapp(parse_phone("+33612345678", "FR"), validator_url="https://v.test/check", validator_key="k", client=client)
    no = check_whatsapp(parse_phone("+33472000000", "FR"), validator_url="https://v.test/check", validator_key="k", client=client)
    assert yes.status == "yes" and no.status == "no" and yes.method == "validator"
    down = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    assert check_whatsapp(parse_phone("+33612345678", "FR"), validator_url="https://v.test", client=down).status == "unverified"
