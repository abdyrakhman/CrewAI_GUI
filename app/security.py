"""Transport-level protections: path confinement, SSRF guard, security headers.

Every disk path that comes from a request or from a crew specification must go
through :func:`confine`; every outbound URL through :func:`check_url`.
"""
from __future__ import annotations

import ipaddress
import socket
from pathlib import Path
from urllib.parse import urlparse

MAX_BODY = 64 * 1024 * 1024
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Cross-Origin-Resource-Policy": "same-origin",
}
HTML_CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'"
)


class PathEscape(ValueError):
    """A path tried to leave the directory it is confined to."""


def confine(path: str | Path, root: str | Path, kind: str = "path") -> Path:
    """Resolve ``path`` inside ``root`` or raise :class:`PathEscape`."""
    text = str(path or "")
    if "\x00" in text:
        raise PathEscape(f"{kind}: недопустимый путь")
    base = Path(root).resolve()
    candidate = Path(text)
    if not candidate.is_absolute():
        candidate = base / candidate
    try:
        resolved = candidate.resolve()
    except OSError as exc:
        raise PathEscape(f"{kind}: путь недоступен") from exc
    try:
        resolved.relative_to(base)
    except ValueError as exc:
        raise PathEscape(f"{kind}: путь вне {base}") from exc
    return resolved


def web_path(relative: str, root: Path) -> Path:
    """Static file inside ``web/``; rejects dot segments, backslashes and drives."""
    text = str(relative or "").strip()
    if not text:
        text = "index.html"
    if "\x00" in text or "\\" in text:
        raise PathEscape("static: недопустимый путь")
    if text.startswith("/") or ":" in text:
        raise PathEscape("static: абсолютный путь запрещён")
    parts = [part for part in text.split("/") if part not in {"", "."}]
    if any(part == ".." for part in parts):
        raise PathEscape("static: выход за каталог запрещён")
    return confine("/".join(parts) or "index.html", root, "static")


def _is_blocked_ip(ip: ipaddress._BaseAddress) -> bool:
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def check_url(url: str) -> str:
    """Reject non-http(s) URLs and hosts resolving to local/private addresses."""
    text = str(url or "").strip()
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Разрешены только адреса http:// и https://")
    host = parsed.hostname
    if not host:
        raise ValueError("В адресе нет домена")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except OSError as exc:
        raise ValueError(f"Не удалось разрешить адрес {host}: {exc}") from exc
    for info in infos:
        address = info[4][0]
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            continue
        if _is_blocked_ip(ip):
            raise ValueError(f"Адрес {host} ({address}) ведёт в локальную или частную сеть — доступ закрыт")
    return text
