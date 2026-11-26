"""Builds CrewAI objects from a GUI specification and runs them with live events."""
from __future__ import annotations

import contextlib
import io
import json
import os
import re
import sys
import threading
import time
import traceback
from collections import deque
from pathlib import Path
from typing import Any, Callable, Iterator

from . import crewai_env
from .statuses import ACTIVE, TERMINAL
from . import security
from . import tools as tool_registry
from . import workspace as workspace_mod
from .config import OUTPUTS_DIR
from .spec import inputs_for_run, resolve_llm
from .store import Store, as_jsonable, new_id, now_iso

MAX_TEXT = 200_000
MAX_EVENTS = 12_000
_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def env_lock() -> threading.Lock:
    return _ENV_LOCK


PROVIDER_ENV_KEYS = (
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "OPENAI_API_BASE",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "OPENROUTER_API_KEY",
    "GROQ_API_KEY",
    "DEEPSEEK_API_KEY",
    "SERPER_API_KEY",
    "EXA_API_KEY",
    "BROWSERBASE_API_KEY",
    "MODEL",
    "OPENAI_MODEL_NAME",
)


class RunCancelled(Exception):
    """Raised inside the run thread when the user presses «Стоп»."""


class BusyError(RuntimeError):
    """Another run is already in progress."""


_status_lock = threading.Lock()
_ENV_LOCK = threading.Lock()
_status_cache: dict | None = None
_status_at = 0.0


def crewai_status(refresh: bool = False) -> dict:
    """Import-crewai probe, cached: the first import can take seconds."""
    global _status_cache, _status_at
    with _status_lock:
        if _status_cache is not None and not refresh:
            # A failure may be a transient import race: retry it after a pause.
            if _status_cache.get("installed") or (time.time() - _status_at) < 3.0:
                return dict(_status_cache)
        info: dict[str, Any] = {
            "installed": False,
            "version": "",
            "python": sys.version.split()[0],
            "executable": sys.executable,
            "error": "",
            "stream_support": False,
        }
        try:
            crewai_env.configure()
            with crewai_env.import_lock():
                import crewai  # noqa: F401

                try:
                    from crewai.types.streaming import CrewStreamingOutput  # noqa: F401

                    info["stream_support"] = True
                except Exception:  # noqa: BLE001
                    info["stream_support"] = False
            info["installed"] = True
            info["version"] = getattr(crewai, "__version__", "unknown")
        except Exception as exc:  # noqa: BLE001
            info["error"] = f"{type(exc).__name__}: {exc}"
        _status_cache = info
        _status_at = time.time()
        return dict(info)


def _truncate(value: str, limit: int = MAX_TEXT) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n… (обрезано, всего {len(text)} символов)"


def _plain(value: Any, limit: int = 4000) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return _truncate(_ANSI_RE.sub("", value), limit)
    try:
        return _truncate(json.dumps(as_jsonable(value), ensure_ascii=False, default=str), limit)
    except Exception:  # noqa: BLE001
        return _truncate(str(value), limit)


class EventRing:
    """Bounded event log with stable sequence numbers: no gaps, no O(N) trimming."""

    def __init__(self, maxlen: int = MAX_EVENTS) -> None:
        self._buf: deque[dict] = deque(maxlen=maxlen)
        self._lock = threading.Lock()
        self._last = 0

    def append(self, event: dict) -> int:
        with self._lock:
            self._last += 1
            event["seq"] = self._last
            self._buf.append(event)
            return self._last

    def after(self, seq: int) -> list[dict]:
        with self._lock:
            if not self._buf:
                return []
            first = self._buf[0]["seq"]
            start = max(0, seq - first + 1)
            return list(self._buf)[start:]

    def __iter__(self):
        with self._lock:
            return iter(list(self._buf))

    def __len__(self) -> int:
        with self._lock:
            return len(self._buf)

    @property
    def last_seq(self) -> int:
        with self._lock:
            return self._last


def _tool_target(raw: object) -> str:
    """A short hint of what the tool acted on: file name, url or query."""
    text = str(raw or "")
    if not text:
        return ""
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return text[:160]
    if isinstance(data, dict):
        for key in ("filename", "path", "file", "file_path", "query", "url", "name"):
            value = data.get(key)
            if value:
                return str(value)[:160]
        keys = ", ".join(str(key) for key in list(data)[:4])
        return f"{{{keys}}}"[:160]
    return text[:160]


