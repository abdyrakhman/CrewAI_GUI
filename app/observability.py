"""Minimal JSONL observability: request/error records with ids, size-based rotation."""
from __future__ import annotations

import json
import re
import threading
import time
import traceback
import uuid
from pathlib import Path

from .config import DATA_DIR

LOG_DIR = DATA_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
_lock = threading.Lock()
MAX_BYTES = 10 * 1024 * 1024
RETENTION_DAYS = 30

_SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{10,}"),
    re.compile(r"(?i)(api[_-]?key|token|secret)[\"'\s:=]+[A-Za-z0-9._\-]{8,}"),
)


def redact(text: object) -> str:
    """Never store credentials or bearer tokens in the log file."""
    value = str(text)
    for pattern in _SECRET_PATTERNS:
        value = pattern.sub("[redacted]", value)
    return value[:8000]


def _cleanup() -> None:
    cutoff = time.time() - RETENTION_DAYS * 86400
    try:
        for path in LOG_DIR.glob("app-*.jsonl*"):
            if path.stat().st_mtime < cutoff:
                path.unlink()
    except OSError:
        pass


def _path() -> Path:
    return LOG_DIR / f"app-{time.strftime('%Y%m%d')}.jsonl"


def _write(record: dict) -> None:
    record.setdefault("ts", round(time.time(), 3))
    line = json.dumps({key: redact(value) if isinstance(value, str) else value for key, value in record.items()},
                      ensure_ascii=False, default=str) + "\n"
    with _lock:
        try:
            path = _path()
            if path.exists() and path.stat().st_size > MAX_BYTES:
                path.replace(path.with_suffix(".jsonl.1"))
            with path.open("a", encoding="utf-8") as handle:
                handle.write(line)
        except OSError:
            pass


def log_request(method: str, path: str, status: int, request_id: str, started: float) -> None:
    _write(
        {
            "kind": "request",
            "request_id": request_id,
            "method": method,
            "path": path,
            "status": status,
            "ms": round((time.time() - started) * 1000, 1),
        }
    )


def log_error(exc: BaseException, request_id: str, method: str, path: str) -> str:
    """Log the traceback, return the short id shown to the client."""
    error_id = uuid.uuid4().hex[:8]
    _write(
        {
            "kind": "error",
            "error_id": error_id,
            "request_id": request_id,
            "method": method,
            "path": path,
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(limit=20),
        }
    )
    return error_id


def log_event(kind: str, **fields: object) -> None:
    _write({"kind": kind, **fields})


_cleanup()


def recent_lines(limit: int = 200, errors_only: bool = False) -> tuple[str, list[str]]:
    """Tail of today's JSONL log for the diagnostics screen."""
    try:
        limit = max(1, min(int(limit), 500))
    except (TypeError, ValueError):
        limit = 200
    path = _path()
    if not path.exists():
        return path.name, []
    try:
        size = path.stat().st_size
        with path.open("rb") as handle:
            handle.seek(max(0, size - 512 * 1024))
            raw = handle.read().decode("utf-8", "replace")
    except OSError:
        return path.name, []
    lines = [line for line in raw.splitlines() if line.strip()]
    if errors_only:
        lines = [line for line in lines if '"kind": "error"' in line or '"kind":"error"' in line]
    return path.name, lines[-limit:]
