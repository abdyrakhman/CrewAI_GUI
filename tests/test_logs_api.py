"""Diagnostics: recent log endpoint and the settings screen."""
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

DATA = ROOT / ".setup" / f"logs-{uuid.uuid4().hex[:6]}"
for sub in ("crews", "runs", "outputs", "uploads", "logs"):
    (DATA / sub).mkdir(parents=True, exist_ok=True)
os.environ["CREWAI_STUDIO_DATA"] = str(DATA)
os.environ["CREWAI_STUDIO_NO_AUTH"] = "1"
os.environ["TMP"] = str(ROOT / ".setup" / "tmp")
os.environ["TEMP"] = os.environ["TMP"]
(ROOT / ".setup" / "tmp").mkdir(parents=True, exist_ok=True)

from app import observability  # noqa: E402
from app.server import create_server  # noqa: E402

PORT = 7912
BASE = f"http://127.0.0.1:{PORT}"
failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print(("PASS  " if condition else "FAIL  ") + name + (f" — {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(name)


def get_json(path: str) -> tuple[int, dict]:
    try:
        with urllib.request.urlopen(BASE + path, timeout=20) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"{}")


def main() -> int:
    observability.log_error(RuntimeError("boom sk-abcdefgh12345"), "req-test", "GET", "/api/demo")
    observability.log_request("GET", "/api/demo", 200, "req-ok", time.time())

    server = create_server("127.0.0.1", PORT)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    time.sleep(0.6)

    try:
        status, payload = get_json("/api/logs/recent?errors=1&limit=10")
        joined = "\n".join(payload.get("lines") or [])
        check("errors endpoint answers", status == 200 and payload.get("count", 0) >= 1, str(payload)[:120])
        check("error id is present", "error_id" in joined and "boom" in joined, joined[:160])
        check("secrets are redacted", "sk-abcdefgh12345" not in joined and "[redacted]" in joined, joined[:160])
        check("log file name is returned", str(payload.get("file") or "").startswith("app-"), str(payload.get("file")))

        status, payload = get_json("/api/logs/recent?limit=abc")
        check("bad limit still answers", status == 200 and isinstance(payload.get("lines"), list), str(payload)[:80])

        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            page = browser.new_page(viewport={"width": 1400, "height": 950})
            errors = []
            page.on("pageerror", lambda exc: errors.append(str(exc)))
            page.goto(BASE + "/#view=settings", wait_until="domcontentloaded")
            page.wait_for_function("() => window.__studio && window.__studio.settings", timeout=120000)
            page.wait_for_timeout(900)
            page.click('[data-action="show-errors"]')
            page.wait_for_timeout(700)
            modal = page.locator(".modal")
            check("errors modal opens", modal.count() == 1 and "Последние ошибки" in modal.inner_text())
            check("modal shows the log", "error_id" in modal.inner_text() and "boom" in modal.inner_text())
            check("copy action offered", page.locator('[data-action="copy-log"]').count() == 1)
            page.click('[data-action="close-modal"]')
            page.wait_for_timeout(300)
            page.click('[data-action="show-log"]')
            page.wait_for_timeout(700)
            check("full log modal opens", "журнала" in page.locator(".modal").inner_text())
            page.click('[data-action="close-modal"]')
            check("no JavaScript errors", not errors, str(errors[:2]))
            browser.close()
    finally:
        server.shutdown()
        server.server_close()

    print("\nLOGS RESULT:", "PASS" if not failures else f"FAIL ({len(failures)}): {failures}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
