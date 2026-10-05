"""Email validation (FR-12): syntax, then an MX lookup so a dead domain never becomes a recipient."""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

EMAIL_RE = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@([A-Za-z0-9-]+\.)+[A-Za-z]{2,}$")

# Addresses that are never a company contact, even when they appear on its site.
JUNK_LOCALPARTS = {"noreply", "no-reply", "donotreply", "example", "test", "webmaster", "postmaster",
                   "abuse", "privacy", "dpo", "rgpd", "gdpr", "unsubscribe", "newsletter"}
JUNK_DOMAINS = {"example.com", "example.org", "sentry.io", "wixpress.com", "domain.com", "email.com",
                "yourdomain.com", "mail.com", "company.com", "site.com", "w3.org", "schema.org"}
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp")


@dataclass(frozen=True)
class EmailCheck:
    email: str
    syntax_ok: bool
    domain: str
    mx_ok: bool | None      # None when DNS could not be queried at all
    detail: str

    @property
    def deliverable(self) -> bool:
        return self.syntax_ok and self.mx_ok is not False


def syntax_ok(email: str) -> bool:
    return bool(EMAIL_RE.match(email or "")) and ".." not in email


def is_junk(email: str) -> bool:
    e = email.lower()
    local, _, domain = e.partition("@")
    if e.endswith(IMAGE_EXT):
        return True
    if local in JUNK_LOCALPARTS or domain in JUNK_DOMAINS:
        return True
    return any(local.startswith(p) for p in ("noreply", "no-reply", "no_reply"))


@lru_cache(maxsize=512)
def domain_accepts_mail(domain: str) -> tuple[bool | None, str]:
    """(True, detail) when the domain has MX records (or an A/AAAA fallback), (False, detail) when it
    cannot receive mail, (None, detail) when DNS was unreachable."""
    try:
        import dns.resolver  # dnspython
    except ImportError:  # pragma: no cover
        return None, "dnspython not installed"
    resolver = dns.resolver.Resolver()
    resolver.lifetime = 5.0
    try:
        answers = resolver.resolve(domain, "MX")
        hosts = [str(r.exchange).rstrip(".") for r in answers]
        if hosts and hosts != ["", "."] and not all(h in ("", ".") for h in hosts):
            return True, f"MX: {', '.join(hosts[:3])}"
        return False, "MX record is null (domain refuses mail)"
    except dns.resolver.NoAnswer:
        for rtype in ("A", "AAAA"):
            try:
                resolver.resolve(domain, rtype)
                return True, f"no MX but an {rtype} record exists (implicit MX)"
            except Exception:
                continue
        return False, "no MX, A or AAAA record"
    except dns.resolver.NXDOMAIN:
        return False, "domain does not exist"
    except Exception as exc:  # timeouts, no nameservers
        return None, f"DNS lookup failed: {type(exc).__name__}"


def check_email(email: str, *, dns_check: bool = True) -> EmailCheck:
    email = (email or "").strip().strip(".,;:<>()[]\"'")
    ok = syntax_ok(email)
    domain = email.rsplit("@", 1)[-1].lower() if "@" in email else ""
    if not ok:
        return EmailCheck(email=email, syntax_ok=False, domain=domain, mx_ok=None, detail="invalid format")
    if is_junk(email):
        return EmailCheck(email=email, syntax_ok=False, domain=domain, mx_ok=None, detail="not a contact address")
    if not dns_check:
        return EmailCheck(email=email, syntax_ok=True, domain=domain, mx_ok=None, detail="DNS check skipped")
    mx, detail = domain_accepts_mail(domain)
    return EmailCheck(email=email, syntax_ok=True, domain=domain, mx_ok=mx, detail=detail)
