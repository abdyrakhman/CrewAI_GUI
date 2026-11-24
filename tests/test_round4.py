"""Acceptance tests for the fourth architecture review: R-1…R-8."""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DATA = ROOT / ".setup" / f"r4-{uuid.uuid4().hex[:8]}"
for sub in ("crews", "runs", "outputs", "uploads", "workspaces"):
    (DATA / sub).mkdir(parents=True, exist_ok=True)
os.environ["CREWAI_STUDIO_DATA"] = str(DATA)

from app import runner, tools, workspace  # noqa: E402
from app.runner import RunManager, RunState  # noqa: E402
from app.spec import normalize_crew, to_python, validate_crew  # noqa: E402
from app.statuses import STALE_ON_START, TERMINAL  # noqa: E402
from app.store import Store  # noqa: E402

failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print(("PASS  " if condition else "FAIL  ") + name + (f" — {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(name)


def main() -> int:
    store = Store()

    # ---------------------------------------------------------------- R-1
    startup = Path(os.environ.get("APPDATA", str(DATA))) / "Microsoft/Windows/Start Menu/Programs/Startup"
    startup.mkdir(parents=True, exist_ok=True)
    crew = normalize_crew({
        "name": "Импорт с плохой папкой",
        "workspace": str(startup),
        "agents": [{"role": "A", "goal": "g", "backstory": "b"}],
        "tasks": [{"description": "d", "expected_output": "e"}],
    })
    crew["tasks"][0]["agent"] = crew["agents"][0]["id"]
    crew["id"] = "crew-r1"
    path, note = workspace.for_crew(crew, workspace.allowed_roots([]))
    check("R-1 loaded project with Startup workspace falls back", str(path).startswith(str(DATA)) or "workspaces" in str(path), str(path))
    check("R-1 fallback is explained", bool(note), note)
    check("R-1 no file is written to Startup", not any(startup.glob("*.txt")))

    # a normal workspace still passes
    ok_crew = dict(crew, workspace=str(DATA / "workspaces" / "ok"))
    path_ok, note_ok = workspace.for_crew(ok_crew, workspace.allowed_roots([]))
    check("R-1 allowed workspace is kept", str(path_ok).endswith("ok") and not note_ok, f"{path_ok} {note_ok}")

    # ---------------------------------------------------------------- R-2
    check("R-2 network tools are opt-in per name", tools.allowed_network_names(["SerperDevTool"]) == {"SerperDevTool"})
    state = RunState("run-net", {"id": "c", "name": "C"}, {}, "m")

    class FakeTool:
        _run = lambda self, *a, **k: "network call happened"  # noqa: E731

    fake = FakeTool()
    guarded = tools.guard_network_tool(fake, "ScrapeWebsiteTool", state)

    result = {}
    worker = threading.Thread(target=lambda: result.update({"value": guarded._run("http://127.0.0.1:7860/")}))
    worker.start()
    deadline = time.time() + 3
    request = None
    while time.time() < deadline:
        request = next((e for e in state.events if e["type"] == "permission_request"), None)
        if request:
            break
        time.sleep(0.05)
    check("R-2 localhost URL never reaches the tool", request is None, str(request))
    worker.join(3)
    check("R-2 localhost call is refused", "заблокирован" in str(result.get("value", "")), str(result.get("value")))

    # allowed public URL asks for egress consent, then emits tool_network
    public = tools.guard_network_tool(FakeTool(), "SerperDevTool", state)
    out = {}
    worker = threading.Thread(target=lambda: out.update({"value": public._run("https://example.com/doc")}))
    worker.start()
    deadline = time.time() + 3
    request = None
    while time.time() < deadline:
        request = next((e for e in state.events if e["type"] == "permission_request"), None)
        if request:
            break
        time.sleep(0.05)
    check("R-2 egress asks for consent", bool(request), str(request))
    if request:
        state.answer_permission(request["data"]["id"], True, "once")
    worker.join(3)
    check("R-2 egress emits tool_network", any(e["type"] == "tool_network" for e in state.events))

    # ---------------------------------------------------------------- R-3
    saved = store.save_settings({"openai_api_key": "sk-settings-value"})
    env = store.effective_env()
    check("R-3 settings beat the process env", env.get("OPENAI_API_KEY") == "sk-settings-value", env.get("OPENAI_API_KEY"))
    os.environ["OPENAI_API_KEY"] = "stale-process-value"
    check("R-3 stale process env does not shadow settings",
          store.effective_env().get("OPENAI_API_KEY") == "sk-settings-value")
    os.environ.pop("OPENAI_API_KEY", None)

    # ---------------------------------------------------------------- R-4
    legacy = normalize_crew({        "name": "Легаси",
        "agents": [{"role": "A", "goal": "g", "backstory": "b", "tools": ["FileWriterTool"]}],
        "tasks": [{"description": "d", "expected_output": "e"}],
    })
    legacy["tasks"][0]["agent"] = legacy["agents"][0]["id"]
    validation = validate_crew(legacy, {"read_local_file"})
    check("R-4 legacy removed tool is an error", not validation["ok"], str(validation["errors"])[:120])
    code = to_python(legacy, "", 60)
    check("R-4 code export has no removed tools",
          not any(name in code for name in ("FileWriterTool", "DirectoryReadTool", "PDFSearchTool")))

    # ------------------------------------- pasted text with braces must not crash a run
    from app.spec import inputs_for_run

    braced = normalize_crew({
        "name": "Скобки",
        "inputs": [{"key": "topic", "label": "Тема"}],
        "agents": [{"role": "A", "goal": "g", "backstory": "b"}],
        "tasks": [{"description": "Тема {topic}, плюс {id} и {{literal}}", "expected_output": "итог {topic}"}],
    })
    merged = inputs_for_run(braced, {"topic": "значение"})
    check("declared placeholder is supplied by the user", merged.get("topic") == "значение")
    check("undeclared placeholder maps to itself", merged.get("id") == "{id}", str(merged.get("id")))
    check("braces inside doubled braces are covered", merged.get("literal") == "{literal}")

    # ---------------------------------------------------------------- R-5
    s1 = RunState("run-grant", {"id": "c", "name": "C"}, {}, "m")
    folder_a = DATA / "projects" / "secret"
    folder_b = DATA / "projects" / "other"
    folder_a.mkdir(parents=True, exist_ok=True)
    folder_b.mkdir(parents=True, exist_ok=True)
    result = {}
    worker = threading.Thread(target=lambda: result.update({
        "value": s1.ask_permission("fs_read", str(folder_a), "листинг", "A", timeout=3, grant="folder", base=str(folder_a))
    }))
    worker.start()
    deadline = time.time() + 3
    request = None
    while time.time() < deadline:
        request = next((e for e in s1.events if e["type"] == "permission_request"), None)
        if request:
            break
        time.sleep(0.05)
    check("R-5 folder grant target is the folder itself",
          bool(request) and request["data"]["grant_target"] == str(folder_a),
          str(request["data"].get("grant_target") if request else None))
    s1.answer_permission(request["data"]["id"], True, "run")
    worker.join(3)
    neighbour = s1.ask_permission("fs_read", str(folder_b), "листинг", "A", timeout=0.4, grant="folder", base=str(folder_b))
    check("R-5 grant does not cover the neighbour folder", neighbour[0] is False, str(neighbour))

    # ---------------------------------------------------------------- R-6
    service = Path(os.environ.get("APPDATA", str(DATA))) / "Microsoft/Windows/Start Menu/Programs/Startup/x.txt"
    from app.tools import _ask

    allowed, note = _ask(s1, "fs_write", str(service), "тест", "A")
    check("R-6 service directory is refused without dialog", allowed is False and "Служебный" in note, note)

    link = DATA / "link-to-startup"
    try:
        link.symlink_to(startup, target_is_directory=True)
        resolved_rejected = False
        try:
            workspace.assert_safe_target(link / "evil.txt")
        except ValueError:
            resolved_rejected = True
        check("R-6 symlink to Startup is rejected", resolved_rejected)
    except OSError:
        check("R-6 symlink check skipped (no privilege)", True)

    # ---------------------------------------------------------------- R-7
    detached = RunState("run-detached", {"id": "c", "name": "C"}, {}, "m")
    detached.abandoned = True
    write_tool = tools.build_tool("write_local_file", {}, DATA / "ws", False, "A", detached)
    written = write_tool._run("note.txt", "hello")
    check("R-7 detached run cannot write even inside workspace", "отсоединён" in written.lower(), written)
    check("R-7 file was not created", not (DATA / "ws" / "note.txt").exists())

    fetch_tool = tools.build_tool("fetch_url", {}, DATA / "ws", False, "A", detached)
    fetched = fetch_tool._run("https://example.com")
    check("R-7 detached run cannot fetch", "отсоединён" in fetched.lower(), fetched)

    # ---------------------------------------------------------------- R-8
    check("R-8 force_stopping is terminal", "force_stopping" in TERMINAL)
    check("R-8 force_stopping is stale after restart", "force_stopping" in STALE_ON_START)
    check("R-8 manager uses one terminal set", runner.TERMINAL is TERMINAL)

    manager = RunManager(store)
    zombie = RunState("run-force", {"id": "c", "name": "C"}, {}, "m")
    zombie.status = "force_stopping"
    with manager._lock:
        manager._states["run-force"] = zombie
        for index in range(20):
            filler = RunState(f"run-fill-{index}", {"id": "c", "name": "C"}, {}, "m")
            filler.status = "completed"
            manager._states[filler.id] = filler
    manager._trim_memory()
    check("R-8 forced run is evicted from memory", "run-force" not in manager._states, str(list(manager._states)[:3]))

    print("\nROUND4 RESULT:", "PASS" if not failures else f"FAIL ({len(failures)}): {failures}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
