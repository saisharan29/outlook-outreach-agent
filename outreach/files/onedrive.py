"""Files read from OneDrive through Microsoft Graph (same account and login as Outlook)."""
from __future__ import annotations

from .base import FileInfo


class OneDriveFileStore:
    source = "onedrive"

    def __init__(self, graph, root_path: str = "Agency"):
        self.graph = graph
        self.root_path = root_path.strip("/")

    def list_files(self, folder: str) -> list[FileInfo]:
        items = self.graph.list_folder(f"{self.root_path}/{folder}")
        return [FileInfo(name=i["name"], size=int(i.get("size", 0)), folder=folder, ref=i["id"],
                         modified=i.get("lastModifiedDateTime", ""))
                for i in items if "file" in i]

    def read(self, file: FileInfo) -> bytes:
        return self.graph.download_item(file.ref)

    def share_link(self, file: FileInfo) -> str | None:
        try:
            return self.graph.create_share_link(file.ref)
        except Exception:
            return None
