"""Deterministic page fetching and extraction (FR-07, FR-10, FR-13).

Every email or phone number this module returns was literally present in a page it fetched,
with that page's URL as the source. Nothing is derived from patterns. Page text is data: it is
never executed or treated as an instruction.
"""
from __future__ import annotations

import html as htmllib
import re
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import httpx

from ..contacts.phone import Phone, parse_phone
from ..contacts.validation import is_junk, syntax_ok

USER_AGENT = "Mozilla/5.0 (compatible; OutreachDraftAgent/1.0; +contact research for outreach, no scraping of personal data)"
MAX_BYTES = 2_000_000

# Pages worth reading after the home page, in the order the spec gives (contact, footer, legal notice).
CONTACT_HINTS = ("contact", "contactez", "nous-contacter", "nous-joindre", "kontakt")
LEGAL_HINTS = ("mentions-legales", "mentions_legales", "mentionslegales", "legal", "impressum", "legal-notice",
               "mentions")
ABOUT_HINTS = ("a-propos", "apropos", "about", "qui-sommes-nous", "equipe", "team", "notre-equipe")

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
MAILTO_RE = re.compile(r"mailto:([^\"'?> ]+)", re.I)
TEL_RE = re.compile(r"tel:([+0-9 ().-]{6,})", re.I)
PHONE_RE = re.compile(r"(?:\+|00)?\d[\d .\-()]{7,}\d")
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
LINK_RE = re.compile(r"<a\s[^>]*href=[\"']([^\"'#]+)[\"'][^>]*>(.*?)</a>", re.I | re.S)
FOOTER_RE = re.compile(r"<footer.*?</footer>", re.I | re.S)
OBFUSCATED = [
    (re.compile(r"\s*[\[\(\{]\s*(at|arobase|chez)\s*[\]\)\}]\s*", re.I), "@"),
    (re.compile(r"\s*[\[\(\{]\s*(dot|point)\s*[\]\)\}]\s*", re.I), "."),
    (re.compile(r"&#0*64;|&commat;|%40"), "@"),
]


@dataclass
class Page:
    url: str
    status: int
    html: str = ""
    kind: str = "home"             # "home" | "contact" | "legal" | "about" | "directory" | "other"

    @property
    def title(self) -> str:
        m = TITLE_RE.search(self.html)
        return htmllib.unescape(re.sub(r"\s+", " ", m.group(1))).strip() if m else ""

    @property
    def text(self) -> str:
        return html_to_text(self.html)


@dataclass
class Finding:
    kind: str                       # "email" | "phone"
    value: str                      # email or E.164 phone
    source_url: str
    where: str                      # "contact page" | "footer" | "legal notice" | "home page" | "about page" | "directory"
    confidence: str                 # "high" | "medium" | "low"
    context: str = ""               # a short text window around the value (for name/role extraction)
    phone: Phone | None = None


@dataclass
class CrawlResult:
    website: str
    pages: list[Page] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def emails(self) -> list[Finding]:
        return [f for f in self.findings if f.kind == "email"]

    @property
    def phones(self) -> list[Finding]:
        return [f for f in self.findings if f.kind == "phone"]


def html_to_text(html: str) -> str:
    html = re.sub(r"<(script|style|noscript).*?</\1>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<br\s*/?>|</p>|</div>|</li>|</h[1-6]>|</tr>", "\n", html, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", html)
    text = htmllib.unescape(text)
    text = re.sub(r"[ \t\xa0]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n", text).strip()


def deobfuscate(text: str) -> str:
    for pattern, repl in OBFUSCATED:
        text = pattern.sub(repl, text)
    return text


def normalize_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}{p.path or '/'}".rstrip("/") or url


def domain_of(url: str) -> str:
    host = urlparse(normalize_url(url)).netloc.lower()
    return host[4:] if host.startswith("www.") else host


class Fetcher:
    def __init__(self, timeout: float = 15.0, client: httpx.Client | None = None):
        self.client = client or httpx.Client(timeout=timeout, follow_redirects=True,
                                             headers={"User-Agent": USER_AGENT, "Accept-Language": "fr,en;q=0.8"})

    def get(self, url: str) -> Page:
        try:
            r = self.client.get(url)
            ctype = r.headers.get("content-type", "")
            if "html" not in ctype and "text" not in ctype and "xml" not in ctype:
                return Page(url=str(r.url), status=r.status_code, html="")
            return Page(url=str(r.url), status=r.status_code, html=r.text[:MAX_BYTES])
        except Exception as exc:
            return Page(url=url, status=0, html=f"<!-- fetch error: {type(exc).__name__}: {exc} -->")


def _window(text: str, value: str, width: int = 160) -> str:
    i = text.find(value)
    if i == -1:
        return ""
    return re.sub(r"\s+", " ", text[max(0, i - width): i + len(value) + width]).strip()


