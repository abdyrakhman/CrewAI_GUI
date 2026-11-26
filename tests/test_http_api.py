"""HTTP-level test: REST API, static UI, server-sent events, run lifecycle."""
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

STUDIO_DATA = ROOT / ".setup" / f"http-{uuid.uuid4().hex[:8]}"
STUDIO_DATA.mkdir(parents=True, exist_ok=True)
os.environ["CREWAI_STUDIO_DATA"] = str(STUDIO_DATA)
os.environ["CREWAI_STUDIO_NO_AUTH"] = "1"

from mock_llm import MockLLMServer  # noqa: E402

from app.server import create_server  # noqa: E402

MOCK_PORT = 8902
APP_PORT = 7871
BASE = f"http://127.0.0.1:{APP_PORT}"

failures: list[str] = []
TOKEN = ""


def check(name: str, condition: bool, detail: str = "") -> None:
    print(("PASS  " if condition else "FAIL  ") + name + (f" — {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(name)


def request(path: str, method: str = "GET", body: dict | None = None) -> tuple[int, dict | bytes]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    if method != "GET":
        req.add_header("X-Studio-Token", TOKEN)
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            raw = response.read()
            content_type = response.headers.get("Content-Type", "")
            if "application/json" in content_type:
                return response.status, json.loads(raw)
            return response.status, raw
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, raw


def main() -> int:
    global TOKEN
    mock = MockLLMServer(MOCK_PORT).start()
    server = create_server("127.0.0.1", APP_PORT)
    TOKEN = server.RequestHandlerClass.session_token
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.6)

    try:
        status, info = request("/api/info")
        check("GET /api/info", status == 200 and info["crewai"]["installed"], str(info)[:200])

        status, html = request("/")
        check("GET / serves UI", status == 200 and b"CrewAI Studio" in html, str(status))
        status, js = request("/static/app.js")
        check("GET /static/app.js", status == 200 and b"attachRun" in js, str(status))
        status, css = request("/static/styles.css")
        check("GET /static/styles.css", status == 200 and b"--accent" in css, str(status))

        status, payload = request(
            "/api/settings",
            "PUT",
            {
                "settings": {
                    "openai_api_key": "sk-test",
                    "openai_base_url": mock.base_url,
                    "default_llm": "openai/gpt-4o-mini",
                    "live_stream": True,
                }
            },
        )
        check("PUT /api/settings", status == 200 and payload["settings"]["default_llm"] == "openai/gpt-4o-mini")

        status, payload = request("/api/llm/test", "POST", {"model": "openai/gpt-4o-mini"})
        check("POST /api/llm/test", status == 200 and payload.get("ok"), str(payload)[:200])

        status, payload = request("/api/crews", "POST", {"template": "research-brief"})
        crew_id = payload.get("crew", {}).get("id") if isinstance(payload, dict) else None
        check("POST /api/crews from template", status == 201 and bool(crew_id), str(payload)[:200])

        status, payload = request(f"/api/crews/{crew_id}")
        crew = payload.get("crew", {})
        check("GET /api/crews/{id}", status == 200 and len(crew.get("agents", [])) == 3, str(payload)[:200])

        status, payload = request(f"/api/crews/{crew_id}/validate", "POST", {"crew": crew})
        check("POST validate", status == 200 and payload.get("ok"), str(payload)[:300])

        status, payload = request(f"/api/crews/{crew_id}/code")
        check("GET code preview", status == 200 and "Agent(" in payload.get("code", ""), str(payload)[:200])

        status, payload = request("/api/runs", "POST", {"crew_id": crew_id})
        run_id = payload.get("run_id")
        check("POST /api/runs", status == 201 and bool(run_id), str(payload)[:300])

        events: list[str] = []
        chunks = 0
        with urllib.request.urlopen(f"{BASE}/api/runs/{run_id}/events", timeout=180) as stream:
            deadline = time.time() + 180
            for raw in stream:
                line = raw.decode("utf-8", "replace").strip()
                if line.startswith("event:"):
                    name = line.split(":", 1)[1].strip()
                    events.append(name)
                    if name == "stream_end":
                        break
                if time.time() > deadline:
                    break
        check("SSE stream ends with stream_end", events[-1:] == ["stream_end"], str(events[-5:]))
        check("SSE has task events", events.count("task_start") >= 3 and events.count("task_done") >= 3, str(events))
        check("SSE carries agent steps, not raw tokens",
              "agent_start" in events and "llm_chunk" not in events, str(events[-8:]))

        time.sleep(0.4)
        status, payload = request(f"/api/runs/{run_id}")
        run = payload.get("run", {})
        check("GET run snapshot completed", run.get("status") == "completed", json.dumps(run)[:300])
        check("run has result", bool((run.get("result") or {}).get("raw")))
        check("run has per-task output", len((run.get("result") or {}).get("tasks", [])) == 3)

        status, body = request(f"/api/runs/{run_id}/export?format=md")
        check("export markdown", status == 200 and b"# " in body, str(status))

        status, payload = request("/api/runs")
        check("GET /api/runs history", status == 200 and any(r["id"] == run_id for r in payload["runs"]))

        status, payload = request("/api/tools")
        names = {tool["name"] for tool in payload["tools"]}
        check("GET /api/tools", {"read_local_file", "fetch_url", "SerperDevTool"} <= names, str(sorted(names))[:200])

        status, payload = request("/api/files")
        check("GET /api/files", status == 200 and "uploads" in payload)

        status, payload = request("/api/crews", "POST", {"crew": {"name": "Пустой", "agents": [], "tasks": []}})
        empty_id = payload["crew"]["id"]
        status, payload = request("/api/runs", "POST", {"crew_id": empty_id})
        check("invalid crew is rejected with 422", status == 422 and "validation" in payload, str(payload)[:200])

        status, payload = request("/api/status")
        check("GET /api/status", status == 200 and payload.get("busy") is False)

        status, payload = request(f"/api/runs/{run_id}", "DELETE")
        check("DELETE run", status == 200 and payload.get("ok"))
    finally:
        server.shutdown()
        server.server_close()
        mock.stop()
        time.sleep(0.2)

    print("\nHTTP RESULT:", "PASS" if not failures else f"FAIL ({len(failures)}): {failures}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
