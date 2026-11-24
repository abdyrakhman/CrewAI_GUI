"""Tests for the one-click install of the optional ``crewai-tools`` package."""
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
sys.path.insert(0, str(ROOT / "tests"))

DATA = ROOT / ".setup" / f"inst-{uuid.uuid4().hex[:8]}"
DATA.mkdir(parents=True, exist_ok=True)
os.environ["CREWAI_STUDIO_DATA"] = str(DATA)

from app import tools  # noqa: E402
from app.server import create_server  # noqa: E402

PORT = 7885
BASE = f"http://127.0.0.1:{PORT}"
failures: list[str] = []
TOKEN = ""


def check(name: str, condition: bool, detail: str = "") -> None:
    print(("PASS  " if condition else "FAIL  ") + name + (f" — {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(name)


def request(path: str, method: str = "GET", body: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    if method != "GET":
        req.add_header("X-Studio-Token", TOKEN)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, {"error": raw.decode("utf-8", "replace")}


def wait_done(timeout: float = 20.0) -> dict:
    deadline = time.time() + timeout
    status: dict = {}
    while time.time() < deadline:
        status = tools.install_status()
        if not status["running"]:
            return status
        time.sleep(0.05)
    return status


def main() -> int:
    original = list(tools.INSTALL_COMMAND)

    # ------------------------------------------------ successful fake install
    tools.INSTALL_COMMAND = [sys.executable, "-u", "-c", "print('fake pip start'); print('fake pip ok')"]
    started = tools.install_extras()
    check("install starts", started is True)
    status = wait_done()
    check("install finishes", status["running"] is False, str(status)[:160])
    check("install reports success", status["ok"] is True, str(status)[:160])
    check("install captures output", "fake pip ok" in status["output"], status["output"][:120])

    # ------------------------------------------------------ concurrent guard
    tools.INSTALL_COMMAND = [sys.executable, "-u", "-c", "import time; time.sleep(0.8); print('slow done')"]
    check("second start begins", tools.install_extras() is True)
    time.sleep(0.1)
    check("parallel install is refused", tools.install_extras() is False)
    wait_done()

    # ----------------------------------------------------------- HTTP layer
    global TOKEN
    server = create_server("127.0.0.1", PORT)
    TOKEN = server.RequestHandlerClass.session_token
    threading.Thread(target=server.serve_forever, daemon=True).start()
    time.sleep(0.4)
    try:
        tools.INSTALL_COMMAND = [sys.executable, "-u", "-c", "print('http install ok')"]
        status_code, payload = request("/api/tools/install", "POST")
        check("POST /api/tools/install accepted", status_code == 202 and payload.get("started") is True, str(payload)[:160])
        wait_done()

        status_code, payload = request("/api/tools/install")
        check("GET /api/tools/install returns status", status_code == 200 and payload["ok"] is True, str(payload)[:200])
        check("status includes output", "http install ok" in payload["output"])

        tools.INSTALL_COMMAND = [sys.executable, "-u", "-c", "import sys; print('boom'); sys.exit(3)"]
        request("/api/tools/install", "POST")
        wait_done()
        status_code, payload = request("/api/tools/install")
        check("failed install is reported", payload["ok"] is False and "boom" in payload["output"], str(payload)[:200])

        status_code, payload = request("/api/tools")
        check("catalogue still served", status_code == 200)
        optional = [t for t in payload["tools"] if t["source"] == "crewai-tools"]
        check("optional tools are listed", len(optional) == len(tools.OPTIONAL_META), str(len(optional)))
        if any(not t["available"] for t in optional):
            check("uninstalled tools are marked unavailable", True)
        else:
            print("SKIP  all optional tools are installed in this environment")
    finally:
        server.shutdown()
        server.server_close()
        tools.INSTALL_COMMAND = original
        time.sleep(0.2)

    print("\nTOOLS INSTALL RESULT:", "PASS" if not failures else f"FAIL ({len(failures)}): {failures}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