class RunState:
    """One execution: its event log, aggregated text and final result."""

    def __init__(self, run_id: str, crew: dict, inputs: dict[str, str], model: str) -> None:
        self.id = run_id
        self.crew_id = crew.get("id", "")
        self.crew_name = crew.get("name", "Crew")
        self.crew_spec = crew
        self.inputs = dict(inputs or {})
        self.model = model
        self.workspace = ""
        self.status = "queued"
        self.created_at = now_iso()
        self.started_at = ""
        self.finished_at = ""
        self.duration = 0.0
        self.result: dict | None = None
        self.error = ""
        self.task_text: dict[str, list[str]] = {}
        self.events = EventRing()
        self.usage: dict[str, int] = {}
        self.cancelled = False
        self.abandoned = False
        self.persist_cb: Callable[[], None] | None = None
        self._last_persist = time.time()
        self._persist_events = 0
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._perm_lock = threading.RLock()
        self._perm_waiters: dict[str, dict] = {}
        self._perm_grants: set[tuple[str, str]] = set()
        self._perm_seq = 0

    # ----------------------------------------------------------- permissions
    @staticmethod
    def _grant_key(kind: str, target: str, grant: str = "file", base: str | None = None) -> tuple[str, str]:
        """Run-scope grant covers exactly what the dialog promised: a file or a folder."""
        text = str(target)
        if grant != "folder":
            return (kind, text)
        folder = Path(base) if base else Path(text).parent
        if folder.parent == folder or folder == Path.home().resolve():
            return (kind, text)
        return (kind, str(folder))

    def ask_permission(
        self,
        kind: str,
        target: str,
        reason: str = "",
        agent: str = "",
        timeout: float = 300.0,
        grant: str = "file",
        base: str | None = None,
    ) -> tuple[bool, str]:
        """Block until the user answers, the run is cancelled or the timeout hits."""
        grant_kind = "folder" if grant == "folder" else "file"
        grant_key = self._grant_key(kind, target, grant_kind, base)
        with self._perm_lock:
            if grant_key in self._perm_grants:
                return True, ""
            self._perm_seq += 1
            req_id = f"perm-{self._perm_seq}"
            waiter = {
                "event": threading.Event(),
                "allowed": None,
                "note": "",
                "kind": kind,
                "target": str(target),
                "grant": grant_kind,
                "base": str(base) if base else "",
            }
            self._perm_waiters[req_id] = waiter

        self.emit(
            "permission_request",
            {
                "id": req_id,
                "kind": kind,
                "target": str(target),
                "reason": reason,
                "agent": agent,
                "timeout": int(timeout),
                "grant": grant_kind,
                "grant_target": str(self._grant_key(kind, target, grant_kind, base)[1]),
            },
        )
        if not waiter["event"].wait(timeout):
            with self._perm_lock:
                self._perm_waiters.pop(req_id, None)
            self.emit("permission_denied", {"id": req_id, "target": str(target), "reason": "timeout"})
            return False, "Время ожидания подтверждения истекло"

        with self._perm_lock:
            self._perm_waiters.pop(req_id, None)
        allowed = bool(waiter.get("allowed"))
        self.emit(
            "permission_resolved",
            {"id": req_id, "target": str(target), "allowed": allowed, "scope": waiter.get("scope", "once")},
        )
        if allowed:
            return True, ""
        return False, waiter.get("note") or "Пользователь не разрешил доступ"

    def answer_permission(self, req_id: str, allow: bool, scope: str = "once") -> bool:
        with self._perm_lock:
            waiter = self._perm_waiters.get(req_id)
            if waiter is None:
                return False
            waiter["allowed"] = bool(allow)
            waiter["scope"] = "run" if scope == "run" else "once"
            if allow and scope == "run":
                self._perm_grants.add(self._grant_key(waiter["kind"], waiter["target"], waiter.get("grant", "file"), waiter.get("base")))
            if not allow:
                waiter["note"] = "Пользователь запретил доступ"
            waiter["event"].set()
        return True

    def pending_permissions(self) -> list[dict]:
        """Requests the run is currently blocked on."""
        with self._perm_lock:
            return [
                {
                    "id": req_id,
                    "kind": waiter.get("kind", ""),
                    "target": waiter.get("target", ""),
                    "grant": waiter.get("grant", "file"),
                    "base": waiter.get("base", ""),
                }
                for req_id, waiter in self._perm_waiters.items()
            ]

    def deny_pending_permissions(self, note: str = "Запуск остановлен") -> None:
        with self._perm_lock:
            for waiter in self._perm_waiters.values():
                waiter["allowed"] = False
                waiter["note"] = note
                waiter["event"].set()

    # ---------------------------------------------------------------- events
    def emit(self, etype: str, data: dict | None = None) -> None:
        payload = {k: v for k, v in (data or {}).items() if v is not None}
        if etype == "llm_chunk":
            # Raw model tokens are accumulated for the final text but never sent
            # as events: a long answer would flood the UI and freeze the tab.
            with self._cond:
                task = str(payload.get("task") or payload.get("agent") or "output")
                self.task_text.setdefault(task, []).append(str(payload.get("text") or ""))
            return
        with self._cond:
            event = {"ts": round(time.time(), 3), "type": etype, "data": payload}
            self.events.append(event)
            self._cond.notify_all()
        if etype != "llm_chunk":
            self._maybe_persist()

    def _maybe_persist(self) -> None:
        """Checkpoint the snapshot every ~30 s or 200 events so progress survives a crash."""
        if self.persist_cb is None:
            return
        self._persist_events += 1
        now = time.time()
        if self._persist_events < 200 and (now - self._last_persist) < 30:
            return
        self._persist_events = 0
        self._last_persist = now
        try:
            self.persist_cb()
        except Exception:  # noqa: BLE001 - a checkpoint must never break a run
            pass

    def wait_events(self, after: int, timeout: float = 15.0) -> list[dict]:
        deadline = time.monotonic() + timeout
        with self._cond:
            while self.events.last_seq <= after:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._cond.wait(remaining)
        return self.events.after(after)

    def add_text(self, task: str, text: str) -> None:
        """Accumulate streamed text without emitting a chunk event."""
        with self._lock:
            self.task_text.setdefault(task, []).append(text)

    def cancel(self) -> bool:
        if self.status in {"queued", "running"}:
            self.cancelled = True
            self.status = "cancelling"
            self.deny_pending_permissions("Запуск остановлен пользователем")
            self.emit("cancel_requested", {"message": "Останавливаю выполнение…"})
            return True
        return False

    # ------------------------------------------------------------ persistence
    def text_for(self, task: str) -> str:
        return "".join(self.task_text.get(task, []))

    def snapshot(self) -> dict:
        with self._lock:
            events = [e for e in self.events if e["type"] != "llm_chunk"]
            if len(events) > 3000:
                events = events[-3000:]
            return {
                "id": self.id,
                "crew_id": self.crew_id,
                "crew_name": self.crew_name,
                "model": self.model,
                "status": self.status,
                "inputs": self.inputs,
                "created_at": self.created_at,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
                "duration": self.duration,
                "result": self.result,
                "error": self.error,
                "usage": self.usage,
                "events": events,
                "workspace": self.workspace,
                "task_text": {name: _truncate(text, 20_000) for name, text in self.task_text.items() if text},
                "crew": self.crew_spec,
            }


