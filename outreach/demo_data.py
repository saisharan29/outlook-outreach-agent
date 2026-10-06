"""Builds a sample Agency folder: the owner's templates in French, German and Luxembourgish, an
HTML signature, two companies with sample files and registry rows, so the whole flow can be tried
without any account or key.

The French preview text is the owner's own email (Webalix, 30 Sept 2026). The German and
Luxembourgish versions are translations to be proofread by the owner before first use.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from .registry import Company, Registry, now_iso

PREVIEW_FR = """Subject: Aperçu de votre site web

<p>{{greeting}}</p>
<p>Comme convenu lors de notre échange, je vous transmets un premier aperçu du site web que nous avons préparé pour {{company_name}}.</p>
<p>Nous avons réalisé cette première version en amont afin de vous permettre de visualiser concrètement ce que nous pourrions mettre en place pour votre entreprise, aussi bien au niveau du design que de la présentation de vos services, de la navigation et de l’expérience utilisateur.</p>
<p>Vous trouverez ci-joint une courte vidéo de présentation du site.{{preview_link}}</p>
<p>Il s’agit bien entendu uniquement d’un aperçu. La version complète comprend davantage de pages, de contenus, d’animations, de transitions et d’interactions qu’il est difficile de retranscrire entièrement dans une courte vidéo. De plus, la qualité de la vidéo peut être légèrement réduite lors de son envoi par e-mail.</p>
<p>Au-delà de la création du site, {{agency_name}} propose également plusieurs services complémentaires, notamment :</p>
<ul>
<li>la maintenance et le suivi technique du site ;</li>
<li>les mises à jour et adaptations futures ;</li>
<li>l’optimisation SEO afin d’améliorer le référencement et la visibilité sur Google et les autres moteurs de recherche ;</li>
<li>l’optimisation GEO (<i>Generative Engine Optimization</i>), qui vise à structurer et optimiser le site afin qu’il puisse également être mieux compris, identifié et cité par des moteurs de recherche et assistants basés sur l’intelligence artificielle, notamment ChatGPT et d’autres plateformes similaires.</li>
</ul>
<p>Je serais ravi de pouvoir vous présenter le site dans son intégralité lors d’un court Google Meet. Cela me permettrait de vous montrer la qualité réelle du rendu, les différentes pages et animations, ainsi que de recueillir directement vos impressions et les éventuelles modifications que vous souhaiteriez apporter.</p>
<p>N’hésitez pas à me communiquer vos disponibilités si vous souhaitez découvrir la version complète.</p>
<p>Merci encore pour votre temps et pour notre échange. Je reste bien entendu à votre disposition pour toute question.</p>
<p>Bien cordialement,</p>
{{signature}}
<p style="color:#888;font-size:12px">Vous recevez ce message car votre entreprise est publiquement référencée. Répondez « stop » pour ne plus recevoir de message de notre part.</p>
"""

PREVIEW_DE = """Subject: Vorschau Ihrer Website

<p>{{greeting}}</p>
<p>wie bei unserem Gespräch besprochen, sende ich Ihnen eine erste Vorschau der Website, die wir für {{company_name}} vorbereitet haben.</p>
<p>Diese erste Version haben wir vorab erstellt, damit Sie sich konkret vorstellen können, was wir für Ihr Unternehmen umsetzen könnten – beim Design ebenso wie bei der Darstellung Ihrer Leistungen, der Navigation und der Benutzererfahrung.</p>
<p>Im Anhang finden Sie ein kurzes Präsentationsvideo der Website.{{preview_link}}</p>
<p>Es handelt sich selbstverständlich nur um eine Vorschau. Die vollständige Version umfasst mehr Seiten, Inhalte, Animationen, Übergänge und Interaktionen, die sich in einem kurzen Video nur schwer vollständig wiedergeben lassen. Zudem kann die Videoqualität beim Versand per E-Mail leicht reduziert sein.</p>
<p>Über die Erstellung der Website hinaus bietet {{agency_name}} weitere ergänzende Leistungen an, insbesondere:</p>
<ul>
<li>Wartung und technische Betreuung der Website;</li>
<li>zukünftige Aktualisierungen und Anpassungen;</li>
<li>SEO-Optimierung zur Verbesserung der Platzierung und Sichtbarkeit bei Google und anderen Suchmaschinen;</li>
<li>GEO-Optimierung (<i>Generative Engine Optimization</i>), damit die Website auch von KI-basierten Suchmaschinen und Assistenten wie ChatGPT besser verstanden, erkannt und zitiert wird.</li>
</ul>
<p>Gerne stelle ich Ihnen die Website in einem kurzen Google Meet vollständig vor. So kann ich Ihnen die tatsächliche Qualität, die einzelnen Seiten und Animationen zeigen und direkt Ihre Eindrücke und Änderungswünsche aufnehmen.</p>
<p>Teilen Sie mir gerne Ihre Verfügbarkeiten mit, wenn Sie die vollständige Version kennenlernen möchten.</p>
<p>Vielen Dank nochmals für Ihre Zeit und unser Gespräch. Für Fragen stehe ich Ihnen selbstverständlich jederzeit zur Verfügung.</p>
<p>Mit freundlichen Grüßen,</p>
{{signature}}
<p style="color:#888;font-size:12px">Sie erhalten diese Nachricht, weil Ihr Unternehmen öffentlich gelistet ist. Antworten Sie mit „Stop“, um keine weiteren Nachrichten von uns zu erhalten.</p>
"""

PREVIEW_LB = """Subject: Virschau vun Ärer Websäit

