"""Tests for permission prompts, write confirmation, key encryption and template edits."""
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

DATA = ROOT / ".setup" / f"perm-{uuid.uuid4().hex[:8]}"
DATA.mkdir(parents=True, exist_ok=True)
os.environ["CREWAI_STUDIO_DATA"] = str(DATA)

from app.runner import RunState  # noqa: E402
from app.store import Store  # noqa: E402
from app.tools import build_tool  # noqa: E402

failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print(("PASS  " if condition else "FAIL  ") + name + (f" — {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(name)


def wait_for_request(state: RunState, timeout: float = 5.0) -> dict | None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        for event in list(state.events):
            if event["type"] == "permission_request":
                return event["data"]
        time.sleep(0.02)
    return None


def request_ids(state: RunState) -> set[str]:
    return {e["data"]["id"] for e in state.events if e["type"] == "permission_request"}


def wait_new_request(state: RunState, seen: set[str], timeout: float = 8.0) -> dict | None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        fresh = [
            e["data"]
            for e in list(state.events)
            if e["type"] == "permission_request" and e["data"]["id"] not in seen
        ]
        if fresh:
            return fresh[-1]
        time.sleep(0.02)
    return None


def main() -> int:
    workspace = DATA / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    # ---------------------------------------------------- write confirmation
    state = RunState("run-test-1", {"id": "crew-test", "name": "Тест", "workspace": str(workspace)}, {}, "openai/gpt-4o-mini")
    state.status = "running"
    try:
        tool = build_tool("write_local_file", {}, workspace, True, "Аналитик", state)

        result: dict[str, str] = {}

        def run_write() -> None:
            result["value"] = tool._run(filename="report.md", content="привет")

        worker = threading.Thread(target=run_write)
        worker.start()
        request = wait_for_request(state)
        check("write asks for confirmation", request is not None and request["kind"] == "fs_write", str(request))
        check("request names the agent", bool(request and request.get("agent") == "Аналитик"), str(request))
        check("run waits for the answer", worker.is_alive())
        check("event carries the target path", bool(request and "report.md" in request["target"]), str(request))

        state.answer_permission(request["id"], True)
        worker.join(5)
        check("allowed write lands on disk", (workspace / "report.md").is_file())
        check("tool reports success", "сохранён" in result.get("value", ""), result.get("value", ""))

        # ------------------------------------------------- deny a write
        denied: dict[str, str] = {}
        seen = request_ids(state)
        worker = threading.Thread(target=lambda: denied.update(value=tool._run(filename="blocked.md", content="x")))
        worker.start()
        newest = wait_new_request(state, seen)
        check("second write asks again", newest is not None)
        state.answer_permission(newest["id"], False)
        worker.join(5)
        check("denied write is not created", not (workspace / "blocked.md").exists())
        check("tool explains the denial", "не подтверждена" in denied.get("value", "").lower(), denied.get("value", ""))

        # ------------------------------------- remember the answer for the run
        seen = request_ids(state)
        worker = threading.Thread(target=lambda: denied.update(value=tool._run(filename="second.md", content="y")))
        worker.start()
        newest = wait_new_request(state, seen)
        state.answer_permission(newest["id"], True, "run")
        worker.join(5)
        check("run-scope grant writes the file", (workspace / "second.md").is_file())

        started = time.time()
        tool._run(filename="third.md", content="z")
        check("grant is reused without asking", time.time() - started < 1.0 and (workspace / "third.md").is_file(),
              f"{time.time() - started:.2f}s")

        # ------------------------------------------------ read outside workspace
        outside = DATA / "outside.txt"
        outside.write_text("секрет", encoding="utf-8")
        reader = build_tool("read_local_file", {}, workspace, False, "Исследователь", state)
        result.clear()
        seen = request_ids(state)
        worker = threading.Thread(target=lambda: result.update(value=reader._run(path=str(outside))))
        worker.start()
        newest = wait_new_request(state, seen)
        check("outside read asks for access", newest is not None and newest["kind"] == "fs_read", str(newest))
        state.answer_permission(newest["id"], True)
        worker.join(5)
        check("allowed outside read returns content", "секрет" in result.get("value", ""), result.get("value", ""))

        # ------------------------------------------------------------- timeout
        result.clear()
        started = time.time()
        allowed, note = state.ask_permission("fs_write", str(DATA / "slow.txt"), "тест таймаута", "Агент", timeout=0.3)
        check("timeout denies access", allowed is False and "истекло" in note.lower(), note)
        check("timeout is bounded", time.time() - started < 3.0)
        check("timeout emits an event", any(e["type"] == "permission_denied" for e in state.events))

        # ------------------------------------------------------------- cancel
        cancelled_ok: dict[str, object] = {}
        seen = request_ids(state)
        worker = threading.Thread(
            target=lambda: cancelled_ok.update(
                value=state.ask_permission("fs_write", str(DATA / "cancel.txt"), "отмена", "Агент", timeout=10)
            )
        )
        worker.start()
        wait_new_request(state, seen)
        state.cancelled = True
        state.deny_pending_permissions("Запуск остановлен")
        worker.join(5)
        allowed, note = cancelled_ok.get("value", (None, ""))
        check("cancel denies pending requests", allowed is False, str(cancelled_ok))
    finally:
        pass

    # ------------------------------------------------------------- encryption
    store = Store()
    store.save_settings({"openai_api_key": "sk-live-secret-42", "extra_env": {"SERPER_API_KEY": "serper-secret"}})
    raw = (DATA / "settings.json").read_text(encoding="utf-8")
    check("settings file has no plaintext key", "sk-live-secret-42" not in raw)
    check("settings file is encrypted", "enc:v1:" in raw)
    check("key decrypts for internal use", store.get_settings()["openai_api_key"] == "sk-live-secret-42")
    public = store.public_settings()
    check("public settings hide the key", public["openai_api_key"] == "" and public["secret_flags"]["openai_api_key"])
    check("env secret hidden too", public["extra_env"]["SERPER_API_KEY"] == "" and public["env_flags"]["SERPER_API_KEY"])

    store.save_settings({"openai_api_key": ""})
    check("empty value keeps the stored key", store.get_settings()["openai_api_key"] == "sk-live-secret-42")
    store.save_settings({"openai_api_key": "__clear__"})
    check("explicit clear removes the key", store.get_settings()["openai_api_key"] == "")

    # ------------------------------------------------------ template editing
    from app import templates

    entry = templates.save_custom_template(
        {"name": "Проект", "agents": [{"role": "A", "goal": "g", "backstory": "b"}], "tasks": [{"description": "d", "expected_output": "e"}]},
        "Старое имя",
        "Описание",
    )
    updated = templates.update_custom_template(entry["key"], "Новое имя", "Новое описание")
    check("template rename works", updated is not None and updated["title"] == "Новое имя")
    check("template description updated", updated["description"] == "Новое описание")
    check("template subtitle recalculated", "агент" in (updated.get("subtitle") or ""), updated.get("subtitle"))
    templates.delete_custom_template(entry["key"])

    print("\nPERMISSIONS RESULT:", "PASS" if not failures else f"FAIL ({len(failures)}): {failures}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
