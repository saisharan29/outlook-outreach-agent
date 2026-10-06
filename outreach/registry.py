"""Client registry and action log (spec sections 4.6, 7 and FR-28), stored in SQLite inside the
owner's Registry folder. One row per company; one row per action. A CSV export exists for the
owner to open in Excel.
"""
from __future__ import annotations

import csv
import json
import sqlite3
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .naming import normalize

SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL,                 -- normalized name
    city_key TEXT NOT NULL DEFAULT '', -- normalized city
    name TEXT NOT NULL,
    aliases TEXT NOT NULL DEFAULT '[]',
    city TEXT NOT NULL DEFAULT '',
    country TEXT NOT NULL DEFAULT '',
    website TEXT NOT NULL DEFAULT '',
    contact_name TEXT NOT NULL DEFAULT '',
    contact_role TEXT NOT NULL DEFAULT '',
    email TEXT NOT NULL DEFAULT '',
    email_source TEXT NOT NULL DEFAULT '',
    email_confidence TEXT NOT NULL DEFAULT '',
    email_found_at TEXT NOT NULL DEFAULT '',
    phone TEXT NOT NULL DEFAULT '',
    phone_source TEXT NOT NULL DEFAULT '',
    phone_confidence TEXT NOT NULL DEFAULT '',
    phone_found_at TEXT NOT NULL DEFAULT '',
    whatsapp_status TEXT NOT NULL DEFAULT '',
    whatsapp_checked_at TEXT NOT NULL DEFAULT '',
    preview_drafted_at TEXT NOT NULL DEFAULT '',
    preview_file TEXT NOT NULL DEFAULT '',
    quote_drafted_at TEXT NOT NULL DEFAULT '',
    quote_file TEXT NOT NULL DEFAULT '',
    do_not_contact INTEGER NOT NULL DEFAULT 0,
    do_not_contact_reason TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT '',
    UNIQUE(key, city_key)
);
CREATE TABLE IF NOT EXISTS actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL,
    company TEXT NOT NULL,
    email_type TEXT NOT NULL DEFAULT '',
    recipient TEXT NOT NULL DEFAULT '',
    file TEXT NOT NULL DEFAULT '',
    result TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT ''
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class Company:
    name: str
    city: str = ""
    country: str = ""
    website: str = ""
    aliases: list[str] = field(default_factory=list)
    contact_name: str = ""
    contact_role: str = ""
    email: str = ""
    email_source: str = ""
    email_confidence: str = ""
    email_found_at: str = ""
    phone: str = ""
    phone_source: str = ""
    phone_confidence: str = ""
    phone_found_at: str = ""
    whatsapp_status: str = ""
    whatsapp_checked_at: str = ""
    preview_drafted_at: str = ""
    preview_file: str = ""
    quote_drafted_at: str = ""
    quote_file: str = ""
    do_not_contact: bool = False
    do_not_contact_reason: str = ""
    updated_at: str = ""
    id: int | None = None

    @property
    def key(self) -> str:
        return normalize(self.name)

    def contact_is_recent(self, max_age_days: int) -> bool:
        """FR-10 / section 7: details older than the configured age are re-checked."""
        stamp = self.email_found_at or self.phone_found_at
        if not stamp:
            return False
        try:
            found = datetime.fromisoformat(stamp)
        except ValueError:
            return False
        if found.tzinfo is None:
            found = found.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - found <= timedelta(days=max_age_days)

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("id", None)
        return d


@dataclass
class Action:
    at: str
    company: str
    email_type: str
    recipient: str
    file: str
    result: str
    detail: str = ""
    id: int | None = None


