"""Encryption at rest for credentials stored in ``data/settings.json``.

Windows uses DPAPI, which ties the ciphertext to the signed-in user account, so a
copied settings file is useless on another machine or account. Other platforms
fall back to Fernet with a key file kept beside the data (mode 0600).

Values without the ``enc:v1:`` prefix are legacy plaintext and keep working;
they are re-encrypted the next time settings are saved.
"""
from __future__ import annotations

import base64
import os
import sys
import threading
from pathlib import Path

from .config import DATA_DIR

PREFIX = "enc:v1:"
KEY_FILE = DATA_DIR / ".secret.key"
_lock = threading.Lock()
_fernet = None


def _dpapi():
    if sys.platform != "win32":
        return None
    try:
        import win32crypt  # type: ignore

        return win32crypt
    except Exception:  # noqa: BLE001 - optional dependency
        return None


def _get_fernet():
    global _fernet
    if _fernet is not None:
        return _fernet
    from cryptography.fernet import Fernet

    with _lock:
        if _fernet is not None:
            return _fernet
        KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
        if KEY_FILE.exists():
            key = KEY_FILE.read_bytes().strip()
        else:
            key = Fernet.generate_key()
            KEY_FILE.write_bytes(key)
            try:
                os.chmod(KEY_FILE, 0o600)
            except OSError:
                pass
        _fernet = Fernet(key)
        return _fernet


def is_encrypted(value: object) -> bool:
    return isinstance(value, str) and value.startswith(PREFIX)


def encrypt(value: str) -> str:
    """Encrypt a non-empty secret; already-encrypted values pass through."""
    text = str(value or "")
    if not text or is_encrypted(text):
        return text
    raw = text.encode("utf-8")
    dpapi = _dpapi()
    if dpapi is not None:
        try:
            blob = dpapi.CryptProtectData(raw, "CrewAI Studio", None, None, None, 0)
            return PREFIX + "dpapi:" + base64.b64encode(blob).decode("ascii")
        except Exception:  # noqa: BLE001 - fall back to Fernet
            pass
    token = _get_fernet().encrypt(raw).decode("ascii")
    return PREFIX + "fernet:" + token


def decrypt(value: str) -> str:
    text = str(value or "")
    if not is_encrypted(text):
        return text
    body = text[len(PREFIX):]
    if body.startswith("dpapi:"):
        dpapi = _dpapi()
        if dpapi is None:
            raise RuntimeError("Ключ зашифрован через Windows DPAPI и недоступен в этом окружении")
        _, data = dpapi.CryptUnprotectData(base64.b64decode(body[6:]), None, None, None, 0)
        return data.decode("utf-8")
    if body.startswith("fernet:"):
        return _get_fernet().decrypt(body[7:].encode("ascii")).decode("utf-8")
    return text


def mask(value: str) -> str:
    """A short, non-reversible hint for the UI (never the key itself)."""
    text = str(value or "")
    if not text:
        return ""
    return "••••" if len(text) <= 8 else f"••••{text[-4:]}"
