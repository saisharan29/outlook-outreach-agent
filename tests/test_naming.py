from outreach.naming import match_files, normalize, parse_filename

FILES = ["BoulangerieMartin_Lyon_preview_2026-09-20.mp4", "BoulangerieMartin_Lyon_preview_2026-10-02.mp4",
         "BoulangerieMartin_Lyon_quote_2026-10-05.pdf", "GarageDupont_Villeurbanne_preview_2026-10-01.mp4",
         "BoulangerieMartin_Paris_preview_2026-10-01.mp4", "README.txt", "random file.mp4"]


def test_normalize_is_tolerant_to_accents_capitals_and_spacing():
    assert normalize("Boulangerie Martin") == normalize("boulangerie-martin") == normalize("BOULANGERIE  MARTIN")
    assert normalize("Café Léon") == "cafeleon"


def test_parse_filename_strict_and_loose():
    p = parse_filename("BoulangerieMartin_Lyon_preview_2026-10-02.mp4")
    assert p and p.strict and p.type == "preview" and str(p.date) == "2026-10-02" and p.city == "Lyon"
    q = parse_filename("GarageDupont_Lyon_devis.pdf")
    assert q and not q.strict and q.type == "quote" and q.date is None
    assert parse_filename("README.txt") is None
    assert parse_filename("random file.mp4") is None


def test_latest_version_wins_and_is_named():
    m = match_files(FILES, "Boulangerie Martin", "preview", city="Lyon")
    assert m.status == "match" and m.chosen.filename == "BoulangerieMartin_Lyon_preview_2026-10-02.mp4"
    assert "2 versions" in m.note and "picked the most recent" in m.note


def test_same_name_two_cities_is_ambiguous_without_city():
    m = match_files(FILES, "Boulangerie Martin", "preview")
    assert m.status == "ambiguous" and {c.city for c in m.candidates} == {"Lyon", "Paris"}


def test_city_separates_companies():
    assert match_files(FILES, "boulangerie martin", "preview", city="Paris").chosen.city == "Paris"


def test_no_match_lists_closest_only_when_similar():
    m = match_files(FILES, "Boulangerie Martine", "quote")
    assert m.status == "none" and m.candidates and m.candidates[0].company == "BoulangerieMartin"
    far = match_files(FILES, "Fleuriste Rose", "preview")
    assert far.status == "none" and far.candidates == []


def test_aliases_match():
    m = match_files(FILES, "Martin", "quote", aliases=["Boulangerie Martin"])
    assert m.status == "match" and m.chosen.type == "quote"


def test_type_never_crosses():
    assert match_files(FILES, "Garage Dupont", "quote").status == "none"
