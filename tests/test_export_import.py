"""Project export/import, data backup and the removed account roles."""
from __future__ import annotations

import io
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DATA = ROOT / ".setup" / f"export-{uuid.uuid4().hex[:6]}"
for sub in ("crews", "runs", "outputs", "uploads", "logs", "templates"):
    (DATA / sub).mkdir(parents=True, exist_ok=True)
os.environ["CREWAI_STUDIO_DATA"] = str(DATA)
os.environ["CREWAI_STUDIO_NO_AUTH"] = "1"

from app.server import create_server  # noqa: E402
from app.spec import normalize_crew  # noqa: E402
from app.store import Store  # noqa: E402

PORT = 7905
BASE = f"http://127.0.0.1:{PORT}"
failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print(("PASS  " if condition else "FAIL  ") + name + (f" — {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(name)


def raw(path: str, method: str = "GET", body: dict | None = None, token: str = "") -> tuple[int, bytes, dict]:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(BASE + path, data=data, method=method)
    if data is not None:
        request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("X-Studio-Token", token)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, response.read(), dict(response.getheaders())
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), dict(exc.headers)


def api_json(path: str, method: str = "GET", body: dict | None = None, token: str = "") -> tuple[int, dict]:
    status, payload, _ = raw(path, method, body, token)
    try:
        return status, json.loads(payload)
    except json.JSONDecodeError:
        return status, {"raw": payload[:200].decode("utf-8", "replace")}


def main() -> int:
    store = Store()
    crew = normalize_crew({
        "name": "Экспортируемый проект",
        "description": "проверка экспорта",
        "agents": [{"role": "Аналитик", "goal": "Собрать факты", "backstory": "Опытный"}],
        "tasks": [{"description": "Собери факты", "expected_output": "Список"}],
    })
    crew["tasks"][0]["agent"] = crew["agents"][0]["id"]
    saved = store.save_crew(crew)
    store.save_settings({"runs_retention_days": 180})
    store.save_run({
        "id": "run-backup",
        "crew_id": saved["id"],
        "crew_name": saved["name"],
        "status": "completed",
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "duration": 5,
        "usage": {"total_tokens": 10},
        "events": [],
        "result": {},
    })

    server = create_server("127.0.0.1", PORT)
    admin_password = str((getattr(server, "generated_admin", {}) or {}).get("password") or "")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    time.sleep(0.6)

    try:
        page = raw("/")[1].decode("utf-8")
        token = re.search(r'name="studio-token" content="([^"]+)"', page).group(1)

        # ---------------------------------------------------------- export
        status, payload, headers = raw(f"/api/crews/{saved['id']}/export")
        check("export returns the project", status == 200 and b'"format": "crewai-studio-project"' in payload, str(status))
        check("export is a download", "attachment" in headers.get("Content-Disposition", ""),
              headers.get("Content-Disposition", ""))
        document = json.loads(payload)
        check("export keeps agents and tasks",
              len(document["crew"]["agents"]) == 1 and len(document["crew"]["tasks"]) == 1)

        # ---------------------------------------------------------- import
        status, imported = api_json("/api/crews/import", "POST", {"crew": document["crew"]}, token)
        check("import creates a new project", status == 201 and imported["crew"]["id"] != saved["id"], str(imported)[:120])
        check("import keeps the team",
              len(imported["crew"]["agents"]) == 1 and len(imported["crew"]["tasks"]) == 1)
        check("imported project has no workspace", imported["crew"]["workspace"] == "")

        status, imported_raw = api_json("/api/crews/import", "POST", {"crew": {"name": "Пусто"}}, token)
        check("import rejects an empty project", status == 400, str(imported_raw)[:100])

        # ---------------------------------------------------------- backup
        status, payload, headers = raw("/api/backup")
        check("backup returns a zip", status == 200 and payload[:2] == b"PK", str(status))
        check("backup is a download", "attachment" in headers.get("Content-Disposition", ""),
              headers.get("Content-Disposition", ""))
        names = zipfile.ZipFile(io.BytesIO(payload)).namelist()
        check("backup has projects and settings",
              any(name.startswith("crews/") for name in names) and "settings.json" in names and "users.json" in names,
              str(names[:8]))
        check("backup skips sessions and logs",
              "sessions.json" not in names and not any(name.startswith("logs/") for name in names), str(names[:8]))

        status, payload, _ = raw("/api/backup?runs=1")
        names = zipfile.ZipFile(io.BytesIO(payload)).namelist()
        check("backup can include runs", any(name.startswith("runs/") for name in names), str(names[:8]))

        # ------------------------------------------------------- no roles
        status, login = api_json("/api/auth/login", "POST", {"username": "admin", "password": admin_password})
        check("login has no account role", status == 200 and "role" not in login, str(login)[:100])
        users = json.loads((DATA / "users.json").read_text(encoding="utf-8"))
        check("users file has no roles", all("role" not in record for record in users.values()), str(users)[:120])
    finally:
        server.shutdown()
        server.server_close()

    print("\nEXPORT RESULT:", "PASS" if not failures else f"FAIL ({len(failures)}): {failures}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
