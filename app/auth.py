"""Accounts and sessions for the local Studio interface.

Passwords are stored as PBKDF2-HMAC-SHA256 hashes with a per-user salt; the
session cookie carries a random token whose hash is kept on disk. The app stays
local, so this is about keeping other people on the same machine out, not about
protecting a public service.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
from pathlib import Path

from .config import DATA_DIR

USERS_FILE = DATA_DIR / "users.json"
SESSIONS_FILE = DATA_DIR / "sessions.json"
COOKIE_NAME = "studio_session"
SESSION_TTL = 7 * 24 * 3600
PBKDF2_ROUNDS = 200_000
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.\-]{3,32}$")

DEFAULT_ADMIN_USERNAME = "admin"
# Only used to detect and rotate installations that still have the old published password.
LEGACY_DEFAULT_PASSWORD = "123admin!"
PASSWORD_ALPHABET = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
DEFAULT_TTL_HOURS = 12
MAX_TTL_HOURS = 24 * 30

_lock = threading.RLock()
_users_cache: dict | None = None


def _read_json(path: Path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback


def _write_json(path: Path, data) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), PBKDF2_ROUNDS)
    return digest.hex(), salt


def verify_password(password: str, stored: dict) -> bool:
    digest, _ = hash_password(password, stored.get("salt", ""))
    return hmac.compare_digest(digest, stored.get("password_hash", ""))


def load_users() -> dict:
    global _users_cache
    with _lock:
        if _users_cache is None:
            _users_cache = _read_json(USERS_FILE, {})
            if not isinstance(_users_cache, dict):
                _users_cache = {}
        return _users_cache


def save_users(users: dict) -> None:
    global _users_cache
    with _lock:
        _users_cache = users
        _write_json(USERS_FILE, users)


def has_users() -> bool:
    return bool(load_users())


def get_user(username: str) -> dict | None:
    return load_users().get(username)


def create_user(username: str, password: str, must_change: bool = False) -> dict:
    username = str(username or "").strip()
    password = str(password or "")
    if not USERNAME_RE.match(username):
        raise ValueError("Логин: 3–32 символа, буквы, цифры, точка, дефис или подчёркивание")
    if len(password) < 8:
        raise ValueError("Пароль должен быть не короче 8 символов")
    must_change = bool(must_change)
    with _lock:
        users = dict(load_users())
        if username in users:
            raise ValueError("Такой пользователь уже существует")
        digest, salt = hash_password(password)
        users[username] = {
            "username": username,
            "password_hash": digest,
            "salt": salt,
            "must_change": must_change,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        save_users(users)
        return {k: users[username][k] for k in ("username", "created_at")}


def must_change(username: str) -> bool:
    record = get_user(username) or {}
    return bool(record.get("must_change"))


def migrate_roles() -> None:
    """Accounts no longer have roles: drop the field from older files."""
    with _lock:
        users = dict(load_users())
        changed = False
        for record in users.values():
            if "role" in record:
                record.pop("role", None)
                changed = True
        if changed:
            save_users(users)


def migrate_must_change() -> None:
    """Accounts created before the flag existed must set a new password once."""
    with _lock:
        users = dict(load_users())
        changed = False
        for record in users.values():
            if "must_change" not in record:
                record["must_change"] = True
                changed = True
        if changed:
            save_users(users)


def generate_password(length: int = 16) -> str:
    """A readable random password: no look-alike characters."""
    return "".join(secrets.choice(PASSWORD_ALPHABET) for _ in range(length))


def rotate_legacy_default() -> dict | None:
    """If an account still uses the old published password, replace it and report it."""
    with _lock:
        users = dict(load_users())
        for username, record in users.items():
            if not verify_password(LEGACY_DEFAULT_PASSWORD, record):
                continue
            password = generate_password()
            digest, salt = hash_password(password)
            record.update({
                "password_hash": digest,
                "salt": salt,
                "must_change": True,
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            })
            users[username] = record
            save_users(users)
            return {"username": username, "password": password, "rotated": True}
    return None


def ensure_default_admin() -> dict | None:
    """Create the first administrator, or rotate the old published password.

    Returns ``{"username", "password", "rotated"}`` when a password was generated,
    so the caller can show it once in the console.
    """
    if has_users():
        migrate_roles()
        migrate_must_change()
        return rotate_legacy_default()
    username = os.environ.get("CREWAI_STUDIO_ADMIN_USER", DEFAULT_ADMIN_USERNAME)
    password = os.environ.get("CREWAI_STUDIO_ADMIN_PASSWORD") or generate_password()
    try:
        create_user(username, password, must_change=True)
        return {"username": username, "password": password, "rotated": False}
    except ValueError:
        return None


def change_password(username: str, current: str, new_password: str) -> None:
    """Verify the current password and replace it with a new one."""
    with _lock:
        users = dict(load_users())
        record = users.get(username)
        if not record or not verify_password(current, record):
            raise ValueError("Текущий пароль неверен")
        if len(str(new_password or "")) < 8:
            raise ValueError("Новый пароль должен быть не короче 8 символов")
        digest, salt = hash_password(str(new_password))
        record.update({
            "password_hash": digest,
            "salt": salt,
            "must_change": False,
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        })
        users[username] = record
        save_users(users)


# ------------------------------------------------------------------ sessions
def _load_sessions() -> dict:
    data = _read_json(SESSIONS_FILE, {})
    return data if isinstance(data, dict) else {}


def _save_sessions(sessions: dict) -> None:
    _write_json(SESSIONS_FILE, sessions)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(username: str, ttl_hours: float | int = DEFAULT_TTL_HOURS) -> str:
    token = secrets.token_urlsafe(32)
    with _lock:
        sessions = _load_sessions()
        now = time.time()
        sessions = {key: value for key, value in sessions.items() if value.get("expires", 0) > now}
        try:
            ttl = max(1.0, min(float(ttl_hours), MAX_TTL_HOURS)) * 3600
        except (TypeError, ValueError):
            ttl = DEFAULT_TTL_HOURS * 3600
        sessions[_token_hash(token)] = {"username": username, "expires": now + ttl}
        _save_sessions(sessions)
    return token


def session_user(token: str) -> str | None:
    if not token:
        return None
    with _lock:
        sessions = _load_sessions()
        entry = sessions.get(_token_hash(token))
        if not entry or entry.get("expires", 0) <= time.time():
            return None
        if not get_user(entry.get("username", "")):
            return None
        return entry["username"]


def drop_user_sessions(username: str, keep_token: str = "") -> int:
    """Log the user out everywhere except (optionally) the current token."""
    keep = _token_hash(keep_token) if keep_token else ""
    removed = 0
    with _lock:
        sessions = _load_sessions()
        for key in list(sessions):
            if sessions[key].get("username") == username and key != keep:
                sessions.pop(key, None)
                removed += 1
        _save_sessions(sessions)
    return removed


def drop_session(token: str) -> None:
    if not token:
        return
    with _lock:
        sessions = _load_sessions()
        sessions.pop(_token_hash(token), None)
        _save_sessions(sessions)


def cookie_value(cookie_header: str) -> str:
    for part in str(cookie_header or "").split(";"):
        name, _, value = part.strip().partition("=")
        if name == COOKIE_NAME:
            return value.strip()
    return ""
