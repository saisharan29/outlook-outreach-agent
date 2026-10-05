from fastapi.testclient import TestClient

from outreach.web.app import create_app


def test_password_login_status_and_chat(ctx, monkeypatch):
    monkeypatch.setattr(ctx.settings, "APP_PASSWORD", "pw")
    app = create_app(ctx.settings, ctx=ctx, demo=True)
    c = TestClient(app)
    assert c.get("/").status_code == 200 and "Outreach drafts" in c.get("/").text
    assert c.post("/api/chat", json={"message": "status"}).status_code == 401
    assert c.post("/api/login", json={"password": "nope"}).status_code == 401
    assert c.post("/api/login", json={"password": "pw"}).json()["ok"]
    st = c.get("/api/status").json()
    assert st["signed_in"] and st["outlook_connected"] and st["demo"] and st["mode"] == "pipeline"
    r = c.post("/api/chat", json={"message": "Quote email for Garage Dupont"}).json()
    assert "draft created" in r["reply"] and r["pending"] == []
    assert c.get("/api/log").json()["actions"][0]["result"] == "draft_created"
    assert c.get("/api/registry").json()["companies"]
    assert c.get("/auth/microsoft").status_code == 400     # demo graph has no auth
    assert c.get("/auth/microsoft/callback?code=x&state=bad").status_code == 400
