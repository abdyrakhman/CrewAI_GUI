"""Keep CrewAI's own storage inside the project and make its imports safe.

CrewAI 1.x resolves per-user directories at import time (``%LOCALAPPDATA%\\CrewAI``,
``~/.local/share``) and aborts when it cannot create them — which happens inside
sandboxes, on locked-down profiles, or on read-only network drives. Redirecting
everything into ``data/crewai_home`` keeps the app portable and self-contained.
"""
from __future__ import annotations

import os
import re
import threading
from pathlib import Path

from .config import DATA_DIR

_HOME = DATA_DIR / "crewai_home"
_lock = threading.Lock()
_import_lock = threading.RLock()
_configured = False


def import_lock() -> threading.RLock:
    """Serialise the first ``import crewai`` — concurrent imports can fail midway."""
    return _import_lock


def crewai_home() -> Path:
    _HOME.mkdir(parents=True, exist_ok=True)
    return _HOME


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", str(value)) or "app"


def _patch_appdirs(home: Path) -> None:
    try:
        import appdirs
    except Exception:  # noqa: BLE001 - not installed, nothing to patch
        return

    def redirect(name: str, leaf: str) -> Path:
        target = home / leaf / _safe_name(name)
        target.mkdir(parents=True, exist_ok=True)
        return target

    for function_name, leaf in (
        ("user_data_dir", "appdata"),
        ("user_cache_dir", "cache"),
        ("user_log_dir", "logs"),
        ("site_data_dir", "appdata"),
    ):
        original = getattr(appdirs, function_name, None)
        if original is None:
            continue

        def make(original_fn=original, leaf_name=leaf):
            def wrapper(appname=None, appauthor=None, version=None, *args, **kwargs):
                if appname and "crewai" in str(appname).lower():
                    return str(redirect(str(appname), leaf_name))
                return original_fn(appname, appauthor, version, *args, **kwargs)

            return wrapper

        setattr(appdirs, function_name, make())


def _patch_token_manager(home: Path) -> None:
    try:
        import crewai_core.token_manager as token_manager
    except Exception:  # noqa: BLE001
        return

    def storage_path() -> Path:
        target = home / "credentials"
        target.mkdir(parents=True, exist_ok=True)
        return target

    token_manager.TokenManager._get_secure_storage_path = staticmethod(storage_path)  # type: ignore[method-assign]


def _patch_core_paths(home: Path) -> None:
    try:
        import crewai_core.paths as paths
    except Exception:  # noqa: BLE001
        return

    def db_storage_path() -> str:
        home.mkdir(parents=True, exist_ok=True)
        return str(home)

    paths.db_storage_path = db_storage_path  # type: ignore[assignment]
    for module_name in ("crewai_core.user_data", "crewai_core.lock_store"):
        try:
            module = __import__(module_name, fromlist=["db_storage_path"])
            if hasattr(module, "db_storage_path"):
                module.db_storage_path = db_storage_path  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            continue


def configure() -> Path:
    """Redirect CrewAI storage. Safe to call repeatedly, and without crewai installed."""
    global _configured
    with _lock:
        home = crewai_home()
        if _configured:
            return home
        # Memory/vector stores honour this variable; keep them inside the project
        # instead of creating a relative "studio/memory" folder in the CWD.
        storage_dir = home / "storage"
        storage_dir.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("CREWAI_STORAGE_DIR", str(storage_dir))
        # No outbound tracing: the studio is a local tool and the network may be closed.
        os.environ.setdefault("CREWAI_TRACING_ENABLED", "false")
        os.environ.setdefault("OTEL_SDK_DISABLED", "true")
        _patch_appdirs(home)
        _patch_core_paths(home)
        _patch_token_manager(home)
        _configured = True
        return home
