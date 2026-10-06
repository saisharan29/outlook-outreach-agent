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
    assert st["videos"] == 3 and st["quotes"] == 2 and st["templates"]["quote"] == ["fr", "de", "lb"] and st["signature"]
    assert st["languages"] == ["fr", "de", "lb"] and st["country"] == "LU"


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
    assert files["preview_fr.html"]["exists"] and files["preview_lb.html"]["html"] and files["signature.html"]["exists"]
    assert "preview_en.html" not in files
    bad = c.put("/api/templates/quote_fr.html", json={"content": "no subject\n\nbody"})
    assert bad.status_code == 400 and "Subject" in bad.json()["error"]
    bad2 = c.put("/api/templates/quote_fr.html", json={"content": "Subject: x\n\n{{greeting}} {{weird}} {{signature}}"})
    assert bad2.status_code == 400 and "weird" in bad2.json()["error"]
    ok = c.put("/api/templates/quote_fr.html", json={"content": "Subject: Devis {{company_name}}\n\n{{greeting}}\nNew.\n{{signature}}\nstop\n"})
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


def test_health_exports_and_login_lock(ctx, monkeypatch):
    c = client(ctx, monkeypatch)
    assert c.get("/healthz").json()["ok"]
    c.post("/api/chat", json={"message": "Quote email for Garage Dupont"})
    reg = c.get("/api/export/registry.csv")
    assert reg.status_code == 200 and "Garage Dupont" in reg.text and "attachment" in reg.headers["content-disposition"]
    acts = c.get("/api/export/actions.csv")
    assert "draft_created" in acts.text and c.get("/api/export/nope.csv").status_code == 404
    assert (ctx.settings.registry_dir / "agent.log").exists()
    fresh = TestClient(create_app(ctx.settings, ctx=ctx, demo=True))
    for _ in range(5):
        assert fresh.post("/api/login", json={"password": "wrong"}).status_code == 401
    assert fresh.post("/api/login", json={"password": "pw"}).status_code == 429


def test_security_headers_csrf_and_session_expiry(ctx, monkeypatch):
    import time as _time
    from outreach.web import app as webapp
    c = client(ctx, monkeypatch)
    r = c.get("/api/status")
    assert r.headers["x-frame-options"] == "DENY" and "default-src 'self'" in r.headers["content-security-policy"]
    assert r.headers["cache-control"] == "no-store" and "server" not in {k.lower() for k in r.headers}
    # A request carrying a foreign Origin is refused before any handler runs.
    bad = c.post("/api/chat", json={"message": "status"}, headers={"Origin": "https://evil.example"})
    assert bad.status_code == 403
    bad2 = c.post("/api/chat", json={"message": "status"}, headers={"Sec-Fetch-Site": "cross-site"})
    assert bad2.status_code == 403
    ok = c.post("/api/chat", json={"message": "status"}, headers={"Origin": "http://testserver", "Sec-Fetch-Site": "same-origin"})
    assert ok.status_code == 200
    # Idle expiry: pretend 13 hours passed.
    real = _time.time
    monkeypatch.setattr(webapp.time, "time", lambda: real() + 13 * 3600)
    assert c.get("/api/history").status_code == 401
    monkeypatch.setattr(webapp.time, "time", real)
    # Logout invalidates the server-side session even if the cookie is replayed.
    c2 = client(ctx, monkeypatch)
    cookie = c2.cookies.get("ooda_session")
    c2.post("/api/logout")
    c2.cookies.set("ooda_session", cookie)
    assert c2.get("/api/history").status_code == 401


def test_batch_runs_in_parallel_and_keeps_order(ctx, monkeypatch):
    import threading
    from outreach.agent.pipeline import Pipeline
    p = Pipeline(ctx)
    seen = []
    orig = p.run_company
    def slow(req):
        seen.append(threading.current_thread().name)
        return orig(req)
    monkeypatch.setattr(p, "run_company", slow)
    from outreach.agent.models import Session
    reply = p.handle("Quote email for Garage Dupont; Boulangerie Martin, Lyon; Fleuriste Rose, Nantes", Session())
    assert reply.index("Garage Dupont") < reply.index("Boulangerie Martin") < reply.index("Fleuriste Rose")
    assert len(set(seen)) > 1
