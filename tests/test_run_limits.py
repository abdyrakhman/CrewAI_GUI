"""Run limits: wall-clock timeout and the max_iter cap."""
from __future__ import annotations

import os
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

DATA = ROOT / ".setup" / f"limits-{uuid.uuid4().hex[:6]}"
(DATA / "crews").mkdir(parents=True, exist_ok=True)
os.environ["CREWAI_STUDIO_DATA"] = str(DATA)
os.environ["MOCK_DELAY"] = "0.05"
os.environ["CREWAI_STUDIO_RUN_TIMEOUT_SECONDS"] = "1.0"

from mock_llm import MockLLMServer  # noqa: E402

from app.runner import RunManager, _effective_execution_time, _effective_max_iter  # noqa: E402
from app.spec import normalize_crew, validate_crew  # noqa: E402
from app.store import Store  # noqa: E402

MOCK_PORT = 8919
failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print(("PASS  " if condition else "FAIL  ") + name + (f" — {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(name)


def main() -> int:
    mock = MockLLMServer(MOCK_PORT).start()
    store = Store()
    store.save_settings({
        "openai_api_key": "test-key",
        "openai_base_url": f"http://127.0.0.1:{MOCK_PORT}/v1",
        "default_llm": "openai/gpt-4o-mini",
        "max_iter_cap": 5,
        "run_timeout_minutes": 60,
    })

    # settings normalization
    store.save_settings({"run_timeout_minutes": -10, "max_iter_cap": 0})
    settings = store.get_settings()
    check("negative timeout becomes zero", settings["run_timeout_minutes"] == 0, str(settings["run_timeout_minutes"]))
    check("iteration cap is at least one", settings["max_iter_cap"] == 1, str(settings["max_iter_cap"]))
    store.save_settings({"run_timeout_minutes": 99999, "max_iter_cap": 500})
    settings = store.get_settings()
    check("timeout is capped at a day", settings["run_timeout_minutes"] == 1440, str(settings["run_timeout_minutes"]))
    check("iteration cap is capped at 100", settings["max_iter_cap"] == 100, str(settings["max_iter_cap"]))
    store.save_settings({"run_timeout_minutes": 60, "max_iter_cap": 5})

    # helper
    check("cap lowers a big request", _effective_max_iter(40, 20) == 20)
    check("cap keeps a small request", _effective_max_iter(5, 20) == 5)
    check("zero cap disables the limit", _effective_max_iter(40, 0) == 40)
    check("bad values fall back safely", _effective_max_iter("x", "y") == 12, str(_effective_max_iter("x", "y")))

    # validation warning stays for large max_iter
    crew = normalize_crew({
        "name": "Лимиты",
        "default_llm": "openai/gpt-4o-mini",
        "agents": [{"role": "Долгий", "goal": "Работать", "backstory": "Опыт", "max_iter": 40}],
        "tasks": [{"description": "Шаг 1", "expected_output": "1"}, {"description": "Шаг 2", "expected_output": "2"}],
    })
    for task in crew["tasks"]:
        task["agent"] = crew["agents"][0]["id"]
    warnings = validate_crew(crew, {"read_local_file"})["warnings"]
    check("large max_iter is flagged", any("12 итераций" in item["message"] for item in warnings), str(warnings)[:160])

    # confirmation + a short task limit is a trap: the task may expire while the prompt is open
    risky = normalize_crew({
        "name": "Подтверждение",
        "agents": [{"role": "Писатель", "goal": "Писать", "backstory": "Опыт",
                     "confirm_changes": True, "max_execution_time": 300}],
        "tasks": [{"description": "Шаг", "expected_output": "1"}],
    })
    risky["tasks"][0]["agent"] = risky["agents"][0]["id"]
    risky_warnings = validate_crew(risky, {"read_local_file"})["warnings"]
    check("short task limit with confirmation is flagged",
          any("пока вы отвечаете" in item["message"] for item in risky_warnings), str(risky_warnings)[:200])

    # confirmation raises a too-short task limit instead of letting it expire
    check("confirmation raises a short task limit", _effective_execution_time(300, True) == (900, True))
    check("generous task limit stays as is", _effective_execution_time(1200, True) == (1200, False))
    check("no limit is left untouched", _effective_execution_time(0, True) == (0, False))
    check("limit without confirmation is untouched", _effective_execution_time(300, False) == (300, False))

    # a slow run hits the wall-clock limit (env override = 1 s)
    manager = RunManager(store)
    state = manager.start(crew, {}, store.get_settings())
    deadline = time.time() + 30
    while state.status not in {"completed", "failed", "cancelled", "force_stopping"} and time.time() < deadline:
        time.sleep(0.1)

    messages = [str(event["data"].get("message") or "") for event in state.events]
    check("run is stopped by the timeout", state.status == "cancelled", f"{state.status}: {state.error}")
    check("timeout warning is shown", any("Превышен лимит времени" in message for message in messages),
          str([m for m in messages if m][:4]))
    check("iteration cap warning is shown", any("Лимит итераций агента ограничен" in message for message in messages),
          str([m for m in messages if m][:6]))

    mock.stop()
    print("\nRUN LIMITS RESULT:", "PASS" if not failures else f"FAIL ({len(failures)}): {failures}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
