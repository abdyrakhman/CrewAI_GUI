"""End-to-end test: real CrewAI execution through the Studio run manager.

Uses a local OpenAI-compatible mock instead of a paid API, so it verifies the
whole chain: spec -> crewai objects -> event bus -> persisted run snapshot.
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

STUDIO_DATA = ROOT / ".setup" / f"e2e-{uuid.uuid4().hex[:8]}"
STUDIO_DATA.mkdir(parents=True, exist_ok=True)
os.environ["CREWAI_STUDIO_DATA"] = str(STUDIO_DATA)

from mock_llm import MockLLMServer  # noqa: E402

from app.runner import RunManager  # noqa: E402
from app.spec import normalize_crew, validate_crew  # noqa: E402
from app.store import Store  # noqa: E402

MOCK_PORT = 8901


def build_crew() -> dict:
    return normalize_crew(
        {
            "name": "РўРµСЃС‚РѕРІР°СЏ РєРѕРјР°РЅРґР°",
            "description": "Р”РІР° Р°РіРµРЅС‚Р°, РґРІРµ Р·Р°РґР°С‡Рё",
            "process": "sequential",
            "default_llm": "openai/gpt-4o-mini",
            "live_stream": True,
            "agents": [
                {
                    "role": "РСЃСЃР»РµРґРѕРІР°С‚РµР»СЊ",
                    "goal": "РЎРѕР±СЂР°С‚СЊ С„Р°РєС‚С‹ РїРѕ С‚РµРјРµ {topic}",
                    "backstory": "РћРїС‹С‚РЅС‹Р№ Р°РЅР°Р»РёС‚РёРє, РїСЂРѕРІРµСЂСЏРµС‚ РёСЃС‚РѕС‡РЅРёРєРё.",
                    "tools": ["current_datetime"],
                    "max_iter": 5,
                },
                {
                    "role": "Р РµРґР°РєС‚РѕСЂ",
                    "goal": "РЎРѕР±СЂР°С‚СЊ РёС‚РѕРіРѕРІС‹Р№ РѕС‚С‡С‘С‚",
                    "backstory": "РџРёС€РµС‚ РєСЂР°С‚РєРѕ Рё РїРѕ РґРµР»Сѓ.",
                    "max_iter": 5,
                },
            ],
            "tasks": [
                {
                    "name": "РЎР±РѕСЂ С„Р°РєС‚РѕРІ",
                    "description": "РЎРѕР±РµСЂРё С„Р°РєС‚С‹ РїРѕ С‚РµРјРµ {topic}",
                    "expected_output": "РЎРїРёСЃРѕРє С„Р°РєС‚РѕРІ",
                    "output_format": "markdown",
                },
                {
                    "name": "РС‚РѕРіРѕРІС‹Р№ РѕС‚С‡С‘С‚",
                    "description": "РЎРґРµР»Р°Р№ РёС‚РѕРіРѕРІС‹Р№ РѕС‚С‡С‘С‚ РїРѕ СЃРѕР±СЂР°РЅРЅС‹Рј С„Р°РєС‚Р°Рј",
                    "expected_output": "РћС‚С‡С‘С‚ РІ Markdown",
                    "output_format": "markdown",
                },
            ],
            "inputs": [{"key": "topic", "value": "РР РІ Р»РѕРіРёСЃС‚РёРєРµ", "description": "С‚РµРјР°"}],
        }
    )


def main() -> int:
    server = MockLLMServer(MOCK_PORT).start()
    store = Store()
    store.save_settings(
        {
            "openai_api_key": "sk-test",
            "openai_base_url": server.base_url,
            "default_llm": "openai/gpt-4o-mini",
            "live_stream": True,
        }
    )

    crew = build_crew()
    crew["tasks"][0]["agent"] = crew["agents"][0]["id"]
    crew["tasks"][1]["agent"] = crew["agents"][1]["id"]
    crew["tasks"][1]["context"] = [crew["tasks"][0]["id"]]
    crew = store.save_crew(crew)

    validation = validate_crew(crew, {"current_datetime"})
    print("validation:", validation["ok"], validation["errors"], validation["warnings"])
    assert validation["ok"], "spec should validate"

    manager = RunManager(store)
    state = manager.start(crew, {"topic": "РР РІ Р»РѕРіРёСЃС‚РёРєРµ"}, store.get_settings())
    print("run started:", state.id)

    started = time.time()
    while state.status in {"queued", "running"}:
        time.sleep(0.4)
        if time.time() - started > 240:
            print("TIMEOUT вЂ” cancelling")
            manager.cancel(state.id)
            break

    types = [event["type"] for event in state.events]
    print("status:", state.status)
    print("duration:", state.duration, "s")
    print("event types:", sorted(set(types)))
    print("event counts:", {t: types.count(t) for t in sorted(set(types))})
    print("usage:", state.usage)
    if state.error:
        print("ERROR:", state.error)
    for event in state.events:
        if event["type"] == "warning":
            print("WARN:", event["data"])
    print("result head:", (state.result or {}).get("raw", "")[:200])
    print("tasks:", [(t["name"], len(t["output"])) for t in (state.result or {}).get("tasks", [])])

    snapshot_path = STUDIO_DATA / "runs" / f"{state.id}.json"
    print("snapshot exists:", snapshot_path.exists())
    if snapshot_path.exists():
        saved = json.loads(snapshot_path.read_text(encoding="utf-8"))
        print("saved status:", saved["status"], "events:", len(saved["events"]))

    server.stop()

    ok = (
        state.status == "completed"
        and bool((state.result or {}).get("raw"))
        and types.count("task_start") >= 2
        and types.count("task_done") >= 2
        and "llm_chunk" in types
        and snapshot_path.exists()
    )
    print("\nE2E RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
