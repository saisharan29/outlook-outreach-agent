"""WhatsApp presence (FR-14 to FR-16), section 6 options B + C by default, A when configured.

- B: a wa.me click-to-chat link so the owner confirms in one tap.
- C: mobile numbers are "likely", landlines "unlikely" — a heuristic, never reported as a check.
- A: an optional third-party validator (HTTP) when WHATSAPP_VALIDATOR_URL is set. Unofficial,
  paid per check; the owner chooses whether to enable it.

Reported value is one of: "yes", "no", "unverified" (FR-14), with a `hint` for the heuristic.
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx

from .phone import Phone


@dataclass(frozen=True)
class WhatsAppStatus:
    status: str          # "yes" | "no" | "unverified"
    hint: str            # "mobile, WhatsApp likely" | "landline, WhatsApp unlikely" | ...
    link: str            # https://wa.me/33612345678
    method: str          # "validator" | "heuristic"

    @property
    def label(self) -> str:
        return {"yes": "on WhatsApp", "no": "not on WhatsApp", "unverified": "could not verify"}[self.status]


def wa_link(phone: Phone) -> str:
    return f"https://wa.me/{phone.digits}"


def heuristic(phone: Phone) -> WhatsAppStatus:
    if phone.kind == "mobile":
        hint = "mobile number, WhatsApp likely"
    elif phone.kind == "landline":
        hint = "landline, WhatsApp unlikely"
    else:
        hint = "number type unknown"
    return WhatsAppStatus(status="unverified", hint=hint, link=wa_link(phone), method="heuristic")


def check_whatsapp(phone: Phone, *, validator_url: str = "", validator_key: str = "",
                   timeout: float = 10.0, client: httpx.Client | None = None) -> WhatsAppStatus:
    base = heuristic(phone)
    if not validator_url:
        return base
    try:
        c = client or httpx.Client(timeout=timeout)
        r = c.get(validator_url, params={"phone": phone.digits},
                  headers={"Authorization": f"Bearer {validator_key}"} if validator_key else {})
        if r.status_code != 200:
            return WhatsAppStatus(status="unverified", hint=f"{base.hint}; validator answered {r.status_code}",
                                  link=base.link, method="validator")
        data = r.json()
        value = data.get("whatsapp", data.get("exists", data.get("status")))
        if value in (True, "yes", "true", "valid", "exists"):
            return WhatsAppStatus(status="yes", hint="confirmed by validator", link=base.link, method="validator")
        if value in (False, "no", "false", "invalid", "not_exists"):
            return WhatsAppStatus(status="no", hint="validator says no account", link=base.link, method="validator")
        return WhatsAppStatus(status="unverified", hint=f"{base.hint}; validator gave no answer",
                              link=base.link, method="validator")
    except Exception as exc:
        return WhatsAppStatus(status="unverified", hint=f"{base.hint}; validator unreachable ({type(exc).__name__})",
                              link=base.link, method="validator")
