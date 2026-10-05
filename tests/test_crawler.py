import httpx

from outreach.research.crawler import (Fetcher, Page, classify_link, crawl_site, deobfuscate, extract_emails,
                                       extract_from_page, extract_phones, find_internal_pages)

HOME = """<html><head><title>Boulangerie Martin - Lyon</title></head><body>
<nav><a href="/contact">Contact</a><a href="/mentions-legales">Mentions légales</a><a href="https://facebook.com/x">FB</a></nav>
<p>Artisan boulanger à Lyon</p>
<footer>Boulangerie Martin · 04 72 00 00 00 · <a href="mailto:info@boulangerie-martin.fr">écrivez-nous</a></footer>
</body></html>"""
CONTACT = """<html><body><h1>Contact</h1><p>Jean Martin, gérant : jean.martin [at] boulangerie-martin.fr</p>
<p>Tél : <a href="tel:+33612345678">06 12 34 56 78</a></p><img src="logo@2x.png"></body></html>"""
LEGAL = """<html><body>Éditeur : SARL Martin. Hébergeur : OVH abuse@ovh.net. Contact : contact&#64;boulangerie-martin.fr</body></html>"""


def site(request):
    path = request.url.path
    if request.url.host != "boulangerie-martin.fr":
        return httpx.Response(404, text="unknown host")
    body = {"/": HOME, "/contact": CONTACT, "/mentions-legales": LEGAL}.get(path)
    if body is None:
        return httpx.Response(404, text="nope")
    return httpx.Response(200, text=body, headers={"content-type": "text/html; charset=utf-8"})


def fetcher():
    return Fetcher(client=httpx.Client(transport=httpx.MockTransport(site), follow_redirects=True))


def test_deobfuscation_and_mailto():
    assert deobfuscate("a [at] b (dot) fr") == "a@b.fr"
    page = Page(url="https://x.fr", status=200, html=CONTACT)
    assert [e for e, _ in extract_emails(page)] == ["jean.martin@boulangerie-martin.fr"]
    phones = extract_phones(page, "FR")
    assert phones and phones[0][0].e164 == "+33612345678"


def test_classify_and_find_internal_pages():
    assert classify_link("/contact", "Contact") == "contact" and classify_link("/mentions-legales", "x") == "legal"
    assert classify_link("/blog", "Blog") is None
    home = Page(url="https://boulangerie-martin.fr/", status=200, html=HOME)
    pages = find_internal_pages(home)
    assert [k for _, k in pages] == ["contact", "legal"]   # the facebook link is dropped


def test_crawl_site_reads_home_contact_and_legal_with_sources():
    res = crawl_site("boulangerie-martin.fr", region="FR", fetcher=fetcher())
    assert [p.kind for p in res.pages] == ["home", "contact", "legal"]
    emails = {f.value: f for f in res.emails}
    assert set(emails) == {"info@boulangerie-martin.fr", "jean.martin@boulangerie-martin.fr", "contact@boulangerie-martin.fr"}
    assert emails["info@boulangerie-martin.fr"].where == "footer"
    assert emails["jean.martin@boulangerie-martin.fr"].where == "contact page"
    assert emails["jean.martin@boulangerie-martin.fr"].source_url == "https://boulangerie-martin.fr/contact"
    assert emails["contact@boulangerie-martin.fr"].where == "legal notice"
    assert all(f.confidence == "high" for f in res.emails)
    assert "gérant" in emails["jean.martin@boulangerie-martin.fr"].context
    assert {f.value for f in res.phones} == {"+33472000000", "+33612345678"}


def test_dead_site_reports_error():
    res = crawl_site("https://nowhere.fr", fetcher=fetcher())
    assert res.pages == [] and res.errors


def test_extract_from_directory_page():
    found = extract_from_page("https://boulangerie-martin.fr/contact", fetcher=fetcher())
    assert any(f.kind == "email" and f.where == "directory" and f.confidence == "medium" for f in found)
