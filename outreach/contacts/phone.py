"""Phone numbers in international format (FR-09) and the mobile/landline heuristic (FR-16)."""
from __future__ import annotations

from dataclasses import dataclass

import phonenumbers
from phonenumbers import PhoneNumberType, NumberParseException


@dataclass(frozen=True)
class Phone:
    e164: str            # +33612345678
    international: str   # +33 6 12 34 56 78
    kind: str            # "mobile" | "landline" | "unknown"
    country: str         # ISO region, e.g. "FR"

    @property
    def digits(self) -> str:
        return self.e164.lstrip("+")


def parse_phone(raw: str, default_region: str = "FR") -> Phone | None:
    """None when the text is not a valid phone number for its region."""
    if not raw:
        return None
    try:
        num = phonenumbers.parse(raw, default_region.upper())
    except NumberParseException:
        return None
    if not phonenumbers.is_valid_number(num):
        return None
    t = phonenumbers.number_type(num)
    if t in (PhoneNumberType.MOBILE, PhoneNumberType.FIXED_LINE_OR_MOBILE):
        kind = "mobile" if t == PhoneNumberType.MOBILE else "unknown"
    elif t == PhoneNumberType.FIXED_LINE:
        kind = "landline"
    else:
        kind = "unknown"
    return Phone(
        e164=phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164),
        international=phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.INTERNATIONAL),
        kind=kind,
        country=phonenumbers.region_code_for_number(num) or default_region.upper(),
    )
