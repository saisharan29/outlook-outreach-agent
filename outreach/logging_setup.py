"""One log file in the owner's Registry folder, rotated, so a problem can be investigated after the fact."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging(folder: Path | str, level: str = "INFO") -> logging.Logger:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger("outreach")
    target = str(folder / "agent.log")
    for h in list(root.handlers):
        if isinstance(h, RotatingFileHandler):
            if h.baseFilename == target:
                return root
            root.removeHandler(h)
            h.close()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    handler = RotatingFileHandler(folder / "agent.log", maxBytes=2_000_000, backupCount=5, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root.addHandler(handler)
    return root