<p>{{greeting}}</p>
<p>Wéi bei eisem Gespréich ofgemaach, schécken ech Iech eng éischt Virschau vun der Websäit, déi mir fir {{company_name}} virbereet hunn.</p>
<p>Dës éischt Versioun hu mir am Viraus gemaach, fir datt Dir Iech konkret kënnt virstellen, wat mir fir Äert Betrib kéinten opsetzen – beim Design grad wéi bei der Presentatioun vun Äre Servicer, der Navigatioun an der Benotzererfarung.</p>
<p>Am Uhang fannt Dir eng kuerz Presentatiounsvideo vun der Websäit.{{preview_link}}</p>
<p>Et handelt sech natierlech nëmmen ëm eng Virschau. Déi komplett Versioun huet méi Säiten, Inhalter, Animatiounen, Iwwergäng an Interaktiounen, déi sech an engem kuerze Video schwéier komplett weise loossen. Ausserdeem kann d’Qualitéit vum Video beim Verschécke per E-Mail liicht reduzéiert sinn.</p>
<p>Niewent der Websäit selwer bitt {{agency_name}} och weider Servicer un, ënner anerem:</p>
<ul>
<li>d’Maintenance an de techneschen Suivi vun der Websäit;</li>
<li>zukünfteg Aktualiséierungen an Upassungen;</li>
<li>SEO-Optimiséierung, fir d’Plazéierung an d’Visibilitéit op Google an anere Sichmaschinnen ze verbesseren;</li>
<li>GEO-Optimiséierung (<i>Generative Engine Optimization</i>), fir datt d’Websäit och vu KI-baséierte Sichmaschinnen an Assistenten, wéi ChatGPT, besser verstanen, erkannt an zitéiert gëtt.</li>
</ul>
<p>Ech géif Iech d’Websäit gär an engem kuerze Google Meet komplett virstellen. Sou kann ech Iech déi richteg Qualitéit, déi eenzel Säiten an Animatioune weisen an direkt Är Andréck an Ännerungswënsch ophuelen.</p>
<p>Deelt mir gär Är Disponibilitéite mat, wann Dir déi komplett Versioun wëllt kenneléieren.</p>
<p>Villmools Merci nach eng Kéier fir Är Zäit an eist Gespréich. Fir Froe stinn ech Iech natierlech gär zur Verfügung.</p>
<p>Mat beschte Gréiss,</p>
{{signature}}
<p style="color:#888;font-size:12px">Dir kritt dës Noriicht, well Äert Betrib ëffentlech referenzéiert ass. Äntwert mat „Stop“, fir keng weider Noriichte vun eis ze kréien.</p>
"""

QUOTE_FR = """Subject: Devis pour le site web de {{company_name}}

<p>{{greeting}}</p>
<p>Merci pour votre intérêt. Vous trouverez ci-joint le devis pour le site web de {{company_name}}, avec le détail des prestations et des délais.</p>
<p>Je reste à votre disposition pour toute question ou ajustement.</p>
<p>Bien cordialement,</p>
{{signature}}
<p style="color:#888;font-size:12px">Pour ne plus recevoir de message de notre part, répondez « stop ».</p>
"""
QUOTE_DE = """Subject: Angebot für die Website von {{company_name}}

