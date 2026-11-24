"""API tests for the role library, custom templates and project deletion."""
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

DATA = ROOT / ".setup" / f"feat-{uuid.uuid4().hex[:8]}"
DATA.mkdir(parents=True, exist_ok=True)
os.environ["CREWAI_STUDIO_DATA"] = str(DATA)

from app.server import create_server  # noqa: E402

PORT = 7876
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
        with urllib.request.urlopen(req, timeout=60) as response:
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, {"error": raw.decode("utf-8", "replace")}


def main() -> int:
    global TOKEN
    server = create_server("127.0.0.1", PORT)
    TOKEN = server.RequestHandlerClass.session_token
    threading.Thread(target=server.serve_forever, daemon=True).start()
    time.sleep(0.4)
    try:
        # ---------------------------------------------------------- roles
        status, payload = request("/api/roles")
        roles = payload.get("roles", [])
        check("GET /api/roles seeds defaults", status == 200 and len(roles) >= 10, str(status))
        check("default role has goal and backstory parts",
              bool(roles[0].get("goal")) and bool(roles[0].get("experience")) and bool(roles[0].get("character")))

        status, payload = request("/api/roles", "POST", {
            "name": "Тестовая роль", "goal": "Проверить всё", "experience": "Опыт 5 лет",
            "character": "Внимательный", "tools": ["fetch_url"],
        })
        role = payload.get("role", {})
        check("POST /api/roles creates", status == 201 and role.get("name") == "Тестовая роль", str(payload)[:200])
        check("role gets id", bool(role.get("id")))

        status, payload = request(f"/api/roles/{role['id']}", "PUT", {"character": "Очень внимательный"})
        check("PUT /api/roles updates", status == 200 and payload["role"]["character"] == "Очень внимательный")
        check("update keeps experience", payload["role"]["experience"] == "Опыт 5 лет")

        status, payload = request("/api/roles", "POST", {"name": "", "goal": "x"})
        check("role without name rejected", status == 400, str(payload)[:120])

        status, payload = request(f"/api/roles/{role['id']}", "DELETE")
        check("DELETE /api/roles removes", status == 200 and payload.get("ok"))
        status, payload = request("/api/roles")
        check("deleted role is gone", all(item["id"] != role["id"] for item in payload["roles"]))

        status, payload = request("/api/roles/reset", "POST")
        check("POST /api/roles/reset restores defaults", status == 200 and len(payload["roles"]) >= 10)

        # ------------------------------------------------------ templates
        status, payload = request("/api/crews", "POST", {"template": "research-brief"})
        crew = payload.get("crew", {})
        check("template-based project created", status == 201, str(payload)[:150])

        status, payload = request("/api/templates")
        builtin_count = len(payload.get("templates", []))
        check("builtin templates listed", status == 200 and builtin_count >= 4)

        status, payload = request("/api/templates", "POST",
                                  {"crew_id": crew["id"], "title": "Мой бриф", "description": "Из проекта"})
        template = payload.get("template", {})
        check("POST /api/templates saves project", status == 201 and template.get("title") == "Мой бриф", str(payload)[:200])
        check("custom template flagged", template.get("custom") is True)
        check("custom template has subtitle", "агент" in (template.get("subtitle") or ""))

        status, payload = request("/api/templates")
        check("custom template appears in list",
              any(item["key"] == template["key"] for item in payload["templates"]))
        check("custom templates come first", payload["templates"][0]["key"] == template["key"])

        status, payload = request("/api/templates", "POST", {"crew_id": crew["id"], "title": ""})
        check("template without title rejected", status == 400, str(payload)[:120])

        status, payload = request("/api/crews", "POST", {"template": template["key"]})
        created = payload.get("crew", {})
        check("project can be created from custom template", status == 201 and created.get("name") == "Мой бриф", str(payload)[:200])
        check("template copy has agents", len(created.get("agents", [])) == 3)
        check("template copy has new id", created.get("id") != crew.get("id"))

        status, payload = request(f"/api/templates/{template['key']}", "DELETE")
        check("DELETE /api/templates removes", status == 200 and payload.get("ok"))
        status, payload = request("/api/templates")
        check("deleted template is gone", all(item["key"] != template["key"] for item in payload["templates"]))

        # --------------------------------------------------- delete projects
        status, payload = request(f"/api/crews/{created['id']}", "DELETE")
        check("DELETE /api/crews removes project", status == 200 and payload.get("ok"))
        status, payload = request(f"/api/crews/{created['id']}")
        check("deleted project returns 404", status == 404)
        status, payload = request("/api/crews")
        check("project list shrinks", all(item["id"] != created["id"] for item in payload.get("crews", [])))

        status, payload = request("/api/crews/does-not-exist", "DELETE")
        check("deleting missing project is safe", status == 200 and payload.get("ok") is False)
    finally:
        server.shutdown()
        server.server_close()
        time.sleep(0.2)

    print("\nFEATURES RESULT:", "PASS" if not failures else f"FAIL ({len(failures)}): {failures}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
