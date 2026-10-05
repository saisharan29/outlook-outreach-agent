"""Microsoft Graph: drafts, attachments and OneDrive, with no way to send.

- A draft is `POST /me/messages`: it lands in the Drafts folder on every device (FR-21).
- Attachments under 3 MB go in one request; larger ones use an upload session (section 6).
- `/sendMail` and `/send` are blocked in this client on top of the missing permission (FR-25).
"""
from __future__ import annotations

import base64
import re
from dataclasses import dataclass

import httpx

from .auth import MicrosoftAuth, Token, TokenStore

GRAPH = "https://graph.microsoft.com/v1.0"
SMALL_ATTACHMENT_LIMIT = 3 * 1024 * 1024          # Graph: direct attach below 3 MB
UPLOAD_CHUNK = 5 * 1024 * 1024                      # multiples of 320 KiB, under 60 MiB
_BLOCKED = re.compile(r"/(sendMail|send|reply|replyAll|forward|createReply|createForward)(\?|$)", re.I)


class GraphError(RuntimeError):
    pass


class SendBlocked(GraphError):
    pass


@dataclass
class DraftResult:
    draft_id: str
    web_link: str
    subject: str
    to: str
    attachment: str = ""
    attachment_mode: str = ""      # "attached" | "link" | "none"


