"""Microsoft sign-in (OAuth authorization code flow) and encrypted token storage.

Permissions requested (spec section 9): read/write mail (drafts), read/write files (read the
folders, make a sharing link for a video too large to attach), offline access. Mail.Send is
deliberately absent: the agent is technically unable to send, whatever it is told.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet, InvalidToken

SCOPES = ["offline_access", "User.Read", "Mail.ReadWrite", "Files.ReadWrite"]
FORBIDDEN_SCOPES = {"Mail.Send", "Mail.Send.Shared", "SMTP.Send"}
assert not FORBIDDEN_SCOPES & set(SCOPES), "the agent must never hold a send permission"

_HINTS = {
    "AADSTS7000215": "Microsoft says the client secret is wrong. Copy the secret VALUE (not its ID) from "
                     "Azure → Certificates & secrets into MS_CLIENT_SECRET.",
    "AADSTS7000222": "The client secret has expired. Create a new one in Azure and update MS_CLIENT_SECRET.",
    "AADSTS700016": "Microsoft does not know this client ID. Check MS_CLIENT_ID.",
    "AADSTS50011": "The redirect address does not match what is registered in Azure (Authentication → Web).",
    "AADSTS65001": "The permissions were not granted. Sign in again and accept them.",
    "AADSTS54005": "That sign-in code was already used. Start the sign-in again.",
}


@dataclass
class Token:
    access_token: str
    refresh_token: str
    expires_at: float          # unix time
    account: str = ""          # the signed-in address
    scope: str = ""

    def valid(self, margin: int = 60) -> bool:
        return bool(self.access_token) and time.time() < self.expires_at - margin


class TokenStore:
    """Tokens encrypted at rest with a key derived from SECRET_KEY (never in code or chat)."""

    def __init__(self, path: Path | str, secret: str):
        self.path = Path(path)
        digest = hashlib.sha256(secret.encode()).digest()
        self._fernet = Fernet(base64.urlsafe_b64encode(digest))

    def save(self, token: Token) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        blob = self._fernet.encrypt(json.dumps(token.__dict__).encode())
        self.path.write_bytes(blob)

    def load(self) -> Token | None:
        if not self.path.exists():
            return None
        try:
            data = json.loads(self._fernet.decrypt(self.path.read_bytes()))
        except (InvalidToken, ValueError):
            raise RuntimeError("Stored Microsoft token cannot be decrypted; SECRET_KEY changed? Sign in again.")
        return Token(**data)

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()


class MicrosoftAuth:
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str, tenant: str = "common",
                 http: httpx.Client | None = None, app_secret: str = "dev"):
        self.client_id, self.client_secret = client_id, client_secret
        self.redirect_uri, self.tenant = redirect_uri, tenant
        self.http = http or httpx.Client(timeout=20)
        self._app_secret = app_secret.encode()

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def _base(self) -> str:
        return f"https://login.microsoftonline.com/{self.tenant}/oauth2/v2.0"

    # State protects the callback against forgery; it is signed, time-limited, never stored.
    def make_state(self, ttl: int = 900) -> str:
        payload = f"{int(time.time()) + ttl}.{secrets.token_urlsafe(12)}"
        sig = hmac.new(self._app_secret, payload.encode(), hashlib.sha256).hexdigest()[:32]
        return f"{payload}.{sig}"

    def check_state(self, state: str) -> bool:
        try:
            exp, nonce, sig = state.split(".")
        except ValueError:
            return False
        expected = hmac.new(self._app_secret, f"{exp}.{nonce}".encode(), hashlib.sha256).hexdigest()[:32]
        return hmac.compare_digest(sig, expected) and int(exp) > time.time()

    def authorization_url(self) -> str:
        return f"{self._base()}/authorize?" + urlencode({
            "client_id": self.client_id, "response_type": "code", "redirect_uri": self.redirect_uri,
            "response_mode": "query", "scope": " ".join(SCOPES), "state": self.make_state(),
            "prompt": "select_account"})

    def _token_request(self, data: dict) -> dict:
        r = self.http.post(f"{self._base()}/token", data={
            "client_id": self.client_id, "client_secret": self.client_secret,
            "scope": " ".join(SCOPES), **data})
        if r.status_code >= 400:
            try:
                body = r.json()
                text = (body.get("error_description") or body.get("error") or "").splitlines()[0]
            except ValueError:
                text = r.text[:200]
            hint = next((h for code, h in _HINTS.items() if code in text), "")
            raise RuntimeError(f"Microsoft refused the sign-in ({r.status_code}). {hint or text}".strip())
        return r.json()

    @staticmethod
    def _to_token(data: dict, previous: Token | None = None) -> Token:
        granted = set((data.get("scope") or "").split())
        if granted & FORBIDDEN_SCOPES:
            raise RuntimeError("Microsoft granted a send permission; refusing to store this token.")
        return Token(access_token=data["access_token"],
                     refresh_token=data.get("refresh_token") or (previous.refresh_token if previous else ""),
                     expires_at=time.time() + int(data.get("expires_in", 3600)),
                     account=previous.account if previous else "", scope=data.get("scope", ""))

    def exchange_code(self, code: str) -> Token:
        return self._to_token(self._token_request({"grant_type": "authorization_code", "code": code,
                                                   "redirect_uri": self.redirect_uri}))

    def refresh(self, token: Token) -> Token:
        return self._to_token(self._token_request({"grant_type": "refresh_token",
                                                   "refresh_token": token.refresh_token}), token)