def extract_emails(page: Page) -> list[tuple[str, str]]:
    """(email, context) pairs literally present in the page (mailto links first)."""
    found: dict[str, str] = {}
    raw = deobfuscate(page.html)
    text = deobfuscate(page.text)
    for m in MAILTO_RE.findall(raw):
        e = htmllib.unescape(m).strip().lower()
        if syntax_ok(e) and not is_junk(e):
            found.setdefault(e, _window(text, e.split("@")[0]))
    for e in EMAIL_RE.findall(text) + EMAIL_RE.findall(raw):
        e = e.strip(".").lower()
        if syntax_ok(e) and not is_junk(e):
            found.setdefault(e, _window(text, e))
    return list(found.items())


def extract_phones(page: Page, region: str) -> list[tuple[Phone, str]]:
    found: dict[str, tuple[Phone, str]] = {}
    text = page.text
    for m in TEL_RE.findall(page.html):
        p = parse_phone(m, region)
        if p:
            found.setdefault(p.e164, (p, _window(text, m.strip()) or "tel: link"))
    for m in PHONE_RE.findall(text):
        digits = re.sub(r"\D", "", m)
        if len(digits) < 9 or len(digits) > 15:
            continue
        p = parse_phone(m, region)
        if p:
            found.setdefault(p.e164, (p, _window(text, m)))
    return list(found.values())


def classify_link(href: str, label: str) -> str | None:
    h = (href or "").lower()
    l = re.sub(r"\s+", " ", html_to_text(label or "")).lower()
    for kind, hints in (("contact", CONTACT_HINTS), ("legal", LEGAL_HINTS), ("about", ABOUT_HINTS)):
        if any(x in h for x in hints) or any(x in l for x in hints) or (kind == "contact" and l.strip() == "contact"):
            return kind
    return None


def find_internal_pages(home: Page) -> list[tuple[str, str]]:
    base_domain = domain_of(home.url)
    seen: dict[str, str] = {}
    for href, label in LINK_RE.findall(home.html):
        kind = classify_link(href, label)
        if not kind:
            continue
        url = urljoin(home.url, htmllib.unescape(href))
        if domain_of(url) != base_domain or url.lower().endswith((".pdf", ".jpg", ".png")):
            continue
        seen.setdefault(url.split("#")[0], kind)
    order = {"contact": 0, "legal": 1, "about": 2}
    return sorted(seen.items(), key=lambda kv: order[kv[1]])[:6]


WHERE = {"home": "home page", "contact": "contact page", "legal": "legal notice", "about": "about page",
         "directory": "directory", "other": "page"}


def crawl_site(website: str, *, region: str = "FR", fetcher: Fetcher | None = None) -> CrawlResult:
    """Read the company's own site: home, then contact page, legal notice and about page."""
    fetcher = fetcher or Fetcher()
    result = CrawlResult(website=normalize_url(website))
    home = fetcher.get(result.website)
    if home.status == 0 or home.status >= 400:
        result.errors.append(f"{result.website} answered {home.status or 'nothing'}")
        if home.status == 0 and result.website.startswith("https://"):
            home = fetcher.get("http://" + result.website[len("https://"):])
            if home.status == 0 or home.status >= 400:
                return result
            result.errors.clear()
        elif home.status >= 400:
            return result
    home.kind = "home"
    result.pages.append(home)
    for url, kind in find_internal_pages(home):
        page = fetcher.get(url)
        if page.status and page.status < 400 and page.html:
            page.kind = kind
            result.pages.append(page)
    site_domain = domain_of(result.website)
    for page in result.pages:
        where = WHERE[page.kind]
        footer = FOOTER_RE.search(page.html)
        footer_html = deobfuscate(htmllib.unescape(footer.group(0))).lower() if footer else ""
        footer_text = html_to_text(footer.group(0)) if footer else ""
        for email, ctx in extract_emails(page):
            place = "footer" if page.kind == "home" and email in footer_html else where
            same_domain = email.split("@")[1] == site_domain or site_domain.endswith(email.split("@")[1])
            conf = "high" if same_domain or page.kind in ("contact", "legal") else "medium"
            result.findings.append(Finding("email", email, page.url, place, conf, ctx))
        for phone, ctx in extract_phones(page, region):
            place = "footer" if page.kind == "home" and phone.international.replace(" ", "") in footer_text.replace(" ", "") else where
            result.findings.append(Finding("phone", phone.e164, page.url, place, "high", ctx, phone=phone))
    return result


def extract_from_page(url: str, *, region: str = "FR", fetcher: Fetcher | None = None,
                      where: str = "directory", confidence: str = "medium") -> list[Finding]:
    """Emails and phones literally present on one third-party page (directories, FR-07 step 3)."""
    fetcher = fetcher or Fetcher()
    page = fetcher.get(url)
    if page.status == 0 or page.status >= 400 or not page.html:
        return []
    out = [Finding("email", e, page.url, where, confidence, ctx) for e, ctx in extract_emails(page)]
    out += [Finding("phone", p.e164, page.url, where, confidence, ctx, phone=p) for p, ctx in extract_phones(page, region)]
    return out
