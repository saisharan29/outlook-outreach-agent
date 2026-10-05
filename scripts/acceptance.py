"""Acceptance run for section 10 of the specification, without creating a single draft.

    python scripts/acceptance.py companies.csv            # research only, prints the table and the hit rate
    python scripts/acceptance.py companies.csv --out results.csv

companies.csv columns: name, city (optional), website (optional), expected_email (optional).
A company counts as a hit when an email with a source was found; when expected_email is given,
it must match. Target in the spec: at least 80 % of the 20 test companies without the owner's help.
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from outreach.agent.context import build_context      # noqa: E402
from outreach.agent.tools import Tools                  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    rows = list(csv.DictReader(open(args.csv, encoding="utf-8-sig")))
    ctx = build_context()
    tools = Tools(ctx)
    results = []
    for r in rows:
        name, city, website = r.get("name", "").strip(), r.get("city", "").strip(), r.get("website", "").strip()
        expected = (r.get("expected_email") or "").strip().lower()
        t0 = time.time()
        out = {"name": name, "city": city, "identified": "", "website": "", "email": "", "confidence": "",
               "source": "", "phone": "", "whatsapp": "", "hit": "no", "seconds": 0, "note": ""}
        try:
            ident = tools.identify_company(name, city, website)
            out["identified"] = ident["status"]
            if ident["status"] == "identified":
                comp = ident["company"]
                out["website"] = comp.get("website", "")
                found = tools.find_contacts(comp, force_refresh=True)
                e, p = found.get("email"), found.get("phone")
                if e:
                    out.update(email=e["address"], confidence=e["confidence"], source=e["source"])
                    out["hit"] = "yes" if (not expected or expected == e["address"].lower()) else "wrong"
                if p:
                    wa = tools.check_whatsapp(p["e164"])
                    out["phone"], out["whatsapp"] = p["international"], wa["status"]
                out["note"] = "; ".join(found.get("notes", []))[:200]
            elif ident["status"] == "ambiguous":
                out["note"] = f"{len(ident['candidates'])} candidates: " + ", ".join(
                    f"{c.get('name')} ({c.get('city')})" for c in ident["candidates"][:4])
            else:
                out["note"] = ident.get("note", "")
        except Exception as exc:
            out["note"] = f"{type(exc).__name__}: {exc}"
        out["seconds"] = round(time.time() - t0, 1)
        results.append(out)
        print(f"{out['hit']:>5}  {name:<32} {out['email']:<40} {out['confidence']:<7} {out['seconds']:>5}s  {out['note'][:60]}")
    hits = sum(1 for x in results if x["hit"] == "yes")
    print(f"\n{hits}/{len(results)} companies with a correct email ({100 * hits / max(1, len(results)):.0f} %). "
          f"Spec target: 80 %. Slowest: {max((x['seconds'] for x in results), default=0)} s (limit 120 s).")
    if args.out:
        with open(args.out, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(results[0].keys()) if results else ["name"])
            w.writeheader()
            w.writerows(results)
        print("Written", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