class RunManager:
    """Serialises crew executions; the event bus is process-global, so runs must not overlap."""

    def __init__(self, store: Store) -> None:
        self.store = store
        self._states: dict[str, RunState] = {}
        self._active: str | None = None
        self._lock = threading.Lock()
        # Runs interrupted by an app restart would otherwise stay "running" forever.
        try:
            self.store.mark_orphaned_runs()
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------ query
    def get(self, run_id: str) -> RunState | None:
        return self._states.get(run_id)

    def active_id(self) -> str | None:
        return self._active

    def is_busy(self) -> bool:
        with self._lock:
            return self._active is not None

    # ------------------------------------------------------------------ start
    def start(self, crew: dict, inputs: dict[str, str], settings: dict) -> RunState:
        with self._lock:
            if self._active:
                raise BusyError("Дождитесь завершения текущего запуска или остановите его.")
            status = crewai_status()
            if not status["installed"]:
                raise RuntimeError(
                    "CrewAI не установлен в этом окружении. Запустите start.bat — он создаст venv и установит зависимости."
                )
            run_id = f"{time.strftime('%Y%m%d-%H%M%S')}-{new_id()[:6]}"
            model = resolve_llm("", crew.get("default_llm", ""), settings.get("default_llm", ""))
            state = RunState(run_id, crew, inputs, model)
            self._states[run_id] = state
            self._active = run_id
            self._trim_memory()
        self.store.save_run(state.snapshot())
        state.persist_cb = lambda: self.store.save_run(state.snapshot())
        thread = threading.Thread(target=self._execute_safe, args=(state, settings), name=f"run-{run_id}", daemon=True)
        thread.start()
        return state

    def _trim_memory(self) -> None:
        finished = [
            rid for rid, st in self._states.items()
            if st.status in TERMINAL and rid != self._active
        ]
        for rid in finished[: max(0, len(finished) - 15)]:
            self._states.pop(rid, None)

    def cancel(self, run_id: str) -> bool:
        state = self._states.get(run_id)
        if state is None:
            return False
        cancelled = state.cancel()
        if cancelled:
            threading.Thread(target=self._cancel_watchdog, args=(state,), daemon=True).start()
        return cancelled

    def _cancel_watchdog(self, state: RunState, grace: float = 12.0) -> None:
        """A model call or tool can ignore the flag: mark the run forced, keep the slot."""
        deadline = time.time() + grace
        while time.time() < deadline:
            if state.status in TERMINAL:
                return
            time.sleep(0.25)
        if state.status in TERMINAL:
            return
        state.status = "force_stopping"
        state.emit(
            "force_stopping",
            {
                "message": "Модель или инструмент не реагируют. Запуск помечен как принудительно "
                "останавливаемый; слот освободится, когда поток завершится, либо нажмите «Отсоединить».",
            },
        )

    def detach(self, run_id: str) -> bool:
        """Give up on a stuck run: free the slot, ignore its writes and permissions."""
        state = self._states.get(run_id)
        if state is None or state.abandoned:
            return False
        if state.status in {"completed", "failed"}:
            return False
        state.abandoned = True
        state.cancelled = True
        state.deny_pending_permissions("Запуск отсоединён")
        state.status = "cancelled"
        if not getattr(state, "_ended", False):
            state._ended = True
            state.emit("run_cancelled", {"message": "Запуск отсоединён", "detached": True})
            state.emit("stream_end", {"status": "cancelled", "detached": True})
        with self._lock:
            if self._active == state.id:
                self._active = None
        return True

    def answer_permission(self, run_id: str, request_id: str, allow: bool, scope: str = "once") -> bool:
        state = self._states.get(run_id)
        if state is None:
            return False
        return state.answer_permission(request_id, allow, scope)

    # -------------------------------------------------------------- execution
    def _execute_safe(self, state: RunState, settings: dict) -> None:
        try:
            self._execute(state, settings)
        except RunCancelled:
            state.status = "cancelled"
            state.emit("run_cancelled", {"message": "Запуск остановлен пользователем"})
        except Exception as exc:  # noqa: BLE001 - surface everything to the UI
            if state.abandoned:
                state.status = "cancelled"
            else:
                state.status = "failed"
                state.error = f"{type(exc).__name__}: {exc}"
                state.emit("error", {"message": state.error, "traceback": traceback.format_exc(limit=12)})
        finally:
            state.finished_at = now_iso()
            if state.started_at:
                state.duration = round(time.time() - state._started_ts, 2) if hasattr(state, "_started_ts") else 0.0
            try:
                self.store.save_run(state.snapshot())
            except Exception:  # noqa: BLE001
                pass
            with self._lock:
                if self._active == state.id:
                    self._active = None
            if not getattr(state, "_ended", False):
                state._ended = True
                state.emit("stream_end", {"status": state.status})

    def _execute(self, state: RunState, settings: dict) -> None:
        crewai_env.configure()
        import crewai
        from crewai import LLM, Agent, Crew, Process, Task

        settings_env = self.store.effective_env()
        roots = workspace_mod.allowed_roots((settings.get("fs_roots") or []))
        workspace, fallback_note = workspace_mod.for_crew(state.crew_spec, roots)
        env = settings_env
        # The process environment is not a stack: set what this run needs and
        # leave it in place. Restoring a snapshot after a detach would pin an
        # older run's keys over the settings the user just saved.
        with _ENV_LOCK:
            for key in PROVIDER_ENV_KEYS:
                if key not in env:
                    os.environ.pop(key, None)
            os.environ.update({k: v for k, v in env.items() if v})
        state.status = "running"
        state.started_at = now_iso()
        state._started_ts = time.time()

        state.workspace = str(workspace)
        if fallback_note:
            state.emit("warning", {"message": fallback_note})
            state.emit("info", {"message": f"Использую папку по умолчанию: {workspace}"})

        state.emit(
            "run_started",
            {
                "crew": state.crew_name,
                "model": state.model,
                "inputs": state.inputs,
                "workspace": state.workspace,
            },
        )
        state.emit("info", {"message": f"Рабочая область: {state.workspace}"})

        stream_supported = crewai_status()["stream_support"]
        emit_chunks = bool(settings.get("live_stream"))
        if stream_supported and not emit_chunks:
            state.emit("info", {"message": "Потоковая передача выключена: текст появится по завершении задач, отмена работает"})
        tool_cache: dict[tuple[str, bool, str], Any] = {}
        warnings: list[str] = []

        memory_enabled, memory_note = memory_available(state.crew_spec, env)
        if memory_note:
            state.emit("warning", {"message": memory_note})

        agent_specs = state.crew_spec.get("agents", [])
        max_iter_top = max((int(a.get("max_iter") or 12) for a in agent_specs), default=12)
        time_limits = [int(a.get("max_execution_time") or 0) for a in agent_specs]
        reasoning_count = sum(1 for a in agent_specs if a.get("reasoning"))
        tools_count = sum(len(a.get("tools") or []) for a in agent_specs)
        rag_tools = sorted(
            {tool for a in agent_specs for tool in (a.get("tools") or []) if tool in tool_registry.RAG_TOOL_NAMES}
        )
        if rag_tools and not (env.get("OPENAI_API_KEY") or env.get("GEMINI_API_KEY") or env.get("GOOGLE_API_KEY")):
            state.emit(
                "warning",
                {
                    "message": f"Инструменты {', '.join(rag_tools)} ищут по эмбеддингам: без ключа OpenAI/Gemini "
                    "они будут падать с ошибкой и тормозить запуск.",
                },
            )
        state.emit(
            "info",
            {
                "message": (
                    f"Параметры: итераций до {max_iter_top}, лимит времени "
                    f"{min([t for t in time_limits if t] or [0]) or 'нет'} с, "
                    f"рассуждения {'да' if reasoning_count else 'нет'}, "
                    f"память {'да' if memory_enabled else 'нет'}, инструментов {tools_count}"
                )
            },
        )

        allowed_network = tool_registry.allowed_network_names(settings.get("allow_network_tools"))

        def build_tools(names: list[str], confirm: bool = False, agent_role: str = "") -> list[Any]:
            built = []
            for name in names or []:
                cache_key = (name, bool(confirm), agent_role)
                if cache_key in tool_cache:
                    built.append(tool_cache[cache_key])
                    continue
                try:
                    obj = tool_registry.build_tool(
                        name, env, workspace, bool(confirm), agent_role, state, name in allowed_network
                    )
                except Exception as exc:  # noqa: BLE001
                    warnings.append(f"Инструмент «{name}» недоступен: {exc}")
                    state.emit("warning", {"message": warnings[-1]})
                    continue
                tool_cache[cache_key] = obj
                built.append(obj)
            return built

        agents: dict[str, Any] = {}
        agent_meta: list[dict] = []
        default_global = settings.get("default_llm", "")
        llm_timeout = int(settings.get("llm_timeout") or 120)
        for spec in state.crew_spec.get("agents", []):
            llm = resolve_llm(spec.get("llm", ""), state.crew_spec.get("default_llm", ""), default_global)
            kwargs: dict[str, Any] = {
                "role": spec.get("role", "") or "Помощник",
                "goal": spec.get("goal", "") or "Выполнить задачу",
                "backstory": spec.get("backstory", "") or "Опытный специалист",
                "max_iter": int(spec.get("max_iter") or 12),
                "allow_delegation": bool(spec.get("allow_delegation")),
                "cache": bool(spec.get("cache", True)),
                "reasoning": bool(spec.get("reasoning")),
                "verbose": bool(state.crew_spec.get("verbose")),
            }
            max_exec = int(spec.get("max_execution_time") or 0)
            if max_exec > 0:
                kwargs["max_execution_time"] = max_exec
            if kwargs["reasoning"]:
                # ``None`` means "retry until ready" in CrewAI, which can loop for a long time.
                kwargs["max_reasoning_attempts"] = int(spec.get("max_reasoning_attempts") or 2)
            if llm:
                try:
                    kwargs["llm"] = LLM(model=llm, timeout=llm_timeout)
                except Exception:  # noqa: BLE001 - fall back to the plain model string
                    kwargs["llm"] = llm
            tools_built = build_tools(
                spec.get("tools") or [],
                bool(spec.get("confirm_changes")),
                spec.get("role", "") or "",
            )
            if tools_built:
                kwargs["tools"] = tools_built
            try:
                agents[spec.get("id")] = Agent(**kwargs)
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(f"Не удалось создать агента «{spec.get('role')}»: {exc}") from exc
            agent_meta.append(
                {"id": spec.get("id"), "role": spec.get("role"), "llm": llm or "(по умолчанию)",
                 "tools": [t.name if hasattr(t, "name") else str(t) for t in tools_built]}
            )

        tasks: list[Any] = []
        task_by_id: dict[str, Any] = {}
        task_meta: list[dict] = []
        for spec in state.crew_spec.get("tasks", []):
            task_kwargs: dict[str, Any] = {
                "description": spec.get("description", ""),
                "expected_output": spec.get("expected_output", ""),
                "async_execution": bool(spec.get("async_execution")),
                # CrewAI 1.15 asks for human feedback only in the console: passing the
            # flag to Task would block the run on ``input()`` and fail headlessly.
            }
            agent = agents.get(spec.get("agent") or "")
            if agent is not None and state.crew_spec.get("process") != "hierarchical":
                task_kwargs["agent"] = agent
            fmt = spec.get("output_format")
            if fmt == "markdown":
                task_kwargs["markdown"] = True
            if fmt == "file" and spec.get("output_file"):
                raw = str(spec["output_file"]).strip()
                name = Path(raw).name
                target = security.confine(name, workspace, "output_file")
                task_kwargs["output_file"] = str(target)
                task_kwargs["create_directory"] = True
            task_tools = build_tools(spec.get("tools") or [])
            if task_tools:
                task_kwargs["tools"] = task_tools
            context_specs = [task_by_id[c] for c in (spec.get("context") or []) if c in task_by_id]
            if context_specs:
                task_kwargs["context"] = context_specs
            task_kwargs["name"] = spec.get("name") or None
            try:
                task = Task(**{k: v for k, v in task_kwargs.items() if v is not None})
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(f"Не удалось создать задачу «{spec.get('name') or spec.get('description')[:40]}»: {exc}") from exc
            tasks.append(task)
            task_by_id[spec.get("id")] = task
            task_meta.append(
                {"id": spec.get("id"), "name": spec.get("name") or "", "agent": spec.get("agent"),
                 "description": spec.get("description", "")}
            )

        process = Process.hierarchical if state.crew_spec.get("process") == "hierarchical" else Process.sequential
        crew_kwargs: dict[str, Any] = {
            "agents": list(agents.values()),
            "tasks": tasks,
            "process": process,
            "verbose": bool(state.crew_spec.get("verbose")),
            "cache": bool(state.crew_spec.get("cache", True)),
            "memory": memory_enabled,
            "planning": bool(state.crew_spec.get("planning")),
            # Streaming is always on: it is what makes «Остановить» react quickly.
            "stream": bool(stream_supported),
        }
        rpm = int(state.crew_spec.get("max_rpm") or settings.get("max_rpm") or 0)
        if rpm > 0:
            crew_kwargs["max_rpm"] = rpm
        if process is Process.hierarchical:
            manager = resolve_llm(state.crew_spec.get("manager_llm", ""), state.crew_spec.get("default_llm", ""), default_global)
            crew_kwargs["manager_llm"] = manager or state.model or "openai/gpt-4o-mini"
        if crew_kwargs["planning"]:
            crew_kwargs["planning_llm"] = state.model or default_global or "openai/gpt-4o-mini"

        if emit_chunks:
            state.emit("info", {"message": "Включена потоковая передача ответов моделей"})

        state.emit(
            "plan",
            {
                "agents": agent_meta,
                "tasks": task_meta,
                "process": state.crew_spec.get("process"),
                "stream": emit_chunks,
            },
        )

        crew = self._make_crew(Crew, crew_kwargs, state, warnings)

        # --- event bus: structured progress ---------------------------------
        bus = None
        handler_scope = None
        try:
            from crewai.events import crewai_event_bus as bus  # type: ignore

            handler_scope = bus.scoped_handlers()
            handler_scope.__enter__()
            self._register_handlers(bus, state)
        except Exception as exc:  # noqa: BLE001
            state.emit("warning", {"message": f"Живые события CrewAI недоступны: {exc}"})
            bus = None

        try:
            try:
                output = crew.kickoff(inputs=inputs_for_run(state.crew_spec, state.inputs))
            except ValueError as exc:
                if "template variable" in str(exc).lower():
                    raise RuntimeError(
                        "В тексте задачи есть фигурные скобки, которых нет во «Входных данных». "
                        "Добавьте это поле во входные данные или экранируйте скобки как {{…}}."
                    ) from exc
                raise
            result = self._consume_output(state, output, stream_supported, emit_chunks)
        finally:
            if bus is not None and handler_scope is not None:
                with contextlib.suppress(Exception):
                    handler_scope.__exit__(None, None, None)

        state.usage = dict((result.get("token_usage") or {})) if isinstance(result, dict) else {}
        if state.cancelled or state.abandoned:
            # A cancelled run must never come back as "completed" in history.
            state.result = result
            state.status = "cancelled"
            if not state.abandoned:
                state.emit("run_cancelled", {"message": "Запуск остановлен пользователем"})
            return
        state.result = result
        state.status = "completed"
        state.emit("run_done", {"result": result})
        total = (state.usage or {}).get("total_tokens", 0)
        state.emit("info", {"message": f"Готово за {state.duration or round(time.time() - state._started_ts, 1)} с · токенов: {total}"})

    def _make_crew(self, Crew: Any, kwargs: dict, state: RunState, warnings: list[str]) -> Any:
        try:
            return Crew(**kwargs)
        except Exception as exc:  # noqa: BLE001
            if kwargs.get("memory") and "chroma" in str(exc).lower():
                warnings.append("Память недоступна (нет chromadb) — запускаю без памяти")
                state.emit("warning", {"message": warnings[-1]})
                kwargs["memory"] = False
                return Crew(**kwargs)
            raise

    def _register_handlers(self, bus: Any, state: RunState) -> None:
        from crewai.events import (  # type: ignore
            AgentExecutionCompletedEvent,
            AgentExecutionStartedEvent,
            CrewKickoffCompletedEvent,
            CrewKickoffFailedEvent,
            CrewKickoffStartedEvent,
            LLMCallCompletedEvent,
            LLMCallFailedEvent,
            TaskCompletedEvent,
            TaskFailedEvent,
            TaskStartedEvent,
            ToolUsageErrorEvent,
            ToolUsageFinishedEvent,
            ToolUsageStartedEvent,
        )

        def guard(fn: Callable[[Any, Any], None]) -> Callable[[Any, Any], None]:
            def inner(source: Any, event: Any) -> None:
                if state.cancelled:
                    # The streaming loop stops the run; CrewAI swallows listener
                    # exceptions anyway, so raising here would only add noise.
                    return
                try:
                    fn(source, event)
                except Exception as exc:  # noqa: BLE001 - never break a run because of UI glue
                    state.emit("warning", {"message": f"Событие пропущено: {exc}"})

            return inner

        @guard
        def on_crew_start(source: Any, event: Any) -> None:
            state.emit("crew_start", {"name": getattr(event, "crew_name", state.crew_name)})

        @guard
        def on_crew_done(source: Any, event: Any) -> None:
            state.emit(
                "crew_done",
                {"tokens": getattr(event, "total_tokens", 0), "output": _plain(getattr(event, "output", ""), 2000)},
            )

        @guard
        def on_crew_failed(source: Any, event: Any) -> None:
            state.emit("error", {"message": str(getattr(event, "error", "ошибка crew"))})

        @guard
        def on_task_start(source: Any, event: Any) -> None:
            task = getattr(event, "task", None)
            state.emit(
                "task_start",
                {
                    "name": getattr(event, "task_name", None) or getattr(task, "name", "") or "",
                    "agent": getattr(event, "agent_role", None) or "",
                    "description": _plain(getattr(task, "description", ""), 3000),
                },
            )

        @guard
        def on_task_done(source: Any, event: Any) -> None:
            out = getattr(event, "output", None)
            state.emit(
                "task_done",
                {
                    "name": getattr(event, "task_name", None) or getattr(out, "name", "") or "",
                    "agent": getattr(event, "agent_role", None) or getattr(out, "agent", ""),
                    "output": _plain(getattr(out, "raw", out), 20_000),
                },
            )

        @guard
        def on_task_failed(source: Any, event: Any) -> None:
            state.emit(
                "task_failed",
                {"name": getattr(event, "task_name", "") or "", "error": str(getattr(event, "error", ""))[:4000]},
            )

        @guard
        def on_agent_start(source: Any, event: Any) -> None:
            state.emit(
                "agent_start",
                {
                    "agent": getattr(event, "agent_role", "") or "Агент",
                    "task": getattr(event, "task_name", "") or "",
                },
            )

        @guard
        def on_agent_done(source: Any, event: Any) -> None:
            state.emit(
                "agent_done",
                {
                    "agent": getattr(event, "agent_role", "") or "Агент",
                    "task": getattr(event, "task_name", "") or "",
                    "output": _plain(getattr(event, "output", ""), 4000),
                },
            )

        @guard
        def on_tool_start(source: Any, event: Any) -> None:
            state.emit(
                "tool_start",
                {
                    "tool": getattr(event, "tool_name", "") or "",
                    "agent": getattr(event, "agent_role", "") or "",
                    "task": getattr(event, "task_name", "") or "",
                    "target": _tool_target(getattr(event, "tool_args", "")),
                },
            )

        @guard
        def on_tool_done(source: Any, event: Any) -> None:
            output = getattr(event, "output", None)
            if output is None:
                output = getattr(event, "tool_output", None)
            state.emit(
                "tool_done",
                {
                    "tool": getattr(event, "tool_name", "") or "",
                    "agent": getattr(event, "agent_role", "") or "",
                    "output": _plain(output, 3000),
                    "failed": bool(getattr(event, "failure", None) or getattr(event, "error", None)),
                },
            )

        @guard
        def on_tool_error(source: Any, event: Any) -> None:
            state.emit(
                "tool_error",
                {
                    "tool": getattr(event, "tool_name", "") or "",
                    "error": _plain(getattr(event, "error", ""), 2000),
                },
            )

        @guard
        def on_llm_done(source: Any, event: Any) -> None:
            usage = getattr(event, "usage", None)
            if not usage:
                return
            data = as_jsonable(usage) if not isinstance(usage, dict) else usage
            if not isinstance(data, dict):
                return
            for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                if isinstance(data.get(key), int):
                    state.usage[key] = state.usage.get(key, 0) + int(data[key])
            state.emit("usage", dict(state.usage))

        @guard
        def on_llm_failed(source: Any, event: Any) -> None:
            state.emit("warning", {"message": f"Ошибка вызова LLM: {_plain(getattr(event, 'error', ''), 800)}"})

        handlers = [
            (CrewKickoffStartedEvent, on_crew_start),
            (CrewKickoffCompletedEvent, on_crew_done),
            (CrewKickoffFailedEvent, on_crew_failed),
            (TaskStartedEvent, on_task_start),
            (TaskCompletedEvent, on_task_done),
            (TaskFailedEvent, on_task_failed),
            (AgentExecutionStartedEvent, on_agent_start),
            (AgentExecutionCompletedEvent, on_agent_done),
            (ToolUsageStartedEvent, on_tool_start),
            (ToolUsageFinishedEvent, on_tool_done),
            (ToolUsageErrorEvent, on_tool_error),
            (LLMCallCompletedEvent, on_llm_done),
            (LLMCallFailedEvent, on_llm_failed),
        ]
        for event_cls, handler in handlers:
            try:
                bus.on(event_cls)(handler)
            except Exception as exc:  # noqa: BLE001
                state.emit("warning", {"message": f"Не удалось подписаться на {event_cls.__name__}: {exc}"})

    def _consume_output(
        self,
        state: RunState,
        output: Any,
        streaming: bool,
        emit_chunks: bool = True,
    ) -> dict:
        is_stream = False
        if streaming:
            try:
                from crewai.types.streaming import CrewStreamingOutput  # type: ignore

                is_stream = isinstance(output, CrewStreamingOutput)
            except Exception:  # noqa: BLE001
                is_stream = hasattr(output, "result") and hasattr(output, "__iter__")

        if is_stream:
            last_task = ""
            for chunk in output:  # type: ignore[union-attr]
                if state.cancelled:
                    with contextlib.suppress(Exception):
                        output.close()  # type: ignore[union-attr]
                    raise RunCancelled()
                text = getattr(chunk, "content", None)
                task_name = getattr(chunk, "task_name", "") or ""
                agent_role = getattr(chunk, "agent_role", "") or ""
                if text:
                    if task_name and task_name != last_task:
                        last_task = task_name
                        state.emit("task_focus", {"name": task_name})
                    if emit_chunks:
                        state.emit(
                            "llm_chunk",
                            {
                                "text": str(text),
                                "task": task_name,
                                "agent": agent_role,
                                "index": getattr(chunk, "task_index", None),
                            },
                        )
                    else:
                        state.add_text(task_name or agent_role or "output", str(text))
            if state.cancelled:
                raise RunCancelled()
            raw_result = getattr(output, "result", None)
        else:
            raw_result = output
        return serialize_result(raw_result)


