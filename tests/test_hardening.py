"""Acceptance tests for the architect's P0 findings: perimeter, traversal, sandbox, env."""
from __future__ import annotations

import http.client
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

DATA = ROOT / ".setup" / f"sec-{uuid.uuid4().hex[:8]}"
for sub in ("crews", "runs", "outputs", "uploads"):
    (DATA / sub).mkdir(parents=True, exist_ok=True)
os.environ["CREWAI_STUDIO_DATA"] = str(DATA)
os.environ["CREWAI_STUDIO_NO_AUTH"] = "1"

from app.runner import RunState  # noqa: E402
from app.server import create_server  # noqa: E402
from app.spec import normalize_crew, to_python, validate_crew  # noqa: E402
from app.store import Store  # noqa: E402

PORT = 7890
BASE = f"http://127.0.0.1:{PORT}"
failures: list[str] = []
TOKEN = ""


def check(name: str, condition: bool, detail: str = "") -> None:
    print(("PASS  " if condition else "FAIL  ") + name + (f" — {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(name)


def raw_request(path: str, *, method: str = "GET", body: dict | None = None,
                token: bool = True, host: str | None = None, content_type: str = "application/json",
                origin: str | None = None) -> tuple[int, dict, dict]:
    """Low-level request so Host/Origin/Content-Type can be abused deliberately."""
    data = json.dumps(body).encode() if body is not None else None
    headers = {}
    if data is not None:
        headers["Content-Type"] = content_type
    if token:
        headers["X-Studio-Token"] = TOKEN
    if host:
        headers["Host"] = host
    if origin:
        headers["Origin"] = origin
    conn = http.client.HTTPConnection("127.0.0.1", PORT, timeout=20)
    conn.putrequest(method, path, skip_host=bool(host), skip_accept_encoding=True)
    for key, value in headers.items():
        conn.putheader(key, value)
    if data is not None:
        conn.putheader("Content-Length", str(len(data)))
    conn.endheaders(data)
    response = conn.getresponse()
    payload = response.read()
    try:
        parsed = json.loads(payload) if payload else {}
    except json.JSONDecodeError:
        parsed = {"raw": payload[:120].decode("utf-8", "replace")}
    dict_headers = {k.lower(): v for k, v in response.getheaders()}
    conn.close()
    return response.status, parsed, dict_headers


def main() -> int:
    global TOKEN
    # A damaged project must be quarantined at startup and reported as 409 later.
    (DATA / "crews" / "crew-corrupt.json").write_text("{not json", encoding="utf-8")
    server = create_server("127.0.0.1", PORT)
    TOKEN = server.RequestHandlerClass.session_token
    threading.Thread(target=server.serve_forever, daemon=True).start()
    time.sleep(0.5)
    store = Store()

    try:
        # ------------------------------------------------- 1. static traversal
        checks = [
            "/../data/settings.json",
            "/..%2fdata%2fsettings.json",
            "/%2e%2e/data/settings.json",
            "/..%5cdata%5csettings.json",
            "/....//data/settings.json",
            "/static/../../data/settings.json",
            "/static/..%2f..%2fdata%2fsettings.json",
            "/%00../data/settings.json",
            "/C:/Windows/win.ini",
        ]
        for path in checks:
            status, payload, _ = raw_request(path)
            check(f"traversal blocked: {path}", status in {403, 404}, f"{status} {str(payload)[:80]}")

        status, body, headers = raw_request("/static/app.js")
        check("normal static file is served",
              status == 200 and "javascript" in headers.get("content-type", ""), f"{status} {headers.get('content-type')}")
        status, body, headers = raw_request("/")
        check("index is served with the session token injected", status == 200 and "__STUDIO_TOKEN__" not in str(body))
        check("security headers present",
              headers.get("x-content-type-options") == "nosniff"
              and "content-security-policy" in headers
              and "referrer-policy" in headers, str(list(headers))[:120])

        # ------------------------------------------------------ 2. perimeter
        status, payload, headers = raw_request("/api/crews", host="evil.example:7860")
        check("foreign Host is rejected", status == 403, str(status))
        status, payload, _ = raw_request("/api/crews", host=f"localhost:{PORT}")
        check("localhost Host is accepted", status == 200, str(status))

        status, payload, _ = raw_request("/api/settings", method="PUT", body={"settings": {"theme": "dark"}}, token=False)
        check("mutation without token is rejected", status == 403, str(payload)[:100])
        status, payload, _ = raw_request("/api/settings", method="PUT", body={"settings": {"theme": "dark"}},
                                         content_type="text/plain")
        check("text/plain mutation is rejected (CSRF)", status == 415, str(payload)[:100])
        status, payload, _ = raw_request("/api/settings", method="PUT", body={"settings": {"theme": "dark"}},
                                         origin="http://evil.example")
        check("foreign Origin is rejected", status == 403, str(payload)[:100])
        status, payload, _ = raw_request("/api/settings", method="PUT", body={"settings": {"theme": "light"}})
        check("legit mutation is accepted", status == 200, str(payload)[:100])

        status, payload, headers = raw_request("/api/info")
        check("no CORS headers are sent", "access-control-allow-origin" not in headers, str(headers.keys()))
        status, payload, headers = raw_request("/api/crews", method="OPTIONS", token=False)
        check("OPTIONS advertises no CORS", "access-control-allow-origin" not in headers, str(status))

        # ------------------------------------------------- 3. sandbox: output_file
        spec = normalize_crew(
            {
                "name": "Песочница",
                "workspace": str(DATA / "ws"),
                "agents": [{"role": "A", "goal": "g", "backstory": "b"}],
                "tasks": [{
                    "name": "t", "description": "d", "expected_output": "e",
                    "output_format": "file", "output_file": "C:\\Windows\\Temp\\evil.bat",
                }],
            }
        )
        spec["tasks"][0]["agent"] = spec["agents"][0]["id"]
        validation = validate_crew(spec, set())
        messages = " ".join(item["message"] for item in validation["errors"])
        check("absolute output_file is a validation error", not validation["ok"] and "только имя файла" in messages,
              messages[:160])

        saved_spec = normalize_crew({
            "name": "Сохранённый",
            "agents": [{"role": "A", "goal": "g", "backstory": "b"}],
            "tasks": [{"description": "d", "expected_output": "e"}],
        })
        saved_spec["tasks"][0]["agent"] = saved_spec["agents"][0]["id"]
        crew = store.save_crew(saved_spec)
        status, payload, _ = raw_request("/api/runs", method="POST", body={"crew": {"name": "inline"}})
        check("inline crew spec is rejected", status == 422, str(payload)[:120])
        status, payload, _ = raw_request("/api/runs", method="POST", body={"crew_id": crew["id"]})
        check("saved project can still be run", status in {201, 409}, str(payload)[:120])

        # ----------------------------------------- 10. environment allow-list
        status, payload, _ = raw_request("/api/settings", method="PUT", body={"settings": {
            "extra_env": {"PATH": "C:\\evil", "LD_PRELOAD": "x.so", "PIP_INDEX_URL": "https://evil",
                          "STUDIO_CUSTOM": "ok"},
        }})
        blocked = set(payload.get("blocked_env") or [])
        check("dangerous env keys are refused", {"PATH", "LD_PRELOAD", "PIP_INDEX_URL"} <= blocked, str(blocked))
        saved = store.get_settings().get("extra_env", {})
        check("dangerous env keys are not stored", not ({"PATH", "LD_PRELOAD", "PIP_INDEX_URL"} & set(saved)), str(saved))
        check("allow-listed env key survives", saved.get("STUDIO_CUSTOM") == "ok", str(saved))

        from app import tools

        check("pip target is pinned to the installed crewai", "==" in tools.install_target(), tools.install_target())

        # ------------------------------------------------------- 9. code parity
        code = to_python(crew, "")
        check("generated code keeps tools section", "def studio_tool" in code)
        spec2 = normalize_crew({
            "name": "Код",
            "agents": [{"role": "A", "goal": "g", "backstory": "b", "tools": ["current_datetime"],
                        "max_iter": 5, "max_execution_time": 60}],
            "tasks": [{"description": "d", "expected_output": "e"}],
        })
        code2 = to_python(spec2, "")
        check("generated code carries the time limit", "max_execution_time=60" in code2, code2[:200])
        check("generated code carries max_iter", "max_iter=5" in code2)
        check("generated code wires the tool", "studio_tool('current_datetime')" in code2)

        # --------------------------------------------------- run index / perf
        for index in range(30):
            store.save_run({
                "id": f"run-{index}", "crew_id": "c", "crew_name": "n", "status": "completed",
                "started_at": f"2026-01-01T00:00:{index:02d}", "duration": 1,
                "result": {"token_usage": {"total_tokens": index}}, "events": [],
            })
        started = time.time()
        runs = store.list_runs()
        elapsed = time.time() - started
        check("run index lists runs", len(runs) >= 30, str(len(runs)))
        check("list_runs is fast", elapsed < 0.5, f"{elapsed:.3f}s")
        check("index file exists", (DATA / "runs" / "index.jsonl").exists())

        # ---------------------------------------- P0-1: third-party tool boundary
        status, payload, _ = raw_request("/api/tools")
        tool_rows = payload.get("tools") or []
        names = {row["name"] for row in tool_rows}
        removed = {"FileReadTool", "FileWriterTool", "DirectoryReadTool", "PDFSearchTool",
                   "CSVSearchTool", "JSONSearchTool", "TXTSearchTool", "MDXSearchTool"}
        check("file/RAG third-party tools are gone from the catalogue", not (removed & names), str(removed & names))
        builtin_rows = [row for row in tool_rows if row["source"] == "builtin"]
        check("built-in tools are marked sandboxed", all(row.get("policy") == "sandboxed" for row in builtin_rows))
        network_rows = [row for row in tool_rows if row["source"] == "crewai-tools"]
        installed_network = [row for row in network_rows if row.get("installed")]
        check("network tools are disabled by default",
              all(not row["available"] for row in network_rows), str(len(network_rows)))

        from app.tools import build_tool

        refused = False
        try:
            build_tool("FileReadTool", {}, None, False, "", None, True)
        except RuntimeError:
            refused = True
        check("removed tool cannot be constructed even with network allowed", refused)

        status, payload, _ = raw_request("/api/settings", method="PUT", body={"settings": {"allow_network_tools": True}})
        status, payload, _ = raw_request("/api/tools")
        network_rows = [row for row in payload.get("tools") or [] if row["source"] == "crewai-tools"]
        if installed_network:
            check("opt-in enables installed network tools", any(row["available"] for row in network_rows))
        raw_request("/api/settings", method="PUT", body={"settings": {"allow_network_tools": False}})

        rejected_tools: list[dict] = []
        spec_tools = normalize_crew({
            "name": "Инструменты",
            "agents": [{"role": "A", "goal": "g", "backstory": "b", "tools": ["PDFSearchTool"]}],
            "tasks": [{"description": "d", "expected_output": "e"}],
        }, rejected_tools)
        spec_tools["tasks"][0]["agent"] = spec_tools["agents"][0]["id"]
        validation = validate_crew(spec_tools, {"read_local_file"})
        check("removed tool is dropped from a legacy project",
              spec_tools["agents"][0]["tools"] == [] and validation["ok"],
              str(spec_tools["agents"][0]["tools"]) + str(validation["errors"])[:120])
        check("dropping a removed tool is reported",
              any("отключён" in item["message"] for item in rejected_tools),
              str(rejected_tools)[:160])

        # ------------------------------------------- P1-2: workspace is domain policy
        blocked = False
        try:
            store.save_crew(normalize_crew({
                "name": "Плохая папка",
                "workspace": "C:\\Windows\\System32",
                "agents": [{"role": "A", "goal": "g", "backstory": "b"}],
                "tasks": [{"description": "d", "expected_output": "e"}],
            }))
        except ValueError:
            blocked = True
        check("save_crew rejects an OS directory as workspace", blocked)

        status, payload, _ = raw_request("/api/crews", method="POST", body={
            "crew": {
                "name": "Плохая папка 2",
                "workspace": "C:\\Windows\\System32",
                "agents": [{"role": "A", "goal": "g", "backstory": "b"}],
                "tasks": [{"description": "d", "expected_output": "e"}],
            }
        })
        check("API rejects an OS directory as workspace", status in {400, 403}, f"{status} {payload}")

        status, payload, _ = raw_request(f"/api/crews/{crew['id']}", method="PUT", body={"crew": {"name": "Обрезано"}})
        check("partial PUT cannot erase a project", status == 422, f"{status} {payload}")
        status, payload, _ = raw_request(f"/api/crews/{crew['id']}")
        check("project survived the partial PUT", len(payload["crew"]["tasks"]) == 1, str(payload["crew"]["tasks"])[:80])

        status, payload, _ = raw_request("/api/templates", method="POST", body={
            "title": "Шаблон с папкой",
            "crew": {
                "name": "С папкой",
                "workspace": str(DATA / "ws-template"),
                "agents": [{"role": "A", "goal": "g", "backstory": "b"}],
                "tasks": [{"description": "d", "expected_output": "e"}],
            },
        })
        check("template creation succeeds", status in {200, 201}, str(payload)[:120])
        template_key = (payload.get("template") or {}).get("key", "")
        status, payload, _ = raw_request("/api/templates")
        entry = next((item for item in payload.get("templates") or [] if item.get("key") == template_key), {})
        check("template drops the project workspace", (entry.get("crew") or {}).get("workspace") in {"", None},
              str((entry.get("crew") or {}).get("workspace")))

        # ------------------------------------------- P1-3: grant scope is honest
        sse_state = RunState("run-scope", {"id": "c", "name": "C"}, {}, "m")
        captured: dict = {}

        def ask_worker() -> None:
            captured["result"] = sse_state.ask_permission(
                "fs_write", str(DATA / "outside" / "a.txt"), "тест", "Агент", timeout=3, grant="file"
            )

        worker = threading.Thread(target=ask_worker, daemon=True)
        worker.start()
        deadline = time.time() + 3
        request_event = None
        while time.time() < deadline:
            request_event = next((e for e in sse_state.events if e["type"] == "permission_request"), None)
            if request_event:
                break
            time.sleep(0.05)
        check("permission request reports per-file grant",
              bool(request_event) and request_event["data"].get("grant") == "file",
              str(request_event["data"].get("grant") if request_event else None))
        sse_state.answer_permission(request_event["data"]["id"], True, "run")
        worker.join(3)
        second = sse_state.ask_permission("fs_write", str(DATA / "outside" / "b.txt"), "тест", "Агент",
                                          timeout=0.4, grant="file")
        check("file grant does not cover the whole folder", second[0] is False, str(second))

        # ------------------------------------------- P1-6: index stays bounded
        for _ in range(600):
            store.save_run({
                "id": "run-hot", "crew_id": "c", "crew_name": "n", "status": "running",
                "started_at": "2026-01-01T00:00:00", "duration": 1, "events": [],
            })
        index_lines = len((DATA / "runs" / "index.jsonl").read_text(encoding="utf-8").splitlines())
        check("run index is compacted instead of growing forever", index_lines < 300, str(index_lines))

        # ------------------------------------------- P2-11: chunked bodies refused
        conn = http.client.HTTPConnection("127.0.0.1", PORT, timeout=10)
        conn.putrequest("POST", "/api/settings", skip_host=True)
        conn.putheader("Host", f"127.0.0.1:{PORT}")
        conn.putheader("Transfer-Encoding", "chunked")
        conn.putheader("X-Studio-Token", TOKEN)
        conn.putheader("Content-Type", "application/json")
        conn.endheaders()
        response = conn.getresponse()
        check("chunked request is rejected", response.status == 411, str(response.status))
        conn.close()

        # ------------------------------------------- P2-13: corrupt project is visible
        status, payload, _ = raw_request("/api/crews/crew-corrupt")
        check("corrupt project returns 409, not 404", status == 409, f"{status} {payload}")

        # ------------------------------------------- P2-14: SSE ids and resume
        stream_state = RunState("run-sse", {"id": "c", "name": "C"}, {}, "m")
        stream_state.emit("info", {"message": "первое"})
        stream_state.emit("info", {"message": "второе"})
        stream_state.status = "completed"
        server.RequestHandlerClass.manager._states["run-sse"] = stream_state
        conn = http.client.HTTPConnection("127.0.0.1", PORT, timeout=10)
        conn.putrequest("GET", "/api/runs/run-sse/events", skip_host=True)
        conn.putheader("Host", f"127.0.0.1:{PORT}")
        conn.putheader("Last-Event-ID", "1")
        conn.endheaders()
        response = conn.getresponse()
        chunk = response.read(4000).decode("utf-8", "replace")
        check("SSE carries event ids", "id: 2" in chunk, chunk[:160])
        check("SSE resumes after Last-Event-ID", '"message": "первое"' not in chunk, chunk[:200])
        conn.close()

        # single instance guard
        from app import config, instance

        lock_path = config.DATA_DIR / ".test-instance.lock"
        first = instance.acquire(lock_path)
        check("instance lock is acquired", first is not None)
        second = instance.acquire(lock_path)
        check("second instance is refused", second is None)
        instance.release(first)
        third = instance.acquire(lock_path)
        check("lock can be reacquired after release", third is not None)
        instance.release(third)

        # one uploaded file may not exceed the ceiling
        import base64

        from app import security

        original_limit = security.MAX_UPLOAD
        security.MAX_UPLOAD = 64
        try:
            status, payload, _ = raw_request(
                "/api/files", method="POST",
                body={"name": "big.txt", "data": base64.b64encode(b"x" * 500).decode()},
            )
            check("oversized upload is rejected", status == 413, f"{status} {str(payload)[:100]}")
            status, payload, _ = raw_request(
                "/api/files", method="POST",
                body={"name": "small.txt", "data": base64.b64encode(b"ok").decode()},
            )
            check("small upload is accepted", status in {200, 201}, f"{status} {str(payload)[:100]}")
        finally:
            security.MAX_UPLOAD = original_limit
    finally:
        server.shutdown()
        server.server_close()
        time.sleep(0.2)

    print("\nHARDENING RESULT:", "PASS" if not failures else f"FAIL ({len(failures)}): {failures}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
