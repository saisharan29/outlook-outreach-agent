"""A stand-in for Microsoft Graph so the whole flow runs on a laptop with no account: drafts are
written to Registry/demo_drafts.json instead of Outlook. Never used when MS_CLIENT_ID is set."""
from __future__ import annotations

import json
from pathlib import Path

from ..outlook.graph import DraftResult, SendBlocked


class FakeGraph:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.drafts: list[dict] = json.loads(self.path.read_text()) if self.path.exists() else []
        self.fail_next: str = ""

    def connected(self) -> bool:
        return True

    def account(self) -> str:
        return "demo@outlook.local (demo mode: drafts go to Registry/demo_drafts.json)"

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.drafts, indent=2, ensure_ascii=False))

    def create_draft(self, *, to: str, subject: str, body: str, body_type: str = "Text", to_name: str = "") -> DraftResult:
        if self.fail_next == "create":
            self.fail_next = ""
            raise RuntimeError("demo: Outlook unavailable")
        draft_id = f"demo-{len(self.drafts) + 1}"
        self.drafts.append({"id": draft_id, "to": to, "subject": subject, "body": body, "attachments": []})
        self._save()
        return DraftResult(draft_id=draft_id, web_link=f"file://{self.path}#{draft_id}", subject=subject, to=to)

    def attach(self, draft_id: str, filename: str, content: bytes, content_type: str = "") -> None:
        if self.fail_next == "attach":
            self.fail_next = ""
            raise RuntimeError("demo: attachment upload failed")
        for d in self.drafts:
            if d["id"] == draft_id:
                d["attachments"].append({"name": filename, "size": len(content)})
        self._save()

    def delete_draft(self, draft_id: str) -> None:
        self.drafts = [d for d in self.drafts if d["id"] != draft_id]
        self._save()

    def find_messages_to(self, address: str, folder: str = "drafts", top: int = 10) -> list[dict]:
        if folder != "drafts":
            return []
        return [{"id": d["id"], "subject": d["subject"], "webLink": ""} for d in self.drafts
                if d["to"].lower() == address.lower()]

    def create_share_link(self, item_id: str, scope: str = "anonymous") -> str:
        raise RuntimeError("demo mode cannot create sharing links")

    def create_share_link_by_path(self, path: str, scope: str = "anonymous") -> str:
        raise RuntimeError("demo mode cannot create sharing links")

    def probe_cannot_send(self):
        raise SendBlocked("demo mode has no send endpoint")
