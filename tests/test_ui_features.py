"""Browser test for the role library, custom templates and project deletion."""
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

DATA = ROOT / ".setup" / f"uifeat-{uuid.uuid4().hex[:8]}"
DATA.mkdir(parents=True, exist_ok=True)
os.environ["CREWAI_STUDIO_DATA"] = str(DATA)
TMP = ROOT / ".setup" / "tmp"
TMP.mkdir(parents=True, exist_ok=True)
os.environ["TMP"] = str(TMP)
os.environ["TEMP"] = str(TMP)

from playwright.sync_api import sync_playwright  # noqa: E402

from app.server import create_server  # noqa: E402

PORT = 7877
BASE = f"http://127.0.0.1:{PORT}"
SHOTS = ROOT / ".setup" / "shots"
failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print(("PASS  " if condition else "FAIL  ") + name + (f" — {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(name)


def main() -> int:
    SHOTS.mkdir(parents=True, exist_ok=True)
    server = create_server("127.0.0.1", PORT)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    time.sleep(0.5)

    errors: list[str] = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            page = browser.new_page(viewport={"width": 1500, "height": 1000})
            page.on("pageerror", lambda exc: errors.append(f"pageerror: {exc}"))
            page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)

            page.goto(f"{BASE}/#view=roles", wait_until="domcontentloaded")
            page.wait_for_selector(".role-card")
            roles_before = page.evaluate("window.__studio.roles.length")
            check("roles view lists library", roles_before >= 10, str(roles_before))

            # 1. create a role
            page.click('.topbar [data-action="new-role"]')
            page.wait_for_selector("#role-name")
            page.fill("#role-name", "Методист")
            page.fill("#role-goal", "Собрать методику и проверить её на практике")
            page.fill("#role-experience", "8 лет преподавания и методологии.")
            page.fill("#role-character", "Терпеливый, любит структуру и примеры.")
            page.click('[data-action="save-role"]')
            page.wait_for_timeout(600)
            roles_after = page.evaluate("window.__studio.roles.length")
            check("role created via UI", roles_after == roles_before + 1, f"{roles_before} -> {roles_after}")

            # 2. project + apply the role through the picker
            page.click("#btn-new-crew")
            page.wait_for_selector('[data-field="name"]')
            page.click('[data-action="apply-role"][data-index="0"]')
            page.wait_for_selector(".role-pick")
            page.locator(".role-pick", has_text="Методист").first.click()
            page.wait_for_timeout(500)
            agent = page.evaluate("window.__studio.crew.agents[0]")
            check("role applied to agent", agent["role"] == "Методист", str(agent.get("role")))
            check("goal filled from role", agent["goal"] == "Собрать методику и проверить её на практике", str(agent.get("goal")))
            check("backstory composed from experience+character",
                  "8 лет преподавания" in agent["backstory"] and "Терпеливый" in agent["backstory"],
                  str(agent.get("backstory")))
            page.screenshot(path=str(SHOTS / "ui-role-applied.png"))

            # 3. persistence after reload
            page.wait_for_timeout(1600)
            crew_id = page.evaluate("window.__studio.crew.id")
            page.goto(f"{BASE}/#crew={crew_id}", wait_until="domcontentloaded")
            page.wait_for_selector('[data-field="name"]')
            page.wait_for_timeout(600)
            saved_role = page.evaluate("window.__studio.crew.agents[0].role")
            check("role survives reload (autosave)", saved_role == "Методист", str(saved_role))

            # 4. save project as template
            page.click('[data-action="save-as-template"]')
            page.wait_for_selector("#tpl-title")
            page.fill("#tpl-title", "Методический шаблон")
            page.fill("#tpl-desc", "Команда с ролью Методист")
            page.click('[data-action="confirm-save-template"]')
            page.wait_for_timeout(800)
            templates = page.evaluate("window.__studio.templates.map(t => ({title: t.title, custom: !!t.custom}))")
            check("template saved from project", any(t["custom"] and t["title"] == "Методический шаблон" for t in templates), str(templates))

            # 5. template appears in the section and can create a project
            page.goto(f"{BASE}/#view=templates", wait_until="domcontentloaded")
            page.wait_for_selector(".template-card.custom")
            check("custom template card rendered", page.locator(".template-card.custom").count() == 1)
            page.locator(".template-card.custom").first.click()
            page.wait_for_selector('[data-field="name"]', timeout=15000)
            page.wait_for_timeout(500)
            check("project created from custom template",
                  page.evaluate("window.__studio.crew.name") == "Методический шаблон",
                  page.evaluate("window.__studio.crew.name"))
            crews_now = page.evaluate("window.__studio.crews.length")

            # 6. delete the template
            page.goto(f"{BASE}/#view=templates", wait_until="domcontentloaded")
            page.wait_for_selector(".template-card.custom")
            page.locator(".template-card.custom [data-action='delete-template']").first.click()
            page.wait_for_selector('[data-action="confirm-delete-template"]')
            page.click('[data-action="confirm-delete-template"]')
            page.wait_for_timeout(700)
            check("template deleted", page.locator(".template-card.custom").count() == 0)

            # 7. delete a project from the sidebar
            page.goto(f"{BASE}/#view=builder", wait_until="domcontentloaded")
            page.wait_for_selector(".crew-item")
            page.locator(".crew-item").first.hover()
            page.locator(".crew-item [data-action='delete-crew-by-id']").first.click()
            page.wait_for_selector('[data-action="confirm-delete-crew"]')
            page.click('[data-action="confirm-delete-crew"]')
            page.wait_for_timeout(800)
            crews_after = page.evaluate("window.__studio.crews.length")
            check("project deleted from sidebar", crews_after == crews_now - 1, f"{crews_now} -> {crews_after}")

            page.screenshot(path=str(SHOTS / "ui-roles.png"))
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        time.sleep(0.2)

    relevant = [error for error in errors if "favicon" not in error.lower()]
    check("no JavaScript console errors", not relevant, " | ".join(relevant[:4]))
    print("\nUI FEATURES RESULT:", "PASS" if not failures else f"FAIL ({len(failures)}): {failures}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
