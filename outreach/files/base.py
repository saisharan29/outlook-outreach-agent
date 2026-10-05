"""File storage behind one small interface (FR-17): the Videos and Quotes folders, wherever they live."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class FileInfo:
    name: str
    size: int
    folder: str                 # "Videos" | "Quotes" | "Templates"
    ref: str                    # local path or OneDrive item id
    modified: str = ""


class FileStore(Protocol):
    source: str

    def list_files(self, folder: str) -> list[FileInfo]: ...
    def read(self, file: FileInfo) -> bytes: ...
    def share_link(self, file: FileInfo) -> str | None:
        """A view-only sharing link, or None when the store cannot make one."""
        ...
