"""Files on this machine (or a folder the OneDrive client syncs here)."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .base import FileInfo


class LocalFileStore:
    source = "local"

    def __init__(self, root: Path | str, graph=None, onedrive_root: str = ""):
        """`graph` + `onedrive_root` are optional: when the local folder is a synced OneDrive
        folder and Outlook is connected, sharing links for large videos are created through
        Graph at onedrive_root/<folder>/<name>."""
        self.root = Path(root)
        self.graph = graph
        self.onedrive_root = onedrive_root.strip("/")

    def list_files(self, folder: str) -> list[FileInfo]:
        d = self.root / folder
        if not d.is_dir():
            return []
        out = []
        for p in sorted(d.iterdir()):
            if p.is_file() and not p.name.startswith("."):
                st = p.stat()
                out.append(FileInfo(name=p.name, size=st.st_size, folder=folder, ref=str(p),
                                    modified=datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat()))
        return out

    def read(self, file: FileInfo) -> bytes:
        return Path(file.ref).read_bytes()

    def share_link(self, file: FileInfo) -> str | None:
        if not self.graph or not self.onedrive_root:
            return None
        try:
            return self.graph.create_share_link_by_path(f"{self.onedrive_root}/{file.folder}/{file.name}")
        except Exception:
            return None