class GraphClient:
    def __init__(self, auth: MicrosoftAuth, store: TokenStore, http: httpx.Client | None = None):
        self.auth, self.store = auth, store
        self.http = http or httpx.Client(timeout=60)
        self._token: Token | None = None

    # --- auth ---------------------------------------------------------------
    def connected(self) -> bool:
        try:
            return self.store.load() is not None
        except RuntimeError:
            return False

    def account(self) -> str:
        t = self.store.load()
        return t.account if t else ""

    def _headers(self) -> dict:
        if self._token is None:
            self._token = self.store.load()
        if self._token is None:
            raise GraphError("Outlook is not connected. Sign in with Microsoft first.")
        if not self._token.valid():
            self._token = self.auth.refresh(self._token)
            self.store.save(self._token)
        return {"Authorization": f"Bearer {self._token.access_token}"}

    def _request(self, method: str, url: str, **kw) -> httpx.Response:
        if _BLOCKED.search(url.split("?", 1)[0]):
            raise SendBlocked("This agent cannot send mail: the endpoint is blocked and the permission absent.")
        if not url.startswith("http"):
            url = f"{GRAPH}{url}"
        headers = {**self._headers(), **kw.pop("headers", {})}
        r = self.http.request(method, url, headers=headers, **kw)
        if r.status_code == 401:
            # One refresh, then give up honestly.
            self._token = None
            headers = {**self._headers(), **headers}
            r = self.http.request(method, url, headers=headers, **kw)
        if r.status_code >= 400:
            raise GraphError(f"Microsoft Graph answered {r.status_code} on {method} {url.replace(GRAPH, '')}: "
                             f"{r.text[:200]}")
        return r

    def me(self) -> dict:
        return self._request("GET", "/me").json()

    def complete_sign_in(self, code: str) -> Token:
        token = self.auth.exchange_code(code)
        me = self.http.get(f"{GRAPH}/me", headers={"Authorization": f"Bearer {token.access_token}"})
        if me.status_code == 200:
            token.account = me.json().get("mail") or me.json().get("userPrincipalName", "")
        self.store.save(token)
        self._token = token
        return token

    # --- drafts -------------------------------------------------------------
    def create_draft(self, *, to: str, subject: str, body: str, body_type: str = "Text",
                     to_name: str = "") -> DraftResult:
        payload = {"subject": subject, "body": {"contentType": body_type, "content": body},
                   "toRecipients": [{"emailAddress": {"address": to, **({"name": to_name} if to_name else {})}}]}
        data = self._request("POST", "/me/messages", json=payload).json()
        if not data.get("id"):
            raise GraphError("Graph did not confirm the draft (no id in the answer).")
        return DraftResult(draft_id=data["id"], web_link=data.get("webLink", ""), subject=subject, to=to)

    def attach(self, draft_id: str, filename: str, content: bytes, content_type: str = "application/octet-stream") -> None:
        if len(content) < SMALL_ATTACHMENT_LIMIT:
            self._request("POST", f"/me/messages/{draft_id}/attachments", json={
                "@odata.type": "#microsoft.graph.fileAttachment", "name": filename,
                "contentType": content_type, "contentBytes": base64.b64encode(content).decode()})
            return
        session = self._request("POST", f"/me/messages/{draft_id}/attachments/createUploadSession", json={
            "AttachmentItem": {"attachmentType": "file", "name": filename, "size": len(content),
                               "contentType": content_type}}).json()
        url = session.get("uploadUrl")
        if not url:
            raise GraphError("Graph did not open an upload session for the attachment.")
        total = len(content)
        for start in range(0, total, UPLOAD_CHUNK):
            chunk = content[start:start + UPLOAD_CHUNK]
            end = start + len(chunk) - 1
            r = self.http.put(url, content=chunk, headers={
                "Content-Length": str(len(chunk)), "Content-Range": f"bytes {start}-{end}/{total}"})
            if r.status_code not in (200, 201, 202):
                raise GraphError(f"Attachment upload failed at byte {start}: {r.status_code} {r.text[:120]}")

    def delete_draft(self, draft_id: str) -> None:
        self._request("DELETE", f"/me/messages/{draft_id}")

    def find_messages_to(self, address: str, folder: str = "drafts", top: int = 10) -> list[dict]:
        """Messages addressed to `address` in Drafts or Sent Items (FR-24)."""
        r = self._request("GET", f"/me/mailFolders/{folder}/messages",
                          params={"$search": f'"to:{address}"', "$top": top,
                                  "$select": "id,subject,createdDateTime,sentDateTime,webLink,toRecipients"})
        out = []
        for m in r.json().get("value", []):
            rcpts = [x.get("emailAddress", {}).get("address", "").lower() for x in m.get("toRecipients", [])]
            if address.lower() in rcpts:
                out.append(m)
        return out

    # --- OneDrive -------------------------------------------------------------
    def list_folder(self, path: str) -> list[dict]:
        items, url = [], f"/me/drive/root:/{path.strip('/')}:/children"
        params = {"$select": "id,name,size,file,folder,lastModifiedDateTime", "$top": 200}
        while url:
            data = self._request("GET", url, params=params).json()
            items += data.get("value", [])
            url, params = data.get("@odata.nextLink"), None
        return items

    def download_item(self, item_id: str) -> bytes:
        return self._request("GET", f"/me/drive/items/{item_id}/content", follow_redirects=True).content

    def create_share_link(self, item_id: str, scope: str = "anonymous") -> str:
        data = self._request("POST", f"/me/drive/items/{item_id}/createLink",
                             json={"type": "view", "scope": scope}).json()
        link = (data.get("link") or {}).get("webUrl", "")
        if not link:
            raise GraphError("Graph returned no sharing link.")
        return link

    def create_share_link_by_path(self, path: str, scope: str = "anonymous") -> str:
        data = self._request("POST", f"/me/drive/root:/{path.strip('/')}:/createLink",
                             json={"type": "view", "scope": scope}).json()
        link = (data.get("link") or {}).get("webUrl", "")
        if not link:
            raise GraphError("Graph returned no sharing link.")
        return link

    # --- the acceptance test "cannot send" ---------------------------------------
    def probe_cannot_send(self) -> tuple[bool, str]:
        """Attempts a send on purpose, bypassing the client-side block, and expects Microsoft to
        refuse (403: missing Mail.Send). Used by scripts/verify_cannot_send.py only."""
        r = self.http.post(f"{GRAPH}/me/sendMail", headers=self._headers(), json={
            "message": {"subject": "permission probe", "body": {"contentType": "Text", "content": "probe"},
                        "toRecipients": [{"emailAddress": {"address": "nobody@example.invalid"}}]},
            "saveToSentItems": False})
        if r.status_code in (401, 403):
            return True, f"Microsoft refused the send ({r.status_code}): the permission is absent, as designed."
        return False, f"Unexpected answer {r.status_code}: {r.text[:200]} — check the Azure permissions NOW."
