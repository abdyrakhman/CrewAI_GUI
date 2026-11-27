"""Browser UI test with Playwright (uses the installed Google Chrome).

Covers the paths a user takes: create a project, edit an agent, run it, watch
the live stream, cancel a run, and open every section — while failing on any
JavaScript console error.
"""
from __future__ import annotations

import os
import sys
import threading
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

DATA = ROOT / ".setup" / f"ui-{uuid.uuid4().hex[:8]}"
DATA.mkdir(parents=True, exist_ok=True)
os.environ["CREWAI_STUDIO_DATA"] = str(DATA)
os.environ["CREWAI_STUDIO_NO_AUTH"] = "1"
os.environ["MOCK_DELAY"] = "0.05"
# Chrome/Playwright need scratch space the sandboxed TEMP does not provide.
TMP = ROOT / ".setup" / "tmp"
TMP.mkdir(parents=True, exist_ok=True)
os.environ["TMP"] = str(TMP)
os.environ["TEMP"] = str(TMP)

from mock_llm import MockLLMServer  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

from app.server import create_server  # noqa: E402
from app.store import Store  # noqa: E402

MOCK_PORT = 8904
APP_PORT = 7872
BASE = f"http://127.0.0.1:{APP_PORT}"
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
            "openai_api_key": "sk-test",
            "openai_base_url": mock.base_url,
            "default_llm": "openai/gpt-4o-mini",
            "live_stream": True,
        }
    )
    server = create_server("127.0.0.1", APP_PORT)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    time.sleep(0.5)

    console_errors: list[str] = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            page = browser.new_page(viewport={"width": 1500, "height": 1000})
            page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
            page.on("pageerror", lambda exc: console_errors.append(f"pageerror: {exc}"))
            page.on("framenavigated", lambda frame: print("NAV:", frame.url))

            page.goto(BASE, wait_until="domcontentloaded")
            page.wait_for_selector(".sidebar")
            check("app shell renders", page.locator(".brand-text strong").inner_text() == "CrewAI Studio")

            # 1. create a project from the sidebar button
            page.click("#btn-new-crew")
            page.wait_for_selector('[data-field="name"]', timeout=10000)
            check("new project opens builder", page.locator('[data-field="name"]').count() == 1)

            # 2. edit project + agent, expect autosave
            page.fill('[data-field="name"]', "UI проверка")
            page.fill('[data-field="agents.0.role"]', "Аналитик")
            page.fill('[data-field="agents.0.goal"]', "Разобрать тему {тема}")
            page.fill('[data-field="agents.0.backstory"]', "Опытный аналитик с 10-летним стажем.")
            page.fill('[data-field="tasks.0.description"]', "Собери короткий разбор темы {тема}")
            page.fill('[data-field="tasks.0.expected_output"]', "Список из трёх пунктов")
            page.fill('[data-field="inputs.0.value"]', "ИИ в логистике")
            page.wait_for_timeout(2200)
            save_state = page.locator("#save-state").inner_text()
            check("autosave reports saved", "сохранено" in save_state, save_state)

            # agent select in the task must now offer the renamed agent
            page.select_option('[data-field="tasks.0.agent"]', index=1)
            options = page.locator('[data-field="tasks.0.agent"] option').all_inner_texts()
            check("task agent list is populated", any("Аналитик" in text for text in options), str(options))
            page.wait_for_timeout(1200)

            page.screenshot(path=str(SHOTS / "ui-builder.png"), full_page=False)

            # 3. run it
            page.click('[data-action="run-crew"]')
            page.wait_for_selector('[data-run-task]', timeout=20000)
            page.wait_for_timeout(700)
            page.screenshot(path=str(SHOTS / "ui-running.png"))
            try:
                page.wait_for_selector(".pill.completed", timeout=90000)
            except Exception:
                print("DIAG view:", page.evaluate("window.__studio && window.__studio.view"))
                print("DIAG crews:", page.evaluate("window.__studio && window.__studio.crews.length"))
                print("DIAG hash:", page.evaluate("location.hash"))
                print("DIAG url:", page.url)
                print("DIAG boot:", page.evaluate("window.__studio && window.__studio.__boot"))
                print("DIAG loaded:", page.evaluate("document.readyState"))
                print("DIAG appjs loads:", page.evaluate("performance.getEntriesByType('resource').filter(e=>e.name.includes('app.js')).length"))
                print("DIAG init calls:", page.evaluate("window.__initCalls || 0"))
                print("DIAG scripts:", page.evaluate("document.scripts.length"))
                print("DIAG pill:", page.locator("#run-pill").inner_text() if page.locator("#run-pill").count() else "none")
                print("DIAG body:", page.locator("#view").inner_text()[:1200].replace("\n", " | "))
                print("DIAG console:", console_errors[-5:])
                page.screenshot(path=str(SHOTS / "ui-failed.png"))
                raise
            check("run completes in UI", page.locator(".pill.completed").count() == 1)
            body = page.locator("#run-final").inner_text() if page.locator("#run-final").count() else ""
            check("result panel shows model output", len(body) > 40, body[:80])
            page.wait_for_timeout(400)
            page.screenshot(path=str(SHOTS / "ui-run-done.png"))

            # 4. cancel a slower run
            page.click('[data-action="rerun"]')
            page.wait_for_selector(".pill.running", timeout=30000)
            page.click('[data-action="cancel-run"]')
            page.wait_for_selector(".pill.cancelled", timeout=60000)
            check("cancel stops the run", page.locator(".pill.cancelled").count() == 1)

            # 5. every section renders
            for view, marker in (
                ("templates", ".template-card"),
                ("history", ".table"),
                ("files", ".card"),
                ("settings", '[data-setting="default_llm"]'),
            ):
                page.goto(f"{BASE}/#view={view}", wait_until="domcontentloaded")
                page.wait_for_selector(marker, timeout=15000)
                check(f"view «{view}» renders", page.locator(marker).count() > 0)
            page.screenshot(path=str(SHOTS / "ui-settings.png"))


            # run limits and diagnostics are reachable from settings
            page.wait_for_selector('[data-setting="run_timeout_minutes"]', timeout=15000)
            page.select_option('[data-setting="run_timeout_minutes"]', "30")
            page.fill('[data-setting="max_iter_cap"]', "7")
            page.click('[data-action="save-settings"]')
            page.wait_for_timeout(1200)
            saved = page.evaluate("() => fetch('/api/settings').then((r) => r.json())")
            settings_now = (saved or {}).get("settings", {})
            check(
                "run limits card exists and saves",
                int(float(settings_now.get("run_timeout_minutes") or 0)) == 30
                and int(float(settings_now.get("max_iter_cap") or 0)) == 7,
                f"{settings_now.get('run_timeout_minutes')}/{settings_now.get('max_iter_cap')}",
            )
            check("diagnostics card is present", page.locator('[data-action="show-errors"]').count() == 1)

            # toggles must not scroll the page when they receive focus
            project_id = page.evaluate("window.__studio.crew?.id")
            page.goto(f"{BASE}/#crew={project_id}", wait_until="domcontentloaded")
            page.wait_for_selector('[data-field="name"]', timeout=20000)
            page.wait_for_timeout(800)
            page.evaluate("() => window.scrollTo(0, 0)")
            toggle = page.locator("label.toggle", has_text="Подтверждение изменений").first
            toggle.scroll_into_view_if_needed()
            page.wait_for_timeout(300)
            page.evaluate("() => window.scrollTo(0, 0)")
            before_y = page.evaluate("window.scrollY")
            toggle.click()
            page.wait_for_timeout(700)
            after_y = page.evaluate("window.scrollY")
            check("toggle does not scroll the page", abs(after_y - before_y) < 60, f"{before_y} -> {after_y}")

            # 6. export and code preview endpoints through the UI helpers
            page.goto(f"{BASE}/#view=history", wait_until="domcontentloaded")
            page.wait_for_selector('[data-action="open-run"]', timeout=15000)
            page.locator('tr:has(.chip.ok) [data-action="open-run"]').first.click()
            page.wait_for_selector("#run-final", timeout=20000)
            check("history opens a stored run", page.locator("#run-final").count() == 1)

            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        mock.stop()
        time.sleep(0.2)

    relevant = [error for error in console_errors if "favicon" not in error.lower()]
    check("no JavaScript console errors", not relevant, " | ".join(relevant[:4]))

    print("\nUI RESULT:", "PASS" if not failures else f"FAIL ({len(failures)}): {failures}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