class Registry:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.lock = threading.RLock()

    # --- companies ---------------------------------------------------------
    @staticmethod
    def _row_to_company(r: sqlite3.Row) -> Company:
        d = dict(r)
        d["aliases"] = json.loads(d.get("aliases") or "[]")
        d["do_not_contact"] = bool(d.get("do_not_contact"))
        d.pop("key", None); d.pop("city_key", None)
        return Company(**d)

    def find(self, name: str, city: str | None = None) -> list[Company]:
        """Every company whose name or alias matches; narrowed by city when given."""
        key = normalize(name)
        with self.lock:
            rows = self.conn.execute("SELECT * FROM companies").fetchall()
        out = []
        for r in rows:
            aliases = {normalize(a) for a in json.loads(r["aliases"] or "[]")}
            if key == r["key"] or key in aliases:
                if city and normalize(city) != r["city_key"] and r["city_key"]:
                    continue
                out.append(self._row_to_company(r))
        return out

    def get(self, name: str, city: str = "") -> Company | None:
        with self.lock:
            r = self.conn.execute("SELECT * FROM companies WHERE key=? AND city_key=?",
                              (normalize(name), normalize(city))).fetchone()
        return self._row_to_company(r) if r else None

    def upsert(self, c: Company) -> Company:
        with self.lock:
            return self._upsert(c)

    def _upsert(self, c: Company) -> Company:
        c.updated_at = now_iso()
        cols = c.to_dict()
        cols["aliases"] = json.dumps(sorted({a for a in c.aliases if a}))
        cols["do_not_contact"] = int(c.do_not_contact)
        cols["key"], cols["city_key"] = c.key, normalize(c.city)
        names = ", ".join(cols)
        marks = ", ".join("?" for _ in cols)
        updates = ", ".join(f"{k}=excluded.{k}" for k in cols if k not in ("key", "city_key"))
        self.conn.execute(f"INSERT INTO companies ({names}) VALUES ({marks}) "
                          f"ON CONFLICT(key, city_key) DO UPDATE SET {updates}", list(cols.values()))
        self.conn.commit()
        stored = self.get(c.name, c.city)
        assert stored is not None
        return stored

    def set_do_not_contact(self, name: str, city: str = "", reason: str = "asked to stop") -> Company:
        c = self.get(name, city) or Company(name=name, city=city)
        c.do_not_contact, c.do_not_contact_reason = True, reason
        return self.upsert(c)

    def all_companies(self) -> list[Company]:
        with self.lock:
            return [self._row_to_company(r) for r in self.conn.execute("SELECT * FROM companies ORDER BY name")]

    # --- action log (FR-28) --------------------------------------------------
    def log(self, *, company: str, result: str, email_type: str = "", recipient: str = "",
            file: str = "", detail: str = "") -> Action:
        with self.lock:
            return self._log(company=company, result=result, email_type=email_type, recipient=recipient,
                             file=file, detail=detail)

    def _log(self, *, company: str, result: str, email_type: str = "", recipient: str = "",
             file: str = "", detail: str = "") -> Action:
        a = Action(at=now_iso(), company=company, email_type=email_type, recipient=recipient,
                   file=file, result=result, detail=detail)
        cur = self.conn.execute(
            "INSERT INTO actions (at, company, email_type, recipient, file, result, detail) VALUES (?,?,?,?,?,?,?)",
            (a.at, a.company, a.email_type, a.recipient, a.file, a.result, a.detail))
        self.conn.commit()
        a.id = cur.lastrowid
        return a

    def actions(self, limit: int = 200) -> list[Action]:
        with self.lock:
            rows = self.conn.execute("SELECT * FROM actions ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [Action(**dict(r)) for r in rows]

    # --- export ----------------------------------------------------------------
    def export_csv(self, folder: Path | None = None) -> tuple[Path, Path]:
        folder = Path(folder or self.path.parent)
        comp, acts = folder / "registry.csv", folder / "actions.csv"
        with comp.open("w", newline="", encoding="utf-8") as f:
            rows = [c.to_dict() for c in self.all_companies()]
            w = csv.DictWriter(f, fieldnames=list(Company(name="").to_dict().keys()))
            w.writeheader()
            for r in rows:
                r["aliases"] = "; ".join(r["aliases"])
                w.writerow(r)
        with acts.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["date", "company", "email_type", "recipient", "file", "result", "detail"])
            for a in reversed(self.actions(limit=100000)):
                w.writerow([a.at, a.company, a.email_type, a.recipient, a.file, a.result, a.detail])
        return comp, acts

    def close(self) -> None:
        self.conn.close()
