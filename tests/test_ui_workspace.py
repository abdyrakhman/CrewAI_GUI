"""Browser test for choosing a project workspace folder."""
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

DATA = ROOT / ".setup" / f"uiws-{uuid.uuid4().hex[:8]}"
DATA.mkdir(parents=True, exist_ok=True)
os.environ["CREWAI_STUDIO_DATA"] = str(DATA)
os.environ["CREWAI_STUDIO_NO_AUTH"] = "1"
TMP = ROOT / ".setup" / "tmp"
TMP.mkdir(parents=True, exist_ok=True)
os.environ["TMP"] = str(TMP)
os.environ["TEMP"] = str(TMP)

from playwright.sync_api import sync_playwright  # noqa: E402

from app.server import create_server  # noqa: E402

PORT = 7880
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
    console_errors: list[str] = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            page = browser.new_page(viewport={"width": 1500, "height": 1000})
            page.on("pageerror", lambda exc: errors.append(f"pageerror: {exc}"))
            page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

            page.goto(BASE, wait_until="domcontentloaded")
            page.wait_for_selector(".sidebar")
            page.click("#btn-new-crew")
            page.wait_for_selector("#workspace-input")

            default_path = page.evaluate("window.__studio.workspaceInfo.path")
            default_marker = page.evaluate("window.__studio.workspaceInfo.is_default")
            check("new project shows default workspace", default_marker is True, str(default_path))
            check("default workspace path shown in UI",
                  page.locator(".workspace-line, .hint-text.mono").first.inner_text().strip() != "")

            # 1. open the picker
            page.click('[data-action="pick-workspace"]')
            page.wait_for_selector("#fs-picker .fs-list")
            check("picker opens with directory list", page.locator(".fs-item").count() > 0)
            check("picker shows current path", "CrewAI" in page.input_value("#fs-path"), page.input_value("#fs-path"))

            # 2. create a folder inside the current directory and enter it
            page.fill("#fs-new-name", "agent-workspace")
            page.click('[data-action="fs-mkdir"]')
            page.wait_for_timeout(700)
            check("new folder created and opened", page.input_value("#fs-path").endswith("agent-workspace"), page.input_value("#fs-path"))
            page.screenshot(path=str(SHOTS / "ui-workspace-picker.png"))

            # 3. choose it
            page.click('[data-action="fs-choose"]')
            page.wait_for_timeout(800)
            chosen = page.evaluate("window.__studio.crew.workspace")
            info = page.evaluate("window.__studio.workspaceInfo")
            check("workspace saved on project", chosen.endswith("agent-workspace"), str(chosen))
            check("workspace folder exists on disk", info["exists"] is True, str(info))
            check("ui shows chosen path", page.input_value("#workspace-input").endswith("agent-workspace"))
            check("default marker gone", page.evaluate("window.__studio.workspaceInfo.is_default") is False)

            # 4. persists after reload
            page.wait_for_timeout(900)
            crew_id = page.evaluate("window.__studio.crew.id")
            page.goto(f"{BASE}/#crew={crew_id}", wait_until="domcontentloaded")
            page.wait_for_selector("#workspace-input")
            page.wait_for_timeout(500)
            check("workspace survives reload", page.input_value("#workspace-input").endswith("agent-workspace"),
                  page.input_value("#workspace-input"))

            # 5. invalid path is rejected with a visible error
            page.fill("#workspace-input", str(ROOT / "run.py"))
            page.dispatch_event("#workspace-input", "change")
            page.wait_for_timeout(700)
            check("file path rejected with error toast", page.locator(".toast.err").count() > 0)
            check("workspace unchanged after error", page.evaluate("window.__studio.crew.workspace").endswith("agent-workspace"))

            # 6. reset to the default folder
            page.click('[data-action="reset-workspace"]')
            page.wait_for_timeout(800)
            check("workspace reset to default", page.evaluate("window.__studio.workspaceInfo.is_default") is True,
                  page.evaluate("window.__studio.crew.workspace"))

            # 7. files view shows the workspace
            page.goto(f"{BASE}/#view=files", wait_until="domcontentloaded")
            page.wait_for_selector("text=Рабочая область проекта")
            check("files view lists workspace", page.locator("text=Рабочая область проекта").count() == 1)
            page.screenshot(path=str(SHOTS / "ui-workspace-files.png"))

            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        time.sleep(0.2)

    check("no JavaScript errors", not errors, " | ".join(errors[:4]))
    # The picker deliberately probes folders that do not exist (400 by design),
    # and the test sends an invalid path on purpose.
    unexpected = [
        text for text in console_errors
        if "favicon" not in text.lower() and "Failed to load resource" not in text
    ]
    check("no unexpected console errors", not unexpected, " | ".join(unexpected[:4]))
    print("\nUI WORKSPACE RESULT:", "PASS" if not failures else f"FAIL ({len(failures)}): {failures}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
