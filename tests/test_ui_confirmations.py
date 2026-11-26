"""Browser test: permission prompt, background run indicator, template creation, hidden keys."""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

DATA = ROOT / ".setup" / f"uiconf-{uuid.uuid4().hex[:8]}"
DATA.mkdir(parents=True, exist_ok=True)
os.environ["CREWAI_STUDIO_DATA"] = str(DATA)
os.environ["CREWAI_STUDIO_NO_AUTH"] = "1"
os.environ["MOCK_DELAY"] = "0.06"
TMP = ROOT / ".setup" / "tmp"
TMP.mkdir(parents=True, exist_ok=True)
os.environ["TMP"] = str(TMP)
os.environ["TEMP"] = str(TMP)

from mock_llm import MockLLMServer  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

from app.server import create_server  # noqa: E402
from app.store import Store  # noqa: E402

MOCK_PORT, PORT = 8912, 7884
BASE = f"http://127.0.0.1:{PORT}"
SHOTS = ROOT / ".setup" / "shots"
failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print(("PASS  " if condition else "FAIL  ") + name + (f" — {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(name)


def main() -> int:
    SHOTS.mkdir(parents=True, exist_ok=True)
    mock = MockLLMServer(MOCK_PORT).start()
    store = Store()
    store.save_settings(
        {
            "openai_api_key": "sk-ui-secret-777",
            "openai_base_url": mock.base_url,
            "default_llm": "openai/gpt-4o-mini",
            "live_stream": True,
        }
    )
    server = create_server("127.0.0.1", PORT)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    time.sleep(0.5)

    errors: list[str] = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            page = browser.new_page(viewport={"width": 1500, "height": 1000})
            page.on("pageerror", lambda exc: errors.append(f"pageerror: {exc}"))

            # 1. keys are not exposed in the settings screen
            page.goto(f"{BASE}/#view=settings", wait_until="domcontentloaded")
            page.wait_for_selector('[data-setting="default_llm"]')
            page.wait_for_timeout(500)
            body = page.locator("#view").inner_text()
            check("settings do not show the key", "sk-ui-secret-777" not in body)
            check("saved key is marked", page.locator("text=ключ сохранён и зашифрован").count() >= 1)
            key_input = page.locator('[data-setting="openai_api_key"]')
            check("key input is empty", key_input.input_value() == "")
            page.screenshot(path=str(SHOTS / "ui-secrets.png"))

            # 2. project + long run
            page.goto(BASE, wait_until="domcontentloaded")
            page.wait_for_selector(".sidebar")
            page.click("#btn-new-crew")
            page.wait_for_selector('[data-field="name"]')
            page.select_option('[data-field="tasks.0.agent"]', index=1)
            page.wait_for_timeout(1300)
            page.click('[data-action="run-crew"]')
            page.wait_for_selector(".pill.running", timeout=20000)
            page.wait_for_timeout(600)

            # 3. leaving the run keeps it alive and shows the indicator
            page.click('[data-action="back-to-builder"]')
            page.wait_for_selector("#workspace-input")
            page.wait_for_timeout(400)
            indicator = page.locator("#run-indicator")
            check("active run indicator appears", indicator.is_visible())
            indicator.click()
            page.wait_for_selector(".pill.running", timeout=10000)
            check("indicator returns to the run", page.locator(".run-banner").count() == 1)

            # 4. permission prompt blocks the run until answered
            page.evaluate(
                """() => { handleRunEvent('permission_request', {
                    id: 'perm-ui-1', kind: 'fs_write',
                    target: 'C:\\\\Users\\\\demo\\\\report.md',
                    reason: 'Агент хочет изменить файл',
                    agent: 'Ассистент-исследователь', timeout: 300 }); }"""
            )
            page.wait_for_selector("text=Агент запрашивает доступ", timeout=10000)
            check("permission modal opens", page.locator("text=Агент запрашивает доступ").count() == 1)
            check("modal shows the target", "report.md" in page.locator(".permission-target").inner_text())
            check("scope checkbox offered", page.locator("#perm-scope").count() == 1)
            page.screenshot(path=str(SHOTS / "ui-permission.png"))

            # the prompt can be dismissed and reopened without losing the request
            page.keyboard.press("Escape")
            page.wait_for_timeout(250)
            check("closing the prompt shows the banner", page.locator("#perm-banner").is_visible())
            check("banner names the target", "report.md" in page.locator("#perm-banner-text").inner_text())
            page.click('[data-action="show-permission"]')
            page.wait_for_timeout(250)
            check("banner reopens the prompt", page.locator(".permission-target").count() == 1)
            check("reopened prompt keeps the target", "report.md" in page.locator(".permission-target").inner_text())

            page.click('[data-action="perm-allow"]')
            page.wait_for_timeout(700)
            check("modal closes after the answer", page.locator(".permission-target").count() == 0)

            # 5. run finishes and the indicator disappears
            page.wait_for_selector(".pill.completed", timeout=120000)
            page.wait_for_timeout(500)
            check("indicator hidden after completion", not page.locator("#run-indicator").is_visible())

            # 6. template creation from the templates screen
            page.goto(f"{BASE}/#view=templates", wait_until="domcontentloaded")
            page.wait_for_selector('[data-action="new-template"]')
            page.click('[data-action="new-template"]')
            page.wait_for_selector("#tpl-title")
            page.fill("#tpl-title", "Шаблон из UI")
            page.fill("#tpl-desc", "Проверка создания")
            page.click('[data-action="confirm-new-template"]')
            page.wait_for_timeout(900)
            check("custom template created from UI", page.locator(".template-card.custom").count() == 1)
            page.hover(".template-card.custom")
            page.click(".template-card.custom [data-action='edit-template']")
            page.wait_for_selector('[data-action="save-template-crew"]')
            page.fill('[data-field="name"]', "Шаблон переименован")
            page.click('[data-action="save-template-crew"]')
            page.wait_for_timeout(1200)
            page.click('[data-action="cancel-template-edit"]')
            page.wait_for_timeout(800)
            check("template renamed", "Шаблон переименован" in page.locator(".template-card.custom").inner_text())
            page.screenshot(path=str(SHOTS / "ui-templates.png"))

            # 7. optional tools explain how to install themselves
            page.locator(".crew-item").first.click()
            page.wait_for_selector('[data-field="name"]')
            page.wait_for_timeout(400)
            if page.locator(".tool-option.unavailable").count():
                page.locator(".tool-option.unavailable").first.click()
                page.wait_for_selector('[data-action="install-tools"]', timeout=10000)
                check("unavailable tool opens install dialog", page.locator("text=Инструмент не установлен").count() == 1)
                check("install dialog mentions the package", "crewai-tools" in page.locator(".modal-body").inner_text())
                page.screenshot(path=str(SHOTS / "ui-install-tool.png"))
                page.click('[data-action="close-modal"]')
                page.wait_for_timeout(300)
            else:
                print("SKIP  install dialog (all optional tools installed)")

            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        mock.stop()
        time.sleep(0.2)

    check("no JavaScript errors", not errors, " | ".join(errors[:4]))
    print("\nUI CONFIRMATIONS RESULT:", "PASS" if not failures else f"FAIL ({len(failures)}): {failures}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
