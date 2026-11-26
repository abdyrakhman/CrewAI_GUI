"""Login, forced password change, registration and session protection."""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DATA = ROOT / ".setup" / f"auth-{uuid.uuid4().hex[:6]}"
for sub in ("crews", "runs", "outputs", "uploads"):
    (DATA / sub).mkdir(parents=True, exist_ok=True)
os.environ["CREWAI_STUDIO_DATA"] = str(DATA)

from app.server import create_server  # noqa: E402
from app.store import Store  # noqa: E402

PORT = 7897
BASE = f"http://127.0.0.1:{PORT}"
failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print(("PASS  " if condition else "FAIL  ") + name + (f" — {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(name)


def call(path: str, method: str = "GET", body: dict | None = None, cookie: str = "") -> tuple[int, dict | str, str]:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(BASE + path, data=data, method=method)
    if data is not None:
        request.add_header("Content-Type", "application/json")
    if cookie:
        request.add_header("Cookie", cookie)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
            headers = dict(response.getheaders())
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                payload = raw.decode("utf-8", "replace")
            return response.status, payload, headers.get("Set-Cookie", "")
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = raw.decode("utf-8", "replace")
        return exc.code, payload, exc.headers.get("Set-Cookie", "")


def cookie_from(header: str) -> str:
    return header.split(";", 1)[0] if header else ""


def main() -> int:
    store_settings = {"session_ttl_hours": 3}
    server = create_server("127.0.0.1", PORT)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    time.sleep(0.6)

    try:
        status, payload, _ = call("/api/auth/state")
        check("admin is seeded on first run", status == 200 and payload.get("has_users") is True, str(payload)[:120])

        status, payload, _ = call("/api/info")
        check("API is closed without a session", status == 401, f"{status} {str(payload)[:80]}")

        status, payload, _ = call("/login")
        check("login page is public", status == 200 and "CrewAI Studio" in str(payload), str(status))

        status, payload, _ = call("/api/auth/login", "POST", {"username": "admin", "password": "wrong"})
        check("wrong password is rejected", status == 401, f"{status} {str(payload)[:80]}")

        status, payload, set_cookie = call("/api/auth/login", "POST", {"username": "admin", "password": "123admin!"})
        check("default admin signs in", status == 200 and payload.get("user") == "admin", str(payload)[:120])
        check("first login demands a new password", payload.get("must_change") is True, str(payload)[:120])
        check("login sets a session cookie", "studio_session=" in set_cookie, set_cookie[:80])
        cookie = cookie_from(set_cookie)

        status, payload, _ = call("/api/info", cookie=cookie)
        check("API blocked until the password is changed",
              status == 403 and payload.get("password_change_required") is True, f"{status} {str(payload)[:100]}")

        status, payload, _ = call("/", cookie=cookie)
        check("page redirects to the password screen", "CrewAI Studio" in str(payload) and "Смените пароль" in str(payload),
              str(payload)[:100])

        status, payload, _ = call(
            "/api/auth/password", "POST", {"current": "123admin!", "new": "newpass123"}, cookie=cookie
        )
        check("password change is accepted", status == 200, f"{status} {str(payload)[:80]}")

        status, payload, _ = call("/api/info", cookie=cookie)
        check("API opens after the change", status == 200 and payload.get("app"), str(status))

        status, payload, _ = call("/api/auth/login", "POST", {"username": "admin", "password": "123admin!"})
        check("old password stops working", status == 401, str(status))
        status, payload, set_cookie = call("/api/auth/login", "POST", {"username": "admin", "password": "newpass123"})
        check("new password works", status == 200, str(payload)[:80])
        check("second login has no forced change", payload.get("must_change") is False, str(payload)[:80])
        cookie = cookie_from(set_cookie)

        # a second session must die when the password changes
        status, payload, set_cookie2 = call(
            "/api/auth/login", "POST", {"username": "admin", "password": "newpass123"}
        )
        other = cookie_from(set_cookie2)
        status, payload, _ = call(
            "/api/auth/password", "POST", {"current": "newpass123", "new": "thirdpass123"}, cookie=cookie
        )
        check("password change reports dropped sessions", status == 200 and payload.get("dropped_sessions") >= 1,
              str(payload)[:100])
        status, payload, _ = call("/api/auth/me", cookie=other)
        check("other session is dropped after password change", status == 401, str(status))
        status, payload, _ = call("/api/auth/me", cookie=cookie)
        check("current session survives password change", status == 200, str(status))

        status, payload, _ = call("/api/auth/logout-all", "POST", {}, cookie=cookie)
        check("logout everywhere is accepted", status == 200 and payload.get("ok") is True, str(payload)[:100])
        status, payload, _ = call("/api/auth/me", cookie=cookie)
        check("logout everywhere drops the current session too", status == 401, str(status))

        status, payload, set_cookie = call(
            "/api/auth/login", "POST", {"username": "admin", "password": "thirdpass123"}
        )
        cookie = cookie_from(set_cookie)
        check("login works after logout everywhere", status == 200, str(payload)[:80])

        for attempt in range(5):
            call("/api/auth/login", "POST", {"username": "admin", "password": "nope"})
        status, payload, _ = call("/api/auth/login", "POST", {"username": "admin", "password": "nope"})
        check("brute force is rate limited", status == 429, f"{status} {str(payload)[:100]}")

        status, payload, set_cookie = call("/api/auth/register", "POST", {"username": "tester", "password": "testpass123"})
        check("registration creates an account", status == 201 and payload.get("user") == "tester", str(payload)[:120])
        tester_cookie = cookie_from(set_cookie)
        status, payload, _ = call("/api/auth/me", cookie=tester_cookie)
        check("registered user is signed in", status == 200 and payload.get("user") == "tester", str(payload)[:100])

        status, payload, _ = call("/api/auth/register", "POST", {"username": "tester", "password": "testpass123"})
        check("duplicate registration is rejected", status == 400, f"{status} {str(payload)[:80]}")
        status, payload, _ = call("/api/auth/register", "POST", {"username": "x", "password": "123"})
        check("weak registration is rejected", status == 400, f"{status} {str(payload)[:80]}")

        ttl = Store().get_settings().get("session_ttl_hours")
        check("session lifetime setting exists", ttl == 12, str(ttl))

        status, payload, set_cookie = call("/api/auth/logout", "POST", {}, cookie=cookie)
        check("logout clears the cookie", status == 200 and "Max-Age=0" in set_cookie, set_cookie[:80])
        status, payload, _ = call("/api/info", cookie=cookie)
        check("dropped session is rejected", status == 401, str(status))
    finally:
        server.shutdown()
        server.server_close()

    print("\nAUTH RESULT:", "PASS" if not failures else f"FAIL ({len(failures)}): {failures}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
