"""File-backed persistence for crews, settings and run history."""
from __future__ import annotations

import json
import os
import re
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from .config import CREWS_DIR, DEFAULT_SETTINGS, RUNS_DIR, SETTINGS_FILE, ensure_dirs, read_legacy_env
from .statuses import STALE_ON_START
from .secrets import decrypt as secrets_decrypt
from .secrets import encrypt as secrets_encrypt
from .secrets import is_encrypted as secrets_is_encrypted

# Stored encrypted at rest; the UI only ever sees flags and masks.
SECRET_FIELDS = (
    "openai_api_key",
    "anthropic_api_key",
    "gemini_api_key",
    "openrouter_api_key",
    "groq_api_key",
    "deepseek_api_key",
    "serper_api_key",
)

# Environment variables that could redirect code execution or TLS inside the app.
# Allow-list: only provider credentials, their base URLs and STUDIO_* extras.
_ALLOWED_ENV_NAMES = {
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_BASE_URL",
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
}
_ALLOWED_ENV_SUFFIXES = ("_API_KEY", "_BASE_URL")


def environment_key_blocked(key: str) -> bool:
    upper = str(key or "").strip().upper()
    if not upper or any(ch in upper for ch in "\r\n="):
        return True
    if upper in _ALLOWED_ENV_NAMES or upper.startswith("STUDIO_"):
        return False
    if upper.endswith(_ALLOWED_ENV_SUFFIXES):
        return False
    return True


_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
RUNS_INDEX = RUNS_DIR / "index.jsonl"


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def new_id(prefix: str = "") -> str:
    token = uuid.uuid4().hex[:10]
    return f"{prefix}{token}" if prefix else token


def _atomic_write(path: Path, payload: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, path)


