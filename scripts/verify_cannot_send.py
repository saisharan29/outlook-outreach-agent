"""Acceptance criterion: "The agent cannot send an email, verified by attempting it during testing."

Runs two checks against the connected account:
1. the client-side block: GraphClient refuses any send endpoint before a request leaves;
2. the permission: a direct POST /me/sendMail with the stored token must be refused by Microsoft.
"""
from __future__ import annotations

import sys

sys.path.insert(0, ".")
from outreach.agent.context import build_context          # noqa: E402
from outreach.outlook.auth import FORBIDDEN_SCOPES, SCOPES   # noqa: E402
from outreach.outlook.graph import SendBlocked              # noqa: E402


def main() -> int:
    assert not FORBIDDEN_SCOPES & set(SCOPES), "a send scope is requested!"
    print("Scopes requested:", " ".join(SCOPES), "(no Mail.Send)")
    ctx = build_context()
    g = ctx.graph
    if g is None or not g.connected():
        print("Outlook is not connected; connect it in the web app first.")
        return 2
    try:
        g._request("POST", "/me/sendMail", json={})
        print("FAIL: the client did not block the send endpoint")
        return 3
    except SendBlocked as exc:
        print("PASS (client block):", exc)
    ok, detail = g.probe_cannot_send()
    print(("PASS (permission): " if ok else "FAIL (permission): ") + detail)
    return 0 if ok else 4


if __name__ == "__main__":
    sys.exit(main())
