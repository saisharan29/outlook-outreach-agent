"""The file naming convention (spec section 7) and tolerant matching (FR-18 to FR-20).

Pattern: CompanyName_City_type_YYYY-MM-DD.ext
    BoulangerieMartin_Lyon_preview_2026-10-02.mp4
    BoulangerieMartin_Lyon_quote_2026-10-05.pdf

Matching is tolerant to accents, capitals, spacing and punctuation: "Boulangerie Martin",
"boulangerie-martin" and "BoulangerieMartin" are the same key. The date picks the latest
version; the city separates companies that share a name.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date

TYPE_ALIASES = {
    "preview": {"preview", "apercu", "aperçu", "video", "demo", "site"},
    "quote": {"quote", "devis", "quotation", "offer", "offre"},
}
VIDEO_EXT = {"mp4", "mov", "m4v", "webm", "mkv", "avi"}
QUOTE_EXT = {"pdf"}

_PATTERN = re.compile(
    r"^(?P<company>[^_]+)_(?P<city>[^_]+)_(?P<type>[^_]+)_(?P<date>\d{4}-\d{2}-\d{2})\.(?P<ext>[A-Za-z0-9]+)$"
)
_LOOSE = re.compile(r"^(?P<company>[^_]+)_(?P<city>[^_]+)_(?P<type>[^_]+)(?:_(?P<rest>.*))?\.(?P<ext>[A-Za-z0-9]+)$")


def normalize(text: str) -> str:
    """Lower-case ASCII with nothing but letters and digits: the comparison key."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]", "", text.lower())


def canonical_type(raw: str) -> str | None:
    key = normalize(raw)
    for canon, aliases in TYPE_ALIASES.items():
        if key in {normalize(a) for a in aliases}:
            return canon
    return None


@dataclass(frozen=True)
class ParsedName:
    filename: str
    company: str
    city: str
    type: str                 # "preview" | "quote"
    date: date | None
    ext: str
    strict: bool              # True when the name follows the convention exactly

    @property
    def company_key(self) -> str:
        return normalize(self.company)

    @property
    def city_key(self) -> str:
        return normalize(self.city)


def parse_filename(filename: str) -> ParsedName | None:
    """Parse one file name. Returns None when it does not follow the convention at all."""
    m = _PATTERN.match(filename)
    strict = True
    if not m:
        m = _LOOSE.match(filename)
        strict = False
        if not m:
            return None
    ftype = canonical_type(m.group("type"))
    if not ftype:
        return None
    d = None
    if strict:
        try:
            d = date.fromisoformat(m.group("date"))
        except ValueError:
            strict = False
    return ParsedName(filename=filename, company=m.group("company"), city=m.group("city"),
                      type=ftype, date=d, ext=m.group("ext").lower(), strict=strict)


def expected_extension_ok(parsed: ParsedName) -> bool:
    return parsed.ext in (VIDEO_EXT if parsed.type == "preview" else QUOTE_EXT)


@dataclass
class MatchResult:
    """The outcome of matching files to one company (FR-18 to FR-20)."""
    status: str                           # "match" | "none" | "ambiguous"
    chosen: ParsedName | None = None
    versions: list[ParsedName] | None = None   # every version of the chosen company, newest first
    candidates: list[ParsedName] | None = None # competing companies (ambiguous) or closest names (none)
    note: str = ""


def _similar(a: str, b: str) -> float:
    """Cheap similarity in [0, 1] for 'closest names' suggestions."""
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if a in b or b in a:
        return 0.85
    # Dice coefficient on character bigrams
    ba = {a[i:i + 2] for i in range(len(a) - 1)}
    bb = {b[i:i + 2] for i in range(len(b) - 1)}
    if not ba or not bb:
        return 0.0
    return 2 * len(ba & bb) / (len(ba) + len(bb))


def match_files(filenames: list[str], company: str, file_type: str, city: str | None = None,
                aliases: list[str] | None = None) -> MatchResult:
    """Pick the file for `company` of `file_type` among `filenames`.

    - Exact key match on company (and on city when the owner gave one, or when needed to
      separate two companies with the same name).
    - Several versions of the same company+city: the most recent date wins (FR-19).
    - Two different companies could match: stop and ask (FR-20). A file is never picked
      between two companies.
    """
    keys = {normalize(company)} | {normalize(a) for a in (aliases or []) if a}
    keys.discard("")
    parsed = [p for p in (parse_filename(f) for f in filenames) if p and p.type == file_type]
    exact = [p for p in parsed if p.company_key in keys]
    if city:
        city_key = normalize(city)
        with_city = [p for p in exact if p.city_key == city_key]
        # If the owner named a city and files of that city exist, only they count.
        if with_city:
            exact = with_city
    if not exact:
        scored = sorted(parsed, key=lambda p: max(_similar(p.company_key, k) for k in keys), reverse=True)
        closest = [p for p in scored if max(_similar(p.company_key, k) for k in keys) >= 0.5][:5]
        return MatchResult(status="none", candidates=closest,
                           note="No file follows the convention for this company.")
    groups: dict[tuple[str, str], list[ParsedName]] = {}
    for p in exact:
        groups.setdefault((p.company_key, p.city_key), []).append(p)
    if len(groups) > 1:
        reps = [sorted(g, key=lambda p: (p.date or date.min), reverse=True)[0] for g in groups.values()]
        return MatchResult(status="ambiguous", candidates=reps,
                           note="Files for more than one company (or city) match this name.")
    versions = sorted(exact, key=lambda p: (p.date or date.min, p.filename), reverse=True)
    chosen = versions[0]
    note = ""
    if len(versions) > 1:
        note = (f"{len(versions)} versions found; picked the most recent ({chosen.filename})."
                if chosen.date else f"{len(versions)} versions found but no dates; picked {chosen.filename}.")
    if not expected_extension_ok(chosen):
        note = (note + " " if note else "") + f"Unexpected extension .{chosen.ext} for a {file_type} file."
    return MatchResult(status="match", chosen=chosen, versions=versions, note=note.strip())
