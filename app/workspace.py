"""Project workspace: the folder an agent team reads and writes.

Every project may point at any local directory. Tools and task output files are
confined to that folder; when nothing is configured a per-project folder under
``data/workspaces`` is used instead.
"""
from __future__ import annotations

import os
import string
import time
from pathlib import Path

from .config import DATA_DIR, ROOT

WORKSPACES_DIR = DATA_DIR / "workspaces"
WORKSPACES_DIR.mkdir(parents=True, exist_ok=True)

# A workspace must never point at OS or application internals.
FORBIDDEN_MARKERS = (
    "\\windows\\system32",
    "\\windows\\syswow64",
    "\\startup\\",
    "\\start menu\\",
    "\\.ssh\\",
    "\\site-packages\\",
    "\\node_modules\\",
    "\\appdata\\roaming\\microsoft\\windows\\start menu",
)


def assert_safe_target(path: Path) -> None:
    resolved = path.resolve()
    text = ("\\" + str(resolved).replace("/", "\\") + "\\").lower()
    for marker in FORBIDDEN_MARKERS:
        if marker in text:
            raise ValueError(f"Папка «{resolved}» служебная — выбирать её нельзя")
    for blocked in (ROOT / "app", ROOT / "web", DATA_DIR / "crews", DATA_DIR / "runs"):
        try:
            resolved.relative_to(blocked.resolve())
        except (ValueError, OSError):
            continue
        raise ValueError(f"Папка «{resolved}» зарезервирована приложением")


def default_path(crew_id: str) -> Path:
    safe = "".join(ch for ch in str(crew_id or "project") if ch.isalnum() or ch in "-_") or "project"
    return WORKSPACES_DIR / safe


def allowed_roots(extra: list[str] | None = None) -> list[Path]:
    """Directories the user may browse and pick: home, project, data, plus configured ones."""
    roots: list[Path] = []
    for candidate in [Path.home(), ROOT, DATA_DIR, *[Path(str(item).strip()).expanduser() for item in (extra or []) if str(item).strip()]]:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved not in roots:
            roots.append(resolved)
    return roots


def require_inside(path: Path, roots: list[Path]) -> Path:
    resolved = path.resolve()
    for root in roots:
        try:
            resolved.relative_to(root)
            return resolved
        except ValueError:
            continue
    joined = ", ".join(str(root) for root in roots)
    raise ValueError("Папка вне разрешённых каталогов. Добавьте нужный корень в настройках.")


def resolve(raw: str | None, crew_id: str = "") -> Path:
    """Turn a stored value into an absolute path (no filesystem changes)."""
    value = str(raw or "").strip()
    if not value:
        return default_path(crew_id)
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    return path


