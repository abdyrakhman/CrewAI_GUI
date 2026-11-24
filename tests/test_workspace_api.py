"""API tests for project workspaces: picker, validation, files and a real run."""
from __future__ import annotations

import base64
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

DATA = ROOT / ".setup" / f"wsapi-{uuid.uuid4().hex[:8]}"
DATA.mkdir(parents=True, exist_ok=True)
os.environ["CREWAI_STUDIO_DATA"] = str(DATA)
os.environ["MOCK_DELAY"] = "0.001"

from mock_llm import MockLLMServer  # noqa: E402

from app.server import create_server  # noqa: E402

MOCK_PORT = 8908
PORT = 7879
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
        with urllib.request.urlopen(req, timeout=90) as response:
            raw = response.read()
            return response.status, json.loads(raw or b"{}")
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, {"error": raw.decode("utf-8", "replace")}


def main() -> int:
    mock = MockLLMServer(MOCK_PORT).start()
    global TOKEN
    server = create_server("127.0.0.1", PORT)
    TOKEN = server.RequestHandlerClass.session_token
    threading.Thread(target=server.serve_forever, daemon=True).start()
    time.sleep(0.5)

    workspace_dir = DATA / "my-workspace"
    try:
        # ---------------------------------------------------------- filesystem
        status, payload = request(f"/api/fs?path={urllib.parse.quote(str(DATA))}")
        check("GET /api/fs lists directories", status == 200 and payload["path"] == str(DATA), str(payload)[:120])
        check("fs response has drives", isinstance(payload.get("drives"), list) and payload["drives"], str(payload.get("drives")))
        check("fs reports read and write access",
              payload.get("readable") is True and payload.get("writable") is True,
              f"readable={payload.get('readable')} writable={payload.get('writable')}")
        check("fs response has parent", bool(payload.get("parent")))

        status, payload = request("/api/fs?path=Z%3A%5Cdefinitely-missing-folder-xyz")
        check("missing folder returns 400", status == 400, str(payload)[:120])

        # A folder outside the allowed roots can be allowed from the picker.
        anchor = Path(ROOT.anchor if hasattr(ROOT, "anchor") else "/")
        status, payload = request(f"/api/fs?path={urllib.parse.quote(str(anchor))}")
        check("drive root is blocked before permission", status in {400, 403}, str(payload)[:120])
        settings = request("/api/settings")[1]
        roots = list(settings["settings"].get("fs_roots") or [])
        roots.append(str(anchor))
        status, payload = request("/api/settings", "PUT", {"settings": {"fs_roots": roots}})
        check("root can be saved in settings", status == 200 and str(anchor) in payload["settings"]["fs_roots"], str(payload)[:140])
        status, payload = request(f"/api/fs?path={urllib.parse.quote(str(anchor))}")
        check("drive root becomes browsable after permission", status == 200, str(payload)[:120])

        status, payload = request("/api/fs/mkdir", "POST", {"parent": str(DATA), "name": "nested"})
        check("POST /api/fs/mkdir creates folder", status == 201 and Path(payload["path"]).is_dir(), str(payload)[:120])
        status, payload = request("/api/fs/mkdir", "POST", {"parent": str(DATA), "name": "nested"})
        check("duplicate folder rejected", status == 400, str(payload)[:120])
        status, payload = request("/api/fs/mkdir", "POST", {"parent": str(DATA), "name": "../escape"})
        check("path-like folder name rejected", status == 400, str(payload)[:120])

        # --------------------------------------------------------------- crew
        status, payload = request("/api/crews", "POST", {"crew": {
            "name": "Проект с областью",
            "default_llm": "openai/gpt-4o-mini",
            "agents": [{"role": "Аналитик", "goal": "Сделать отчёт", "backstory": "Опытный"}],
            "tasks": [{"name": "Отчёт", "description": "Сделай отчёт", "expected_output": "Файл",
                       "output_format": "file", "output_file": "result.md"}],
        }})
        crew = payload["crew"]
        crew["tasks"][0]["agent"] = crew["agents"][0]["id"]
        status, payload = request(f"/api/crews/{crew['id']}", "PUT", {"crew": crew})
        crew = payload["crew"]
        check("project created", status == 200, str(payload)[:150])
        check("new project defaults to workspace folder", payload.get("validation", {}).get("ok") is True, str(payload.get("validation"))[:200])

        status, payload = request(f"/api/crews/{crew['id']}")
        info = payload.get("workspace", {})
        check("GET crew exposes workspace info", status == 200 and info.get("is_default") is True, str(info)[:160])
        check("default workspace path is per project", crew["id"] in (info.get("path") or ""), info.get("path"))

        # ------------------------------------------------------- set workspace
        status, payload = request(f"/api/crews/{crew['id']}/workspace", "POST", {"path": str(workspace_dir)})
        crew = payload["crew"]
        check("workspace set", status == 200 and payload["workspace"]["path"] == str(workspace_dir), str(payload)[:200])
        check("workspace folder created on disk", workspace_dir.is_dir())
        check("workspace is not default anymore", payload["workspace"]["is_default"] is False)
        check("crew stores raw workspace", payload["crew"]["workspace"] == str(workspace_dir))

        status, payload = request(f"/api/crews/{crew['id']}")
        check("workspace persists after reload", payload["workspace"]["path"] == str(workspace_dir))

        status, payload = request(f"/api/crews/{crew['id']}/workspace", "POST", {"path": str(ROOT / "run.py")})
        check("file as workspace rejected", status == 400, str(payload)[:120])

        # ---------------------------------------------------- files + preview
        (workspace_dir / "inputs").mkdir(exist_ok=True)
        (workspace_dir / "brief.txt").write_text("Исходные данные", encoding="utf-8")
        (workspace_dir / "inputs" / "data.md").write_text("# Данные", encoding="utf-8")

        status, payload = request(f"/api/files?crew_id={crew['id']}")
        names = {item["path"] for item in payload.get("workspace", {}).get("files", [])}
        check("files listing shows workspace files", status == 200 and {"brief.txt", "inputs/data.md"} <= names, str(names))
        check("files listing reports workspace path", payload.get("workspace", {}).get("path") == str(workspace_dir))

        status, payload = request(f"/api/files/output/brief.txt?crew_id={crew['id']}")
        check("preview reads workspace file", status == 200 and "Исходные" in payload.get("content", ""), str(payload)[:120])

        encoded = base64.b64encode("Загруженная заметка".encode("utf-8")).decode()
        status, payload = request("/api/files", "POST", {"name": "uploaded.txt", "data": encoded, "crew_id": crew["id"]})
        check("upload lands in workspace", status == 200 and payload.get("in_workspace") is True
              and (workspace_dir / "uploaded.txt").is_file(), str(payload)[:160])
        status, payload = request(f"/api/files?crew_id={crew['id']}")
        names = {item["path"] for item in payload.get("workspace", {}).get("files", [])}
        check("uploaded file listed in workspace", "uploaded.txt" in names, str(names))

        # ------------------------------------------------------- run with tools
        request("/api/settings", "PUT", {"settings": {
            "openai_api_key": "sk-test", "openai_base_url": mock.base_url,
            "default_llm": "openai/gpt-4o-mini", "live_stream": True,
        }})
        crew["agents"][0]["tools"] = ["write_local_file", "read_local_file"]
        request(f"/api/crews/{crew['id']}", "PUT", {"crew": crew})

        status, payload = request("/api/runs", "POST", {"crew_id": crew["id"]})
        run_id = payload.get("run_id")
        check("run started", status == 201 and bool(run_id), str(payload)[:200])

        deadline = time.time() + 180
        run = {}
        while time.time() < deadline:
            time.sleep(0.5)
            status, payload = request(f"/api/runs/{run_id}")
            run = payload.get("run", {})
            if run.get("status") not in {"queued", "running"}:
                break
        check("run completed", run.get("status") == "completed", f"{run.get('status')} {run.get('error')}"[:200])
        check("run snapshot knows the workspace", run.get("workspace") == str(workspace_dir), str(run.get("workspace")))
        output_file = workspace_dir / "result.md"
        check("task output file written into workspace", output_file.is_file(), str(list(workspace_dir.iterdir())))

        # ------------------------------------------------------------- reset
        status, payload = request(f"/api/crews/{crew['id']}/workspace", "POST", {"path": ""})
        check("workspace reset to default", status == 200 and payload["workspace"]["is_default"] is True, str(payload)[:150])

        request(f"/api/crews/{crew['id']}", "DELETE")
    finally:
        server.shutdown()
        server.server_close()
        mock.stop()
        time.sleep(0.2)

    print("\nWORKSPACE RESULT:", "PASS" if not failures else f"FAIL ({len(failures)}): {failures}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