<p>{{greeting}}</p>
<p>vielen Dank für Ihr Interesse. Im Anhang finden Sie das Angebot für die Website von {{company_name}} mit allen Leistungen und Fristen.</p>
<p>Für Fragen oder Anpassungen stehe ich Ihnen gerne zur Verfügung.</p>
<p>Mit freundlichen Grüßen,</p>
{{signature}}
<p style="color:#888;font-size:12px">Antworten Sie mit „Stop“, um keine weiteren Nachrichten von uns zu erhalten.</p>
"""
QUOTE_LB = """Subject: Offer fir d’Websäit vu {{company_name}}

<p>{{greeting}}</p>
<p>Merci fir Ären Interessi. Am Uhang fannt Dir den Devis fir d’Websäit vu {{company_name}} mat allen Detailer vun de Servicer an den Delaien.</p>
<p>Fir Froen oder Upassunge sinn ech gär fir Iech do.</p>
<p>Mat beschte Gréiss,</p>
{{signature}}
<p style="color:#888;font-size:12px">Äntwert mat „Stop“, fir keng weider Noriichte vun eis ze kréien.</p>
"""

SIGNATURE_HTML = """<table cellpadding="0" cellspacing="0" style="font-family:Arial,Helvetica,sans-serif;color:#1d1d1b;font-size:14px;line-height:1.4">
<tr><td style="font-size:30px;font-weight:700;letter-spacing:-0.5px;padding-bottom:4px">Webalix.</td></tr>
<tr><td style="font-size:18px;font-weight:700;color:#1b3a63">Paul Roukoz</td></tr>
<tr><td style="font-size:12px;letter-spacing:.12em;color:#2a6fb5;font-weight:600;padding-bottom:2px">CO-FONDATEUR &amp; COO</td></tr>
<tr><td style="color:#555;padding-bottom:10px;border-bottom:1px solid #e6d9c2">Alix Intelligence S.à r.l.</td></tr>
<tr><td style="padding-top:10px">
  <table cellpadding="0" cellspacing="0" style="font-size:14px">
  <tr><td style="font-weight:700;padding-right:18px">Tél</td><td><a href="tel:+352691817815" style="color:#2a6fb5;text-decoration:none">+352 691 817 815</a></td></tr>
  <tr><td style="font-weight:700;padding-right:18px">Web</td><td><a href="https://www.webalix.eu" style="color:#2a6fb5;text-decoration:none">www.webalix.eu</a></td></tr>
  <tr><td style="font-weight:700;padding-right:18px">Email</td><td><a href="mailto:p.roukoz@alixintelligence.lu" style="color:#2a6fb5;text-decoration:none">p.roukoz@alixintelligence.lu</a></td></tr>
  </table>
</td></tr>
</table>
"""

TEMPLATES = {
    "preview_fr.html": PREVIEW_FR, "preview_de.html": PREVIEW_DE, "preview_lb.html": PREVIEW_LB,
    "quote_fr.html": QUOTE_FR, "quote_de.html": QUOTE_DE, "quote_lb.html": QUOTE_LB,
    "signature.html": SIGNATURE_HTML,
    "agency.txt": "Webalix\n",
    "README.txt": """Templates — edit these files freely (or in the app, Templates page); the next draft uses the new wording.
Layout: first line "Subject: …", a blank line, then the body. An .html file is sent as an HTML email.
Placeholders: {{company_name}} {{contact_name}} {{greeting}} {{city}} {{preview_link}} {{signature}} {{agency_name}}
{{greeting}} becomes "Bonjour," before 18:00 and "Bonsoir," after, with the contact's name when it is known.
One file per language: preview_fr / preview_de / preview_lb, quote_fr / quote_de / quote_lb.
The German and Luxembourgish texts are translations of the French one: proofread them before first use.
signature.html is the owner's signature block; replace it with the HTML of the Outlook signature if preferred.
Keep the opt-out sentence: cold B2B email needs one.
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
                           phone_source="https://garage-dupont.example", phone_confidence="high",
                           phone_found_at=now_iso()))
    reg.close()
    return root
