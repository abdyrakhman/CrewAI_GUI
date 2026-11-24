"""Regression: pasted text with braces must not crash a real CrewAI run."""
from __future__ import annotations

import os
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

STUDIO_DATA = ROOT / ".setup" / f"braces-{uuid.uuid4().hex[:8]}"
(STUDIO_DATA / "crews").mkdir(parents=True, exist_ok=True)
os.environ["CREWAI_STUDIO_DATA"] = str(STUDIO_DATA)

from mock_llm import MockLLMServer  # noqa: E402

from app.runner import RunManager  # noqa: E402
from app.spec import normalize_crew  # noqa: E402
from app.store import Store  # noqa: E402

MOCK_PORT = 8907
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
    })
    crew = normalize_crew({
        "name": "Скобки",
        "default_llm": "openai/gpt-4o-mini",
        "agents": [{"role": "Архитектор", "goal": "Оценить {system}", "backstory": "Опытный архитектор.", "max_iter": 3}],
        "tasks": [{
            "name": "Оценка",
            "description": "Проверь {system}. В тексте есть {id} и {unknown_field}, а также {{literal}}.",
            "expected_output": "Краткий отчёт",
        }],
    })
    crew["tasks"][0]["agent"] = crew["agents"][0]["id"]
    crew["inputs"] = [{"key": "system", "label": "Система", "default": "сервис заказов"}]

    manager = RunManager(store)
    state = manager.start(crew, {"system": "сервис заказов"}, store.get_settings())
    deadline = time.time() + 90
    while state.status not in {"completed", "failed", "cancelled"} and time.time() < deadline:
        time.sleep(0.2)
    check("run with undeclared braces completes", state.status == "completed", f"{state.status}: {state.error}")
    check("declared placeholder was substituted", "сервис заказов" in str(state.result or ""), str(state.result)[:200])
    mock.stop()
    print("\nBRACES RESULT:", "PASS" if not failures else f"FAIL ({len(failures)}): {failures}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