def ensure(path: Path) -> Path:
    """Create the folder (with parents) if needed and return it."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def authorize_or_default(
    raw: str | None, crew_id: str, roots: list[Path] | None = None
) -> tuple[Path, str]:
    """Workspace path for a run: (usable path, fallback reason).

    Imported or hand-edited project files can carry any workspace string, so the
    policy must be applied when the project is *used*, not only when it is saved.
    Never raises on user input: a rejected path falls back to the default folder.
    """
    if not str(raw or "").strip():
        return default_path(crew_id), ""
    target = resolve(raw, crew_id)
    try:
        assert_safe_target(target)
        require_inside(target, roots or allowed_roots())
    except (ValueError, OSError) as exc:
        return default_path(crew_id), f"Рабочая область «{target}» отклонена: {exc}"
    return ensure(target), ""


def for_crew(crew: dict, roots: list[Path] | None = None) -> tuple[Path, str]:
    """Resolved workspace for a crew plus a fallback note, if any."""
    return authorize_or_default(crew.get("workspace"), crew.get("id", ""), roots)


def is_default(crew: dict) -> bool:
    return not str(crew.get("workspace") or "").strip()


def check_access(path: Path) -> tuple[bool, bool]:
    """(readable, writable) proven by listing the folder and writing a probe file."""
    readable = False
    try:
        next(path.iterdir(), None)
        readable = True
    except StopIteration:
        readable = True
    except OSError:
        readable = False

    writable_now = False
    if readable:
        probe = path / f".studio-write-test-{os.getpid()}-{time.time_ns() % 100000}"
        try:
            probe.write_text("ok", encoding="utf-8")
            writable_now = True
        except OSError:
            writable_now = False
        finally:
            try:
                probe.unlink(missing_ok=True)
            except OSError:
                pass
    return readable, writable_now


def writable(path: Path) -> bool:
    """Whether the app can create files in the folder (real probe, not just a bit)."""
    return check_access(path)[1]


def drives() -> list[str]:
    """Available drive roots (Windows) or a single ``/`` elsewhere."""
    if os.name != "nt":
        return ["/"]
    roots: list[str] = []
    lister = getattr(os, "listdrives", None)
    if callable(lister):
        try:
            roots = [str(root) for root in lister()]
        except OSError:
            roots = []
    if not roots:
        for letter in string.ascii_uppercase:
            candidate = f"{letter}:\\"
            if Path(candidate).exists():
                roots.append(candidate)
    return roots


def list_directory(raw: str | None, roots: list[Path] | None = None) -> dict:
    """Read-only directory listing for the folder picker (inside allowed roots)."""
    if str(raw or "").strip():
        path = Path(str(raw)).expanduser()
        if not path.is_absolute():
            path = ROOT / path
        try:
            path = path.resolve()
        except OSError as exc:
            raise ValueError(f"Папка недоступна: {path}") from exc
    else:
        path = Path.home().resolve()

    allowed = roots or allowed_roots()
    require_inside(path, allowed)

    try:
        if not path.exists():
            raise ValueError(f"Папка не найдена: {path}")
        if not path.is_dir():
            raise ValueError(f"Это не папка: {path}")
    except OSError as exc:  # disconnected drive, access denied, ...
        raise ValueError(f"Папка недоступна: {path} ({exc.strerror or exc})") from exc

    dirs: list[dict] = []
    files: list[dict] = []
    try:
        entries = sorted(path.iterdir(), key=lambda item: item.name.lower())
    except OSError as exc:
        raise ValueError(f"Нет доступа к папке: {exc}") from exc

    for entry in entries:
        try:
            if entry.is_dir():
                dirs.append({"name": entry.name, "path": str(entry)})
            elif entry.is_file():
                files.append({"name": entry.name, "size": entry.stat().st_size})
        except OSError:
            continue

    readable, writable_now = check_access(path)
    parent = path.parent if path.parent != path else None
    return {
        "path": str(path),
        "name": path.name or str(path),
        "parent": str(parent) if parent else "",
        "dirs": dirs[:400],
        "files": files[:200],
        "drives": drives(),
        "roots": [str(root) for root in allowed],
        "home": str(Path.home()),
        "readable": readable,
        "writable": writable_now,
    }


def make_directory(parent: str, name: str, roots: list[Path] | None = None) -> str:
    clean = str(name or "").strip()
    if not clean or any(sep in clean for sep in ("/", "\\")) or clean in {".", ".."}:
        raise ValueError("Некорректное имя папки")
    base = Path(str(parent or "")).expanduser()
    if not base.is_absolute():
        base = ROOT / base
    require_inside(base, roots or allowed_roots())
    assert_safe_target(base)
    target = base / clean
    if target.exists():
        raise ValueError("Такая папка уже существует")
    try:
        target.mkdir(parents=True)
    except OSError as exc:
        reason = getattr(exc, "strerror", None) or str(exc)
        raise ValueError(
            f"Не удалось создать папку в {base}: {reason}. "
            "Выберите папку, куда разрешена запись, или измените права Windows."
        ) from exc
    return str(target)


def describe(crew: dict, roots: list[Path] | None = None) -> dict:
    """Workspace info for the UI: resolved path, whether it is the default, file count."""
    path, note = authorize_or_default(crew.get("workspace"), crew.get("id", ""), roots)
    exists = False
    is_dir = False
    count = 0
    try:
        exists = path.exists()
        is_dir = path.is_dir() if exists else False
        if is_dir:
            count = sum(1 for _ in path.iterdir())
    except OSError:
        exists, is_dir, count = False, False, 0
    readable, writable_now = check_access(path) if exists and is_dir else (False, False)
    return {
        "path": str(path),
        "note": note,
        "rejected": bool(note),
        "raw": str(crew.get("workspace") or ""),
        "is_default": is_default(crew),
        "exists": exists,
        "is_dir": is_dir,
        "readable": readable,
        "writable": writable_now,
        "files": count,
    }