def memory_available(crew: dict, env: dict[str, str]) -> tuple[bool, str]:
    """CrewAI memory needs an embeddings provider; without one it only slows runs down."""
    if not crew.get("memory"):
        return False, ""
    if env.get("OPENAI_API_KEY") or env.get("OPENAI_BASE_URL") or env.get("GEMINI_API_KEY") or env.get("GOOGLE_API_KEY"):
        return True, ""
    return False, (
        "Память отключена: для эмбеддингов нужен ключ OpenAI, Gemini или OpenAI-совместимый сервер. "
        "Без него память тормозит запуск и выдаёт ошибки."
    )


def serialize_result(result: Any) -> dict:
    if result is None:
        return {"raw": "", "tasks": [], "token_usage": {}, "json": None}
    raw = getattr(result, "raw", None)
    if raw is None:
        raw = str(result)
    tasks_out = []
    for item in getattr(result, "tasks_output", []) or []:
        tasks_out.append(
            {
                "name": getattr(item, "name", "") or "",
                "agent": str(getattr(item, "agent", "") or ""),
                "description": _plain(getattr(item, "description", ""), 4000),
                "output": _truncate(str(getattr(item, "raw", "") or "")),
            }
        )
    token_usage = as_jsonable(getattr(result, "token_usage", {}) or {})
    json_dict = getattr(result, "json_dict", None)
    return {
        "raw": _truncate(str(raw or "")),
        "tasks": tasks_out,
        "token_usage": token_usage if isinstance(token_usage, dict) else {},
        "json": as_jsonable(json_dict) if json_dict is not None else None,
    }


