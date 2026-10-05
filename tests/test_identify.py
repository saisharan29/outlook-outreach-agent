import httpx

from outreach.research.crawler import Fetcher
from outreach.research.identify import Candidate, ContactEmail, ContactResearch, Researcher, _name_and_role
from outreach.research.search import Place, SearchHit, SearchProvider

HOME = """<html><head><title>Garage Dupont</title></head><body><a href="/contact">Contact</a>
<footer>info@garage-dupont.fr · 04 72 00 00 00</footer></body></html>"""
CONTACT = """<html><body>Pierre Dupont, directeur – pierre@garage-dupont.fr – 06 11 22 33 44</body></html>"""
DIRECTORY = """<html><body>Garage Dupont Villeurbanne — garage.dupont@orange.fr</body></html>"""


def handler(request):
    host, path = request.url.host, request.url.path
    if host == "garage-dupont.fr":
        body = {"/": HOME, "/contact": CONTACT}.get(path)
    elif host == "pagesjaunes.fr":
        body = DIRECTORY
    else:
        body = None
    if body is None:
        return httpx.Response(404)
    return httpx.Response(200, text=body, headers={"content-type": "text/html"})


class FakePlaces:
    def find(self, query, max_results=3):
        return [Place(name="Garage Dupont", address="12 rue X, 69100 Villeurbanne", phone="+33 4 72 00 00 00",
                      website="https://garage-dupont.fr", source_url="https://maps.google.com/?cid=1")]


class FakeSearch(SearchProvider):
    name = "fake"

    def search(self, query, count=8):
        return [SearchHit("Garage Dupont | PagesJaunes", "https://pagesjaunes.fr/pros/1", ""),
                SearchHit("Garage Dupont", "https://garage-dupont.fr", "")]


def researcher(**kw):
    f = Fetcher(client=httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True))
    return Researcher(fetcher=f, dns_check=False, **kw)


def test_identify_with_website_given():
    c = researcher().identify("Garage Dupont", "Villeurbanne", "garage-dupont.fr")
    assert len(c) == 1 and c[0].website == "https://garage-dupont.fr" and c[0].name == "Garage Dupont"


def test_identify_via_places_then_search():
    assert researcher(places=FakePlaces()).identify("Garage Dupont", "Villeurbanne")[0].source == "Google Business profile"
    via_search = researcher(search=FakeSearch()).identify("Garage Dupont", "Villeurbanne")
    assert [c.website for c in via_search] == ["https://garage-dupont.fr"]   # the directory hit is excluded
    assert researcher().identify("Unknown Co", "Nowhere") == []


def test_find_contacts_prefers_named_decision_maker_with_sources():
    res = researcher(places=FakePlaces()).find_contacts(Candidate(name="Garage Dupont", website="https://garage-dupont.fr",
                                                                   city="Villeurbanne", country="FR"))
    best = res.best_email
    assert best.email == "pierre@garage-dupont.fr" and best.kind == "named"
    assert best.contact_name == "Pierre Dupont" and best.contact_role == "directeur"
    assert best.source_url == "https://garage-dupont.fr/contact" and best.confidence == "high"
    generic = next(e for e in res.emails if e.email == "info@garage-dupont.fr")
    assert generic.kind == "generic"
    assert res.best_phone.phone.e164 == "+33611223344" and res.best_phone.phone.kind == "mobile"
    assert any("maps.google" in s for s in res.sources_checked)


def test_directory_only_result_is_lower_confidence():
    res = researcher(search=FakeSearch()).find_contacts(Candidate(name="Garage Dupont", website="", city="Villeurbanne", country="FR"))
    assert res.best_email.email == "garage.dupont@orange.fr" and res.best_email.where == "directory"
    assert res.best_email.confidence == "medium"


def test_dead_domain_excluded_from_best():
    r = ContactResearch(emails=[ContactEmail("a@dead.fr", "u", "contact page", "high", "named", mx_ok=False),
                                ContactEmail("contact@ok.fr", "u", "footer", "medium", "generic", mx_ok=True)])
    assert r.best_email.email == "contact@ok.fr"


def test_name_and_role_needs_explicit_role_word():
    assert _name_and_role("Jean Martin, gérant : jean@x.fr", "jean") == ("Jean Martin", "gérant")
    assert _name_and_role("écrivez à jean@x.fr pour toute question", "jean") == ("", "")
