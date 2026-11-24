"""A task with the legacy human_input flag must run, not hang on input()."""
from __future__ import annotations

import os
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

DATA = ROOT / ".setup" / f"humanflag-{uuid.uuid4().hex[:6]}"
(DATA / "crews").mkdir(parents=True, exist_ok=True)
os.environ["CREWAI_STUDIO_DATA"] = str(DATA)

from mock_llm import MockLLMServer  # noqa: E402

from app.runner import RunManager  # noqa: E402
from app.spec import normalize_crew, validate_crew  # noqa: E402
from app.store import Store  # noqa: E402

MOCK_PORT = 8917
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
        "name": "Human flag",
        "default_llm": "openai/gpt-4o-mini",
        "agents": [{"role": "Writer", "goal": "Write a note", "backstory": "Brief.", "max_iter": 3}],
        "tasks": [{"name": "Note", "description": "Write a note", "expected_output": "A note", "human_input": True}],
    })
    crew["tasks"][0]["agent"] = crew["agents"][0]["id"]

    validation = validate_crew(crew, {"read_local_file"})
    check("legacy human_input does not block validation", validation["ok"], str(validation["errors"])[:120])
    check("the flag is reported as ignored",
          any("игнорируется" in item["message"] for item in validation["warnings"]),
          str(validation["warnings"])[:160])

    manager = RunManager(store)
    state = manager.start(crew, {}, store.get_settings())
    deadline = time.time() + 90
    while state.status in {"queued", "running"} and time.time() < deadline:
        time.sleep(0.2)
    check("run completes instead of waiting for console input", state.status == "completed",
          f"{state.status}: {state.error}")
    mock.stop()
    print("\nHUMAN FLAG RESULT:", "PASS" if not failures else f"FAIL ({len(failures)}): {failures}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
