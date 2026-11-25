"""Browser test: interface language switch (RU <-> EN) and persistence."""
from __future__ import annotations

import os
import sys
import threading
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DATA = ROOT / ".setup" / f"ui-i18n-{uuid.uuid4().hex[:6]}"
for sub in ("crews", "runs", "outputs", "uploads"):
    (DATA / sub).mkdir(parents=True, exist_ok=True)
os.environ["CREWAI_STUDIO_DATA"] = str(DATA)
os.environ["CREWAI_STUDIO_NO_AUTH"] = "1"
os.environ["TMP"] = str(ROOT / ".setup" / "tmp")
os.environ["TEMP"] = os.environ["TMP"]
(ROOT / ".setup" / "tmp").mkdir(parents=True, exist_ok=True)

from app.server import create_server  # noqa: E402

PORT = 7884
BASE = f"http://127.0.0.1:{PORT}"
failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print(("PASS  " if condition else "FAIL  ") + name + (f" — {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(name)


def main() -> int:
    from playwright.sync_api import sync_playwright

    server = create_server("127.0.0.1", PORT)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    time.sleep(0.6)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 950})
            errors: list[str] = []
            page.on("pageerror", lambda exc: errors.append(str(exc)))

            page.goto(f"{BASE}/#view=settings", wait_until="domcontentloaded")
            page.wait_for_timeout(1200)
            russian = page.inner_text("body").lower()
            check("default language is Russian", "настройки" in russian and "проекты" in russian, russian[:120])

            page.select_option('[data-setting="ui_language"]', "en")
            page.wait_for_timeout(1200)
            english = page.inner_text("body").lower()
            check("sidebar switched to English", "projects" in english and "settings" in english, english[:160])
            check("settings headings switched", "default models" in english and "api keys" in english, english[:200])
            check("stored language is English", page.evaluate("window.__studio.settings.ui_language") == "en")

            page.reload(wait_until="domcontentloaded")
            page.wait_for_timeout(1200)
            check("language survives reload", "projects" in page.inner_text("body").lower())

            page.click('[data-action="new-crew"]')
            page.wait_for_timeout(900)
            builder = page.inner_text("body").lower()
            check("builder is English", "role" in builder and "workspace" in builder, builder[:160])

            page.goto(f"{BASE}/#view=settings", wait_until="domcontentloaded")
            page.wait_for_timeout(900)
            page.select_option('[data-setting="ui_language"]', "ru")
            page.wait_for_timeout(1000)
            back = page.inner_text("body").lower()
            check("Russian restored", "настройки" in back and "проекты" in back, back[:160])
            check("no JavaScript errors", not errors, str(errors[:2]))
            browser.close()
    finally:
        server.shutdown()
        server.server_close()

    print("\nUI I18N RESULT:", "PASS" if not failures else f"FAIL ({len(failures)}): {failures}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