def stream_lines(manager: "RunManager", run_id: str, after: int = 0, heartbeat: float = 15.0) -> Iterator[str]:
    """Server-Sent-Events generator for one run.

    ``after`` comes from the Last-Event-ID header, so a reconnect resumes instead
    of replaying the whole log.
    """
    state = manager.get(run_id)
    yield f"event: hello\ndata: {json.dumps({'run_id': run_id}, ensure_ascii=False)}\n\n"
    if state is None:
        yield f"event: gone\ndata: {json.dumps({'run_id': run_id})}\n\n"
        return
    last = max(0, int(after or 0))
    first_available = state.events.after(0)
    if last and first_available and last < first_available[0]["seq"] - 1:
        yield f"event: dropped\ndata: {json.dumps({'from': first_available[0]['seq']}, ensure_ascii=False)}\n\n"
        last = first_available[0]["seq"] - 1
    idle = 0.0
    silent_final = 0.0
    while True:
        events = state.wait_events(last, timeout=0.5)
        if events:
            silent_final = 0.0
            for event in events:
                last = event["seq"]
                yield f"id: {event['seq']}\nevent: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
            continue
        if state.status in TERMINAL:
            silent_final += 0.5
            if silent_final >= 2.0:
                break
        idle += 0.5
        if idle >= heartbeat:
            idle = 0.0
            yield ": keep-alive\n\n"
