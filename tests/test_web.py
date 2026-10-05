from fastapi.testclient import TestClient

from outreach.web.app import create_app


def client(ctx, monkeypatch, password="pw"):
    monkeypatch.setattr(ctx.settings, "APP_PASSWORD", password)
    c = TestClient(create_app(ctx.settings, ctx=ctx, demo=True))
    if password:
        assert c.post("/api/login", json={"password": password}).json()["ok"]
    return c


def test_login_required_and_status(ctx, monkeypatch):
    monkeypatch.setattr(ctx.settings, "APP_PASSWORD", "pw")
    c = TestClient(create_app(ctx.settings, ctx=ctx, demo=True))
    assert "Outreach" in c.get("/").text
    assert c.post("/api/chat", json={"message": "status"}).status_code == 401
    assert c.post("/api/login", json={"password": "nope"}).status_code == 401
    assert c.post("/api/login", json={"password": "pw"}).json()["ok"]
    st = c.get("/api/status").json()
    assert st["signed_in"] and st["outlook_connected"] and st["demo"] and st["mode"] == "pipeline"
    assert st["videos"] == 3 and st["quotes"] == 2 and st["templates"]["quote"] == ["fr", "en"] and st["signature"]


def test_chat_returns_structured_reports_and_history(ctx, monkeypatch):
    c = client(ctx, monkeypatch)
    r = c.post("/api/chat", json={"message": "Quote email for Garage Dupont"}).json()
    assert r["role"] == "agent" and r["reports"][0]["status"] == "draft_created"
    assert r["reports"][0]["draft"]["attachment"].endswith(".pdf") and r["pending"] == []
    r2 = c.post("/api/chat", json={"message": "Quote email for Garage Dupont"}).json()
    assert r2["pending"][0]["kind"] == "confirm_duplicate" and r2["reports"][0]["question"]["kind"] == "confirm_duplicate"
    h = c.get("/api/history").json()
    assert [m["role"] for m in h["messages"]] == ["owner", "agent", "owner", "agent"] and len(h["pending"]) == 1
    assert "Cancelled" in c.post("/api/chat", json={"message": "cancel"}).json()["text"]
    assert c.get("/api/history").json()["pending"] == []
    assert c.get("/api/log").json()["actions"][0]["result"] == "cancelled"
    assert c.post("/api/chat", json={"message": "  "}).status_code == 400
    c.post("/api/history/clear")
    assert c.get("/api/history").json()["messages"] == []


def test_templates_editor_validates(ctx, monkeypatch):
    c = client(ctx, monkeypatch)
    files = {f["name"]: f for f in c.get("/api/templates").json()["files"]}
    assert files["preview_fr.txt"]["exists"] and files["signature.txt"]["exists"] is False
    bad = c.put("/api/templates/quote_fr.txt", json={"content": "no subject\n\nbody"})
    assert bad.status_code == 400 and "Subject" in bad.json()["error"]
    bad2 = c.put("/api/templates/quote_fr.txt", json={"content": "Subject: x\n\n{{greeting}} {{weird}} {{signature}}"})
    assert bad2.status_code == 400 and "weird" in bad2.json()["error"]
    ok = c.put("/api/templates/quote_fr.txt", json={"content": "Subject: Devis {{company_name}}\n\n{{greeting}}\nNew.\n{{signature}}\nstop\n"})
    assert ok.json()["ok"] and c.put("/api/templates/evil.txt", json={"content": "x"}).status_code == 400
    r = c.post("/api/chat", json={"message": "Quote email for Garage Dupont"}).json()
    assert r["reports"][0]["draft"]["subject"] == "Devis Garage Dupont"


def test_registry_do_not_contact_toggle(ctx, monkeypatch):
    c = client(ctx, monkeypatch)
    assert c.post("/api/registry/do_not_contact", json={"name": "Garage Dupont", "city": "Villeurbanne", "value": True}).json()["company"]["do_not_contact"]
    r = c.post("/api/chat", json={"message": "Quote email for Garage Dupont"}).json()
    assert r["reports"][0]["status"] == "refused"
    assert c.post("/api/registry/do_not_contact", json={"name": "Nobody", "city": "", "value": True}).status_code == 404
    assert c.get("/api/registry").json()["companies"]


def test_auth_routes_in_demo(ctx, monkeypatch):
    c = client(ctx, monkeypatch)
    assert c.get("/auth/microsoft").status_code == 400
    assert c.get("/auth/microsoft/callback?code=x&state=bad").status_code == 400


def test_no_password_mode(ctx, monkeypatch):
    c = client(ctx, monkeypatch, password="")
    assert c.get("/api/status").json()["signed_in"]
    assert c.post("/api/chat", json={"message": "status"}).json()["text"].startswith("Outlook")
