"""Tests for stopping a run: cooperative cancel, force-detach, orphaned runs, limits."""
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
sys.path.insert(0, str(ROOT / "tests"))

DATA = ROOT / ".setup" / f"cancel-{uuid.uuid4().hex[:8]}"
for sub in ("crews", "runs", "outputs", "uploads"):
    (DATA / sub).mkdir(parents=True, exist_ok=True)
os.environ["CREWAI_STUDIO_DATA"] = str(DATA)
os.environ["MOCK_DELAY"] = "0.25"

from mock_llm import MockLLMServer  # noqa: E402

from app.runner import RunManager, RunState  # noqa: E402
from app.spec import normalize_crew, validate_crew  # noqa: E402
from app.store import Store  # noqa: E402

MOCK_PORT = 8915
failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print(("PASS  " if condition else "FAIL  ") + name + (f" — {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(name)


def wait_status(state: RunState, statuses: set[str], timeout: float = 60.0) -> str:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if state.status in statuses:
            return state.status
        time.sleep(0.1)
    return state.status


def main() -> int:
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
    manager = RunManager(store)

    crew = normalize_crew(
        {
            "name": "Отмена",
            "default_llm": "openai/gpt-4o-mini",
            "agents": [{"role": "Аналитик", "goal": "Проверить", "backstory": "Опыт", "max_iter": 4}],
            "tasks": [{"name": "Задача", "description": "Сделай отчёт", "expected_output": "Отчёт"}],
        }
    )
    crew["tasks"][0]["agent"] = crew["agents"][0]["id"]
    crew = store.save_crew(crew)
    check("spec validates", validate_crew(crew, {"current_datetime"})["ok"])

    # ------------------------------------------------ cooperative stop while streaming
    state = manager.start(crew, {}, store.get_settings())
    time.sleep(1.6)
    started = time.time()
    manager.cancel(state.id)
    check("cancel moves the run to cancelling", state.status in {"cancelling", "cancelled"}, state.status)
    final = wait_status(state, {"cancelled", "completed", "failed"}, timeout=20)
    check("run stops after cancel", final == "cancelled", final)
    check("cancel is fast", time.time() - started < 15, f"{time.time() - started:.1f}s")
    deadline = time.time() + 10
    while manager.is_busy() and time.time() < deadline:
        time.sleep(0.1)
    check("cancelled run frees the manager", not manager.is_busy())

    # --------------------------------------------------------- force-detach watchdog
    zombie = RunState("run-zombie", {"id": "crew-x", "name": "Zombie"}, {}, "openai/gpt-4o-mini")
    zombie.status = "running"
    with manager._lock:
        manager._states["run-zombie"] = zombie
        manager._active = "run-zombie"
    manager._cancel_watchdog(zombie, grace=0.6)
    check("watchdog marks a stuck run as forced", zombie.status == "force_stopping", zombie.status)
    check("watchdog keeps the run slot", manager.is_busy())
    check("watchdog does not fake a terminal event", not any(e["type"] == "stream_end" for e in zombie.events))
    check("detach frees the stuck slot", manager.detach("run-zombie") and not manager.is_busy())
    check("detached run is cancelled", zombie.status == "cancelled", zombie.status)
    check("detach emits stream_end once", sum(1 for e in zombie.events if e["type"] == "stream_end") == 1)

    # ------------------------------------------------------------- limits in the spec
    spec = normalize_crew(
        {
            "name": "Лимиты",
            "agents": [
                {"role": "A", "goal": "g", "backstory": "b", "max_execution_time": 90, "max_iter": 30, "reasoning": True}
            ],
            "tasks": [{"description": "d", "expected_output": "e"}],
        }
    )
    agent = spec["agents"][0]
    check("time limit stored", agent["max_execution_time"] == 90)
    warnings = validate_crew(spec, set())["warnings"]
    messages = " ".join(w["message"] for w in warnings)
    check("high max_iter is warned about", "12 итераций" in messages, messages)
    check("reasoning is warned about", "Рассуждения" in messages, messages)

    # ------------------------------------------------------- memory without embeddings
    from app.runner import memory_available

    allowed, note = memory_available({"memory": True}, {})
    check("memory without embeddings is disabled with a warning", allowed is False and "Память отключена" in note, note)
    allowed, note = memory_available({"memory": True}, {"OPENAI_API_KEY": "sk-x"})
    check("memory works when an embeddings key exists", allowed is True and not note, note)
    allowed, note = memory_available({"memory": False}, {})
    check("memory off stays off", allowed is False and not note)

    # --------------------------------------------- orphaned runs are failed on startup
    orphan = {
        "id": "run-orphan",
        "crew_id": crew["id"],
        "crew_name": "Отмена",
        "status": "running",
        "started_at": "2020-01-01T00:00:00",
        "events": [],
        "crew": crew,
    }
    (DATA / "runs" / "run-orphan.json").write_text(json.dumps(orphan), encoding="utf-8")
    store.mark_orphaned_runs()
    saved = json.loads((DATA / "runs" / "run-orphan.json").read_text(encoding="utf-8"))
    check("orphaned run becomes failed", saved["status"] == "failed", saved["status"])
    check("orphaned run explains why", "перезапуск" in saved["error"].lower(), saved["error"])

    # ------------------------------------- streaming off: still completes, no chunk spam
    settings_off = dict(store.get_settings())
    settings_off["live_stream"] = False
    state_quiet = manager.start(crew, {}, settings_off)
    final = wait_status(state_quiet, {"completed", "failed", "cancelled"}, timeout=120)
    check("run works with streaming disabled", final == "completed", final)
    check("no chunk events when streaming is off",
          not any(e["type"] == "llm_chunk" for e in state_quiet.events))
    check("result is still produced", bool((state_quiet.result or {}).get("raw")))

    mock.stop()
    print("\nCANCEL RESULT:", "PASS" if not failures else f"FAIL ({len(failures)}): {failures}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
