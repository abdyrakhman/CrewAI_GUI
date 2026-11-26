"""Backup archive: projects, roles, templates, settings and accounts."""
from __future__ import annotations

import io
import time
import zipfile
from pathlib import Path

from .config import DATA_DIR

SKIP_NAMES = {"sessions.json"}
SKIP_DIRS = {"logs", "outputs", "__pycache__"}
INCLUDE_DIRS = ("crews", "templates", "uploads")


def build_zip(include_runs: bool = False) -> bytes:
    buffer = io.BytesIO()
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("backup-info.txt", f"CrewAI Studio backup\ncreated: {stamp}\n")
        for name in ("roles.json", "settings.json", "users.json"):
            path = DATA_DIR / name
            if path.is_file():
                archive.write(path, arcname=name)
        for folder in INCLUDE_DIRS:
            base = DATA_DIR / folder
            if not base.exists():
                continue
            for path in sorted(base.rglob("*")):
                if not path.is_file():
                    continue
                if path.name in SKIP_NAMES or path.suffix in {".tmp", ".corrupt"}:
                    continue
                if any(part in SKIP_DIRS for part in path.relative_to(DATA_DIR).parts):
                    continue
                archive.write(path, arcname=str(path.relative_to(DATA_DIR)).replace("\\", "/"))
        if include_runs:
            base = DATA_DIR / "runs"
            if base.exists():
                for path in sorted(base.glob("*.json")):
                    archive.write(path, arcname=f"runs/{path.name}")
    return buffer.getvalue()
