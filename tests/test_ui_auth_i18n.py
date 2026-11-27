"""Login and password-change pages follow the interface language."""
from __future__ import annotations

import os
import sys
import threading
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DATA = ROOT / ".setup" / f"authi18n-{uuid.uuid4().hex[:6]}"
for sub in ("crews", "runs", "outputs", "uploads", "logs"):
    (DATA / sub).mkdir(parents=True, exist_ok=True)
os.environ["CREWAI_STUDIO_DATA"] = str(DATA)
os.environ["TMP"] = str(ROOT / ".setup" / "tmp")
os.environ["TEMP"] = os.environ["TMP"]
(ROOT / ".setup" / "tmp").mkdir(parents=True, exist_ok=True)

from app.server import create_server  # noqa: E402
from app.store import Store  # noqa: E402

Store().save_settings({"ui_language": "en"})

PORT = 7911
BASE = f"http://127.0.0.1:{PORT}"
failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print(("PASS  " if condition else "FAIL  ") + name + (f" — {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(name)


def main() -> int:
    server = create_server("127.0.0.1", PORT)
    admin_password = str((getattr(server, "generated_admin", {}) or {}).get("password") or "")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    time.sleep(0.6)

    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            page = browser.new_page(locale="ru-RU")
            errors = []
            page.on("pageerror", lambda exc: errors.append(str(exc)))

            page.goto(BASE + "/login", wait_until="domcontentloaded")
            page.wait_for_timeout(900)
            body = page.inner_text("body")
            check("login page uses the app language (en)", "Sign in" in body and "Password" in body, body[:140])
            bootstrap = page.locator("#bootstrap-block")
            check("first-run password block is visible", bootstrap.is_visible())
            block_text = bootstrap.inner_text()
            check("block shows the generated password",
                  admin_password in block_text and "admin" in block_text, block_text[:80])
            check("page lang attribute is en", page.evaluate("document.documentElement.lang") == "en")

            page.click("#to-register")
            page.wait_for_timeout(400)
            check("registration form is translated", "Registration" in page.inner_text("body"))

            page.click("#to-login")
            page.fill("#login-user", "admin")
            page.fill("#login-pass", admin_password)
            page.click("#login-submit")
            page.wait_for_timeout(1800)
            check("password screen is translated", "Change the password" in page.inner_text("body"),
                  page.inner_text("body")[:140])
            page.fill("#current", admin_password)
            page.fill("#next", "newpass123")
            page.fill("#repeat", "newpass123")
            page.click("#submit")
            page.wait_for_timeout(2200)

            Store().save_settings({"ui_language": "ru"})
            fresh = browser.new_context(locale="en-US")
            ru_page = fresh.new_page()
            ru_page.goto(BASE + "/login", wait_until="domcontentloaded")
            ru_page.wait_for_timeout(900)
            check("login page switches back to Russian", "Вход" in ru_page.inner_text("body"))
            check("password block is gone after the change", ru_page.locator("#bootstrap-block").is_hidden())
            check("password is not printed anywhere", "newpass123" not in ru_page.inner_text("body")
                  and admin_password not in ru_page.inner_text("body"))
            fresh.close()
            check("no JavaScript errors", not errors, str(errors[:2]))
            browser.close()
    finally:
        server.shutdown()
        server.server_close()

    print("\nAUTH I18N RESULT:", "PASS" if not failures else f"FAIL ({len(failures)}): {failures}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