class Store:
    """Thread-safe JSON store. Every mutating call rewrites one small file."""

    def __init__(self) -> None:
        ensure_dirs()
        self._lock = threading.RLock()
        self.last_blocked_env: list[str] = []
        self.broken_crews: list[dict] = []
        self._settings_cache: dict | None = None
        self._settings_mtime: float = -1.0
        self._index_appends = 0
        self._migrate_plaintext_secrets()
        self._migrate_corrupt_crews()
        try:
            if RUNS_INDEX.exists() and RUNS_INDEX.stat().st_size > 1024 * 1024:
                self._compact_run_index()
        except OSError:
            pass

    def _migrate_plaintext_secrets(self) -> int:
        """One-shot migration at startup instead of a write during a read."""
        stored = self._read_raw_settings()
        changed = 0
        for field in SECRET_FIELDS:
            value = stored.get(field)
            if value and not secrets_is_encrypted(str(value)):
                changed += 1
        env = stored.get("extra_env") or {}
        for value in env.values() if isinstance(env, dict) else []:
            if value and not secrets_is_encrypted(str(value)):
                changed += 1
        if not changed:
            return 0
        try:
            self._write_settings_file(self.get_settings_uncached())
        except OSError:
            return 0
        return changed

    # ------------------------------------------------------------------ crews
    def _crew_path(self, crew_id: str) -> Path:
        if not _SAFE_ID.match(crew_id or ""):
            raise ValueError("invalid crew id")
        return CREWS_DIR / f"{crew_id}.json"

    def list_crews(self) -> list[dict]:
        with self._lock:
            items: list[dict] = []
            self.broken_crews = [
                {"file": path.name, "reason": "Файл проекта повреждён"}
                for path in sorted(CREWS_DIR.glob("*.json.corrupt"))
            ]
            for path in sorted(CREWS_DIR.glob("*.json")):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    self.broken_crews.append({"file": path.name, "reason": "Файл проекта повреждён"})
                    continue
                items.append(
                    {
                        "id": data.get("id", path.stem),
                        "name": data.get("name", path.stem),
                        "description": data.get("description", ""),
                        "process": data.get("process", "sequential"),
                        "agents": len(data.get("agents") or []),
                        "tasks": len(data.get("tasks") or []),
                        "default_llm": data.get("default_llm", ""),
                        "updated_at": data.get("updated_at", ""),
                    }
                )
            items.sort(key=lambda c: c.get("updated_at") or "", reverse=True)
            return items

    def is_corrupt(self, crew_id: str) -> bool:
        try:
            return (CREWS_DIR / f"{crew_id}.json.corrupt").exists()
        except OSError:
            return False

    def _migrate_corrupt_crews(self) -> int:
        """Quarantine damaged project files once, at startup — not during a GET."""
        moved = 0
        for path in sorted(CREWS_DIR.glob("*.json")):
            try:
                json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                try:
                    path.replace(path.with_suffix(".json.corrupt"))
                    moved += 1
                except OSError:
                    continue
        return moved

    def get_crew(self, crew_id: str) -> dict | None:
        path = self._crew_path(crew_id)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def save_crew(self, crew: dict) -> dict:
        crew = dict(crew)
        crew_id = crew.get("id") or new_id("crew-")
        crew["id"] = crew_id
        crew.setdefault("created_at", now_iso())
        crew["updated_at"] = now_iso()
        # Domain-level policy: every save path goes through the same workspace check.
        from .workspace import allowed_roots, assert_safe_target, resolve as resolve_workspace, require_inside

        raw_workspace = str(crew.get("workspace") or "").strip()
        if raw_workspace:
            target = resolve_workspace(raw_workspace, crew_id)
            assert_safe_target(target)
            require_inside(target, allowed_roots((self.get_settings().get("fs_roots") or [])))
        with self._lock:
            _atomic_write(self._crew_path(crew_id), json.dumps(crew, ensure_ascii=False, indent=2))
        return crew

    def delete_crew(self, crew_id: str) -> bool:
        path = self._crew_path(crew_id)
        with self._lock:
            if not path.exists():
                return False
            path.unlink()
            return True

    def duplicate_crew(self, crew_id: str) -> dict | None:
        original = self.get_crew(crew_id)
        if not original:
            return None
        copy = json.loads(json.dumps(original))
        copy["id"] = new_id("crew-")
        copy["name"] = f"{original.get('name', 'Crew')} (копия)"
        copy.pop("created_at", None)
        for agent in copy.get("agents", []):
            agent["id"] = new_id("a-")
        old_task_ids = {t.get("id"): new_id("t-") for t in copy.get("tasks", [])}
        for task in copy.get("tasks", []):
            task["id"] = old_task_ids.get(task.get("id"), new_id("t-"))
            task["context"] = [old_task_ids[c] for c in (task.get("context") or []) if c in old_task_ids]
        return self.save_crew(copy)

    # --------------------------------------------------------------- settings
    def _read_raw_settings(self) -> dict:
        if not SETTINGS_FILE.exists():
            return {}
        try:
            stored = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return stored if isinstance(stored, dict) else {}

    def _write_settings_file(self, settings: dict) -> None:
        """Persist settings with every secret encrypted."""
        storable = dict(settings)
        for field in SECRET_FIELDS:
            if storable.get(field):
                storable[field] = secrets_encrypt(str(storable[field]))
        env = {}
        for key, value in (storable.get("extra_env") or {}).items():
            env[str(key)] = secrets_encrypt(str(value)) if value else ""
        storable["extra_env"] = env
        _atomic_write(SETTINGS_FILE, json.dumps(storable, ensure_ascii=False, indent=2))

    def get_settings(self) -> dict:
        """Settings in plain form for internal use (never sent to the browser).

        Cached by file mtime: /api/status and /api/info are called often and
        decrypting seven keys on every request is wasteful.
        """
        try:
            mtime = SETTINGS_FILE.stat().st_mtime if SETTINGS_FILE.exists() else 0.0
        except OSError:
            mtime = 0.0
        if self._settings_cache is not None and mtime == self._settings_mtime:
            cached = dict(self._settings_cache)
            cached["extra_env"] = dict(self._settings_cache.get("extra_env") or {})
            return cached
        settings = self.get_settings_uncached()
        self._settings_cache = dict(settings)
        self._settings_cache["extra_env"] = dict(settings.get("extra_env") or {})
        self._settings_mtime = mtime
        return settings

    def get_settings_uncached(self) -> dict:
        merged = dict(DEFAULT_SETTINGS)
        merged["extra_env"] = {}
        stored = self._read_raw_settings()
        for key, value in stored.items():
            if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
                merged[key].update(value)
            elif key in merged:
                merged[key] = value
        for field in SECRET_FIELDS:
            if merged.get(field):
                try:
                    merged[field] = secrets_decrypt(str(merged[field]))
                except Exception:  # noqa: BLE001 - keep the app usable if a key is unreadable
                    merged[field] = ""
        env = {}
        for key, value in (merged.get("extra_env") or {}).items():
            try:
                env[str(key)] = secrets_decrypt(str(value)) if value else ""
            except Exception:  # noqa: BLE001
                env[str(key)] = ""
        merged["extra_env"] = env
        return merged

    def public_settings(self) -> dict:
        """Settings safe for the UI: secrets are replaced by flags."""
        settings = self.get_settings()
        public = dict(settings)
        flags: dict[str, bool] = {}
        for field in SECRET_FIELDS:
            flags[field] = bool(settings.get(field))
            public[field] = ""
        env_flags = {str(key): bool(value) for key, value in (settings.get("extra_env") or {}).items()}
        public["extra_env"] = {str(key): "" for key in (settings.get("extra_env") or {})}
        public["secret_flags"] = flags
        public["env_flags"] = env_flags
        return public

    def save_settings(self, patch: dict) -> dict:
        with self._lock:
            self.last_blocked_env = []
            current = self.get_settings()
            for key, value in (patch or {}).items():
                if key not in DEFAULT_SETTINGS or key in {"secret_flags", "env_flags"}:
                    continue
                if key == "run_timeout_minutes":
                    try:
                        current[key] = max(0.0, min(float(value), 1440.0))
                    except (TypeError, ValueError):
                        pass
                    continue
                if key == "max_iter_cap":
                    try:
                        current[key] = max(1, min(int(float(value)), 100))
                    except (TypeError, ValueError):
                        pass
                    continue
                if key == "runs_retention_days":
                    try:
                        current[key] = max(0, min(int(float(value)), 3650))
                    except (TypeError, ValueError):
                        pass
                    continue
                if key == "session_ttl_hours":
                    try:
                        current[key] = max(1, min(int(float(value)), 720))
                    except (TypeError, ValueError):
                        pass
                    continue
                if key == "extra_env":
                    if not isinstance(value, dict):
                        continue
                    merged_env = dict(current.get("extra_env") or {})
                    for env_key, env_value in value.items():
                        env_key = str(env_key).strip()
                        if not env_key:
                            continue
                        if environment_key_blocked(env_key):
                            self.last_blocked_env.append(env_key)
                            continue
                        text = str(env_value or "")
                        if text == "__clear__":
                            merged_env.pop(env_key, None)
                        elif text:
                            merged_env[env_key] = text
                        # empty string means "leave the saved value untouched"
                    current["extra_env"] = merged_env
                    continue
                if key in SECRET_FIELDS:
                    text = str(value or "")
                    if text == "__clear__":
                        current[key] = ""
                    elif text:
                        current[key] = text
                    continue
                current[key] = value
            self._write_settings_file(current)
            self._settings_cache = None
            self._settings_mtime = -1.0
            return current

    def effective_env(self) -> dict[str, str]:
        """Credentials for a run: saved settings win over .env and the process env.

        Precedence is deliberate — the process environment may hold leftovers from
        an earlier run or from the shell, and it must never shadow a key the user
        just saved in the UI.
        """
        settings = self.get_settings()
        env: dict[str, str] = dict(read_legacy_env())
        mapping = {
            "openai_api_key": "OPENAI_API_KEY",
            "openai_base_url": "OPENAI_BASE_URL",
            "anthropic_api_key": "ANTHROPIC_API_KEY",
            "gemini_api_key": "GEMINI_API_KEY",
            "openrouter_api_key": "OPENROUTER_API_KEY",
            "groq_api_key": "GROQ_API_KEY",
            "deepseek_api_key": "DEEPSEEK_API_KEY",
            "serper_api_key": "SERPER_API_KEY",
        }
        env.update({str(k): str(v) for k, v in (settings.get("extra_env") or {}).items()})
        for field, var in mapping.items():
            value = str(settings.get(field) or "").strip()
            if value:
                env[var] = value
            else:
                env.pop(var, None)
        if env.get("OPENAI_BASE_URL"):
            env.setdefault("OPENAI_API_BASE", env["OPENAI_BASE_URL"])
        if env.get("GEMINI_API_KEY"):
            env.setdefault("GOOGLE_API_KEY", env["GEMINI_API_KEY"])
        return env

    # ------------------------------------------------------------------- runs
    def _run_path(self, run_id: str) -> Path:
        if not _SAFE_ID.match(run_id or ""):
            raise ValueError("invalid run id")
        return RUNS_DIR / f"{run_id}.json"

    def save_run(self, run: dict) -> None:
        run_id = run.get("id")
        if not run_id:
            raise ValueError("run without id")
        safe = self._redact_run(run)
        with self._lock:
            _atomic_write(self._run_path(run_id), json.dumps(safe, ensure_ascii=False, indent=2))
            self._append_run_index(safe)

    @staticmethod
    def _redact_run(run: dict) -> dict:
        """Run history keeps prompts and output; credentials echoed by providers must not land there."""
        from .observability import redact

        data = dict(run)
        data["error"] = redact(data.get("error") or "")
        result = data.get("result")
        if isinstance(result, dict):
            cleaned = dict(result)
            for key in ("raw", "output", "final_output"):
                if isinstance(cleaned.get(key), str):
                    cleaned[key] = redact(cleaned[key])
            data["result"] = cleaned
        return data

    # ------------------------------------------------------------- run index
    def _index_entry(self, run: dict) -> dict:
        result = run.get("result") or {}
        return {
            "id": run.get("id", ""),
            "crew_id": run.get("crew_id", ""),
            "crew_name": run.get("crew_name", ""),
            "status": run.get("status", ""),
            "started_at": run.get("started_at", ""),
            "finished_at": run.get("finished_at", ""),
            "duration": run.get("duration", 0),
            "tokens": (result.get("token_usage") or {}).get("total_tokens", 0)
            or (run.get("usage") or {}).get("total_tokens", 0),
            "error": (run.get("error") or "")[:300],
        }

    def _append_run_index(self, run: dict) -> None:
        try:
            with RUNS_INDEX.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(self._index_entry(run), ensure_ascii=False) + "\n")
            self._index_appends += 1
            if self._index_appends >= 500:
                self._compact_run_index()
        except OSError:
            pass

    def _compact_run_index(self) -> int:
        """Rewrite the index with one line per living run: bounded growth and read cost."""
        entries = self._read_run_index()
        alive = {key: entry for key, entry in entries.items() if not entry.get("deleted")}
        tmp = RUNS_INDEX.with_suffix(".jsonl.tmp")
        try:
            tmp.write_text(
                "".join(json.dumps(entry, ensure_ascii=False) + "\n" for entry in alive.values()),
                encoding="utf-8",
            )
            tmp.replace(RUNS_INDEX)
            self._index_appends = 0
        except OSError:
            pass
        return len(alive)

    def _read_run_index(self) -> dict[str, dict]:
        entries: dict[str, dict] = {}
        if not RUNS_INDEX.exists():
            return entries
        try:
            for line in RUNS_INDEX.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if entry.get("id"):
                    entries[entry["id"]] = entry
        except OSError:
            return {}
        return entries

    def _rebuild_run_index(self) -> dict[str, dict]:
        """One-time scan of run files; keeps list_runs cheap afterwards."""
        entries: dict[str, dict] = {}
        for path in RUNS_DIR.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if data.get("id"):
                entries[data["id"]] = self._index_entry(data)
        tmp = RUNS_INDEX.with_suffix(".jsonl.tmp")
        try:
            tmp.write_text(
                "".join(json.dumps(entry, ensure_ascii=False) + "\n" for entry in entries.values()),
                encoding="utf-8",
            )
            tmp.replace(RUNS_INDEX)
        except OSError:
            pass
        return entries

    def get_run(self, run_id: str) -> dict | None:
        path = self._run_path(run_id)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def list_runs(self, limit: int = 100) -> list[dict]:
        with self._lock:
            entries = self._read_run_index()
            if not entries:
                entries = self._rebuild_run_index()
            runs = [entry for entry in entries.values() if not entry.get("deleted")]
            runs.sort(key=lambda r: r.get("started_at") or "", reverse=True)
            return runs[:limit]

    def runs_page(
        self, limit: int = 50, offset: int = 0, status: str = "", crew_id: str = ""
    ) -> dict:
        """A slice of the run history with the total count for the UI."""
        try:
            limit = max(1, min(int(limit), 200))
        except (TypeError, ValueError):
            limit = 50
        try:
            offset = max(0, int(offset))
        except (TypeError, ValueError):
            offset = 0
        with self._lock:
            entries = self._read_run_index()
            if not entries:
                entries = self._rebuild_run_index()
            runs = [entry for entry in entries.values() if not entry.get("deleted")]
            if status:
                runs = [entry for entry in runs if entry.get("status") == status]
            if crew_id:
                runs = [entry for entry in runs if entry.get("crew_id") == crew_id]
            runs.sort(key=lambda entry: entry.get("started_at") or "", reverse=True)
            return {
                "runs": runs[offset : offset + limit],
                "total": len(runs),
                "limit": limit,
                "offset": offset,
            }

    def prune_runs(self, max_runs: int = 5000) -> dict:
        """Delete runs older than the retention setting and cap the total number."""
        from datetime import datetime, timedelta

        settings = self.get_settings()
        try:
            days = int(settings.get("runs_retention_days") or 0)
        except (TypeError, ValueError):
            days = 180
        cutoff = datetime.now() - timedelta(days=days) if days > 0 else None

        removed = 0
        with self._lock:
            entries = self._read_run_index()
            if not entries:
                entries = self._rebuild_run_index()
            alive = [entry for entry in entries.values() if not entry.get("deleted")]
            alive.sort(key=lambda entry: entry.get("started_at") or "", reverse=True)
            keep = []
            for entry in alive:
                stale = False
                if cutoff is not None:
                    try:
                        started = datetime.fromisoformat(str(entry.get("started_at") or ""))
                    except ValueError:
                        started = None
                    stale = bool(started and started < cutoff)
                if stale:
                    try:
                        self._run_path(entry["id"]).unlink(missing_ok=True)
                    except OSError:
                        pass
                    removed += 1
                else:
                    keep.append(entry)
            if len(keep) > max_runs:
                for entry in keep[max_runs:]:
                    try:
                        self._run_path(entry["id"]).unlink(missing_ok=True)
                    except OSError:
                        pass
                    removed += 1
                keep = keep[:max_runs]

            if removed:
                tmp = RUNS_INDEX.with_suffix(".jsonl.tmp")
                try:
                    tmp.write_text(
                        "".join(json.dumps(entry, ensure_ascii=False) + "\n" for entry in keep),
                        encoding="utf-8",
                    )
                    tmp.replace(RUNS_INDEX)
                    self._index_appends = 0
                except OSError:
                    pass
        return {"deleted": removed, "kept": len(keep)}

    def delete_run(self, run_id: str) -> bool:
        path = self._run_path(run_id)
        with self._lock:
            if not path.exists():
                return False
            path.unlink()
            try:
                with RUNS_INDEX.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps({"id": run_id, "deleted": True}, ensure_ascii=False) + "\n")
            except OSError:
                pass
            return True

    def clear_runs(self) -> int:
        count = 0
        with self._lock:
            for path in RUNS_DIR.glob("*.json"):
                try:
                    path.unlink()
                    count += 1
                except OSError:
                    pass
            try:
                RUNS_INDEX.write_text("", encoding="utf-8")
            except OSError:
                pass
        return count

    def mark_orphaned_runs(self) -> int:
        """Runs left mid-flight by an app restart can never continue: mark them failed."""
        changed = 0
        with self._lock:
            for path in RUNS_DIR.glob("*.json"):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if data.get("status") not in STALE_ON_START:
                    continue
                data["status"] = "failed"
                data["error"] = data.get("error") or "Запуск прерван перезапуском приложения"
                data["finished_at"] = data.get("finished_at") or now_iso()
                events = list(data.get("events") or [])
                events.append(
                    {
                        "seq": len(events) + 1,
                        "ts": time.time(),
                        "type": "error",
                        "data": {"message": data["error"]},
                    }
                )
                data["events"] = events[-3000:]
                try:
                    _atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2))
                    changed += 1
                except OSError:
                    continue
        return changed

    # ------------------------------------------------------------------- misc
    def export_bytes(self, name: str, data: bytes) -> Path:
        """Store a generated export under data/outputs and return its path."""
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", name)[:80] or "export"
        from .config import OUTPUTS_DIR

        target = OUTPUTS_DIR / safe
        target.write_bytes(data)
        return target


def rmtree_quiet(path: Path) -> None:
    try:
        shutil.rmtree(path, ignore_errors=True)
    except OSError:
        pass


def as_jsonable(value: Any) -> Any:
    """Best-effort conversion of crewai objects into plain JSON data."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): as_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [as_jsonable(v) for v in value]
    for attr in ("model_dump", "to_dict", "dict"):
        fn = getattr(value, attr, None)
        if callable(fn):
            try:
                return as_jsonable(fn())
            except Exception:  # noqa: BLE001 - third-party objects vary
                continue
    return str(value)
