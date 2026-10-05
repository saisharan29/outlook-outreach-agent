"""Builds a sample Agency folder: templates in both languages, a signature, two companies with
sample files and registry rows, so the whole flow can be tried without any account or key."""
from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

from .registry import Company, Registry, now_iso

TEMPLATES = {
    "preview_fr.txt": """Subject: Votre nouveau site web — {{company_name}}

{{greeting}}

Nous avons préparé un aperçu d'un site web pour {{company_name}}, conçu pour présenter votre activité
à {{city}} et attirer de nouveaux clients. La vidéo ci-jointe vous le montre en une minute.
{{preview_link}}

Si vous souhaitez le voir en ligne ou en discuter, répondez simplement à cet e-mail.

{{signature}}

Vous recevez ce message car votre entreprise est publiquement référencée. Répondez « stop » pour ne plus recevoir de message de notre part.
""",
    "preview_en.txt": """Subject: Your new website — {{company_name}}

{{greeting}}

We have prepared a preview of a website for {{company_name}}, designed to present your business
in {{city}} and bring you new customers. The attached video shows it in one minute.
{{preview_link}}

If you would like to see it live or talk about it, simply reply to this email.

{{signature}}

You receive this message because your business is publicly listed. Reply "stop" to opt out of any further message.
""",
    "quote_fr.txt": """Subject: Devis pour le site web de {{company_name}}

{{greeting}}

Merci pour votre intérêt. Vous trouverez ci-joint le devis pour le site web de {{company_name}},
avec le détail des prestations et des délais.

Je reste à votre disposition pour toute question ou ajustement.

{{signature}}

Pour ne plus recevoir de message de notre part, répondez « stop ».
""",
    "quote_en.txt": """Subject: Quote for the {{company_name}} website

{{greeting}}

Thank you for your interest. Please find attached the quote for the {{company_name}} website,
with the details of the work and the timeline.

I am available for any question or adjustment.

{{signature}}

To opt out of further messages, reply "stop".
""",
    "signature_fr.txt": """Sai Sharan
Studio Web — création de sites pour les commerces
+33 6 00 00 00 00 · studio@example.com
""",
    "signature_en.txt": """Sai Sharan
Studio Web — websites for local businesses
+33 6 00 00 00 00 · studio@example.com
""",
    "agency.txt": "Studio Web\n",
    "README.txt": """Templates — edit these files freely; the next draft uses the new wording.
Layout: first line "Subject: …", a blank line, then the body.
Placeholders: {{company_name}} {{contact_name}} {{greeting}} {{city}} {{preview_link}} {{signature}} {{agency_name}}
{{greeting}} becomes "Bonjour Jean Martin," when the contact name is known, "Bonjour," otherwise.
Each template exists in French (_fr) and English (_en); the language follows the company's country unless you say
"in English" / "en français" in the request. Keep the opt-out sentence: cold B2B email needs one.
""",
}
NAMING_README = """Name files exactly like this, in this folder:
    CompanyName_City_preview_YYYY-MM-DD.mp4      (Videos)
    CompanyName_City_quote_YYYY-MM-DD.pdf        (Quotes)
No spaces in the company name (BoulangerieMartin, not Boulangerie Martin). Accents and capitals do not matter.
The date lets the agent pick the latest version; the city separates two companies with the same name.
"""

_MIN_PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n" \
           b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 100]>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"


def build_demo(root: Path) -> Path:
    root = Path(root)
    for sub in ("Videos", "Quotes", "Templates", "Registry"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    for name, text in TEMPLATES.items():
        (root / "Templates" / name).write_text(text, encoding="utf-8")
    (root / "Videos" / "README.txt").write_text(NAMING_README, encoding="utf-8")
    (root / "Quotes" / "README.txt").write_text(NAMING_README, encoding="utf-8")
    today = date.today().isoformat()
    # Two versions of the Martin video (the latest wins), one quote, one Dupont video.
    (root / "Videos" / "BoulangerieMartin_Lyon_preview_2026-09-20.mp4").write_bytes(b"\0" * 1024)
    (root / "Videos" / f"BoulangerieMartin_Lyon_preview_{today}.mp4").write_bytes(b"\0" * 4096)
    (root / "Videos" / "GarageDupont_Villeurbanne_preview_2026-10-01.mp4").write_bytes(b"\0" * 2048)
    (root / "Quotes" / "BoulangerieMartin_Lyon_quote_2026-10-05.pdf").write_bytes(_MIN_PDF)
    (root / "Quotes" / "GarageDupont_Villeurbanne_quote_2026-10-03.pdf").write_bytes(_MIN_PDF)
    reg = Registry(root / "Registry" / "registry.sqlite")
    if not reg.get("Boulangerie Martin", "Lyon"):
        reg.upsert(Company(name="Boulangerie Martin", city="Lyon", country="FR", website="https://boulangerie-martin.example",
                           aliases=["Martin"], contact_name="Jean Martin", contact_role="gérant",
                           email="contact@boulangerie-martin.example",
                           email_source="https://boulangerie-martin.example/contact", email_confidence="high",
                           email_found_at=now_iso(), phone="+33612345678",
                           phone_source="https://boulangerie-martin.example/contact", phone_confidence="high",
                           phone_found_at=now_iso()))
    if not reg.get("Garage Dupont", "Villeurbanne"):
        reg.upsert(Company(name="Garage Dupont", city="Villeurbanne", country="FR", website="https://garage-dupont.example",
                           email="info@garage-dupont.example", email_source="https://garage-dupont.example/mentions-legales",
                           email_confidence="high", email_found_at=now_iso(), phone="+33472000000",
                           phone_source="https://garage-dupont.example", phone_confidence="high", phone_found_at=now_iso()))
    reg.close()
    return root
