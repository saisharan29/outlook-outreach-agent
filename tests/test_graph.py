import json
import time

import httpx
import pytest

from outreach.outlook.auth import FORBIDDEN_SCOPES, SCOPES, MicrosoftAuth, Token, TokenStore
from outreach.outlook.graph import GRAPH, GraphClient, GraphError, SendBlocked


def make(tmp_path, handler, expired=False):
    transport = httpx.MockTransport(handler)
    auth = MicrosoftAuth("cid", "sec", "http://localhost/cb", http=httpx.Client(transport=transport), app_secret="s")
    store = TokenStore(tmp_path / "tok.enc", "secret")
    store.save(Token(access_token="old" if expired else "tok", refresh_token="ref",
                     expires_at=time.time() + (-10 if expired else 3600), account="me@x.fr"))
    return GraphClient(auth, store, http=httpx.Client(transport=transport))


def test_scopes_have_no_send_permission():
    assert not FORBIDDEN_SCOPES & set(SCOPES) and "Mail.ReadWrite" in SCOPES


def test_token_store_is_encrypted_and_state_signed(tmp_path):
    store = TokenStore(tmp_path / "t.enc", "k")
    store.save(Token("a", "r", 1.0, "me"))
    assert b"a" not in (tmp_path / "t.enc").read_bytes()[:10] and store.load().account == "me"
    with pytest.raises(RuntimeError):
        TokenStore(tmp_path / "t.enc", "other").load()
    auth = MicrosoftAuth("c", "s", "u", app_secret="x")
    st = auth.make_state()
    assert auth.check_state(st) and not auth.check_state(st + "1") and not auth.check_state("bad")
    assert "Mail.Send" not in auth.authorization_url() and "Mail.ReadWrite" in auth.authorization_url()


def test_refuses_a_token_that_carries_send_scope():
    with pytest.raises(RuntimeError, match="send permission"):
        MicrosoftAuth._to_token({"access_token": "a", "scope": "Mail.Send Mail.ReadWrite", "expires_in": 10})


def test_send_endpoints_are_blocked_client_side(tmp_path):
    g = make(tmp_path, lambda r: httpx.Response(200, json={}))
    for url in ("/me/sendMail", "/me/messages/1/send", "/me/messages/1/reply", "/me/messages/1/forward"):
        with pytest.raises(SendBlocked):
            g._request("POST", url, json={})


def test_create_draft_small_attachment_and_duplicate_search(tmp_path):
    calls = []

    def handler(request):
        calls.append((request.method, request.url.path))
        if request.url.path.endswith("/me/messages") and request.method == "POST":
            body = json.loads(request.content)
            assert body["toRecipients"][0]["emailAddress"]["address"] == "a@b.fr"
            return httpx.Response(201, json={"id": "D1", "webLink": "https://outlook/D1"})
        if request.url.path.endswith("/attachments"):
            assert json.loads(request.content)["name"] == "f.pdf"
            return httpx.Response(201, json={"id": "A1"})
        if "mailFolders/drafts" in request.url.path:
            return httpx.Response(200, json={"value": [{"id": "D0", "subject": "Hi", "toRecipients": [{"emailAddress": {"address": "A@b.fr"}}]}]})
        return httpx.Response(200, json={"value": []})

    g = make(tmp_path, handler)
    d = g.create_draft(to="a@b.fr", subject="s", body="b")
    assert d.draft_id == "D1" and d.web_link.endswith("D1")
    g.attach("D1", "f.pdf", b"x" * 100)
    assert g.find_messages_to("a@b.fr", "drafts")[0]["id"] == "D0" and g.find_messages_to("a@b.fr", "sentitems") == []
    assert all("send" not in p.lower() for _, p in calls)


def test_large_attachment_uses_upload_session(tmp_path):
    chunks = []

    def handler(request):
        if request.url.path.endswith("createUploadSession"):
            return httpx.Response(201, json={"uploadUrl": "https://upload.test/s1"})
        if request.url.host == "upload.test":
            chunks.append(request.headers["Content-Range"])
            return httpx.Response(200)
        return httpx.Response(200, json={})

    g = make(tmp_path, handler)
    g.attach("D1", "big.mp4", b"\0" * (6 * 1024 * 1024))
    assert chunks == ["bytes 0-5242879/6291456", "bytes 5242880-6291455/6291456"]


def test_token_refresh_and_error_surface(tmp_path):
    def handler(request):
        if "oauth2/v2.0/token" in request.url.path:
            assert "refresh_token" in request.content.decode()
            return httpx.Response(200, json={"access_token": "new", "expires_in": 3600, "scope": "Mail.ReadWrite"})
        if request.headers["Authorization"] != "Bearer new":
            return httpx.Response(401, text="expired")
        return httpx.Response(403, json={"error": "nope"})

    g = make(tmp_path, handler, expired=True)
    with pytest.raises(GraphError, match="403"):
        g.me()
    assert g.store.load().access_token == "new"


def test_probe_cannot_send_expects_refusal(tmp_path):
    ok, _ = make(tmp_path, lambda r: httpx.Response(403, json={"error": "ErrorAccessDenied"})).probe_cannot_send()
    assert ok
    bad, detail = make(tmp_path, lambda r: httpx.Response(202)).probe_cannot_send()
    assert not bad and "check" in detail.lower()


def test_onedrive_listing_and_links(tmp_path):
    def handler(request):
        if request.url.path.endswith(":/children"):
            return httpx.Response(200, json={"value": [{"id": "I1", "name": "A_B_preview_2026-01-01.mp4", "size": 5, "file": {}},
                                                       {"id": "F", "name": "sub", "folder": {}}]})
        if request.url.path.endswith("/createLink"):
            return httpx.Response(201, json={"link": {"webUrl": "https://1drv.ms/x"}})
        if request.url.path.endswith("/content"):
            return httpx.Response(200, content=b"hello")
        return httpx.Response(404)

    from outreach.files.onedrive import OneDriveFileStore
    store = OneDriveFileStore(make(tmp_path, handler), "Agency")
    files = store.list_files("Videos")
    assert [f.name for f in files] == ["A_B_preview_2026-01-01.mp4"]
    assert store.read(files[0]) == b"hello" and store.share_link(files[0]) == "https://1drv.ms/x"
