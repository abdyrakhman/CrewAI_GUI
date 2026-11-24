"""Tool catalogue: safe built-ins plus whatever ``crewai_tools`` provides."""
from __future__ import annotations

import importlib
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from pathlib import Path
from typing import Any

from .config import DATA_DIR, OUTPUTS_DIR, UPLOADS_DIR
from . import security


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    """Follow at most three redirects, each re-checked against the SSRF policy."""

    max_redirections = 3

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102
        security.check_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)

# name -> (label, description, requires env var)
BUILTIN_META: dict[str, tuple[str, str, str]] = {
    "read_local_file": (
        "Прочитать файл",
        "Читает текстовый файл из рабочей папки проекта.",
        "",
    ),
    "write_local_file": (
        "Записать файл",
        "Сохраняет текст в файл внутри рабочей папки проекта.",
        "",
    ),
    "list_local_files": (
        "Список файлов",
        "Показывает файлы в рабочей папке проекта.",
        "",
    ),
    "fetch_url": (
        "Загрузить страницу",
        "Скачивает содержимое веб-страницы по URL и возвращает текст без HTML-разметки.",
        "",
    ),
    "current_datetime": (
        "Дата и время",
        "Возвращает текущую дату и время — полезно для отчётов и планов.",
        "",
    ),
}

# crewai_tools classes worth exposing, with Russian labels and required env vars.
OPTIONAL_META: dict[str, tuple[str, str, str]] = {
    "SerperDevTool": ("Веб-поиск (Serper)", "Поиск в Google через serper.dev.", "SERPER_API_KEY"),
    "ScrapeWebsiteTool": ("Скрейпинг сайта", "Извлекает содержимое веб-страницы.", ""),
    "WebsiteSearchTool": ("Поиск по сайту", "RAG-поиск по содержимому сайта.", ""),
    "CodeDocsSearchTool": ("Поиск по документации", "RAG-поиск по документации репозитория.", ""),
    "GithubSearchTool": ("Поиск по GitHub", "Поиск по коду GitHub-репозитория.", ""),
    "YoutubeChannelSearchTool": ("Поиск по YouTube", "RAG-поиск по транскриптам канала.", ""),
    "YoutubeVideoSearchTool": ("Поиск по видео", "RAG-поиск по транскрипту видео.", ""),
    "EXASearchTool": ("EXA поиск", "Поиск через exa.ai.", "EXA_API_KEY"),
    "BrowserbaseLoadTool": ("Browserbase", "Загрузка страниц через Browserbase.", "BROWSERBASE_API_KEY"),
}

# Third-party tools that talk to the network (and read files) with their own code:
# they cannot be confined by our policy, so they are opt-in and clearly labelled.
NETWORK_TOOL_NAMES = frozenset(OPTIONAL_META)

# File/RAG tools from crewai-tools were removed: they read arbitrary paths with
# their own implementation, bypassing both the workspace and access prompts.
REMOVED_TOOLS = {
    "FileReadTool": "используйте встроенный «Прочитать файл» — он ограничен рабочей областью",
    "FileWriterTool": "используйте встроенный «Записать файл» — он спрашивает подтверждение",
    "DirectoryReadTool": "используйте встроенный «Список файлов»",
    "CSVSearchTool": "RAG-инструменты читают файлы в обход песочницы",
    "JSONSearchTool": "RAG-инструменты читают файлы в обход песочницы",
    "PDFSearchTool": "RAG-инструменты читают файлы в обход песочницы",
    "TXTSearchTool": "RAG-инструменты читают файлы в обход песочницы",
    "MDXSearchTool": "RAG-инструменты читают файлы в обход песочницы",
}


# Tools that build a vector index: they need an embeddings provider.
RAG_TOOL_NAMES = frozenset(
    {
        "CodeDocsSearchTool",
        "WebsiteSearchTool",
        "YoutubeChannelSearchTool",
        "YoutubeVideoSearchTool",
        "GithubSearchTool",
    }
)


def _within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (ValueError, OSError):
        return False


def _absolute(raw: str, base: Path) -> Path:
    candidate = Path(str(raw or "").strip()).expanduser()
    if not candidate.is_absolute():
        candidate = base / candidate
    try:
        return candidate.resolve()
    except OSError:
        return candidate.absolute()


def _ask(
    run_state: Any,
    kind: str,
    target: str,
    reason: str,
    agent: str,
    grant: str = "file",
    base: str | None = None,
) -> tuple[bool, str]:
    """Ask the user for access through the run that owns this tool instance.

    Service directories (Startup, site-packages, .ssh, app internals) are refused
    without a dialog: consent there is worth less than the risk of a typo.
    """
    from .workspace import assert_safe_target

    if run_state is None or getattr(run_state, "abandoned", False):
        return False, "Запуск не активен: подтверждение недоступно"
    try:
        assert_safe_target(Path(str(target)))
    except (ValueError, OSError) as exc:
        return False, f"Служебный каталог: {exc}"
    return run_state.ask_permission(
        kind=kind, target=str(target), reason=reason, agent=agent, grant=grant, base=base
    )


def _safe_path(raw: str, roots: tuple[Path, ...], label: str = "рабочей папки проекта") -> Path:
    candidate = Path(str(raw or "").strip()).expanduser()
    if not candidate.is_absolute():
        candidate = roots[0] / candidate
    resolved = candidate.resolve()
    for root in roots:
        try:
            resolved.relative_to(root.resolve())
            return resolved
        except ValueError:
            continue
    allowed = ", ".join(str(root) for root in roots)
    raise ValueError(f"Путь вне {label}. Разрешено внутри: {allowed} (получено: {raw})")


def _strip_html(html: str) -> str:
    import re

    text = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&quot;", '"', text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return text.strip()


def build_builtin(
    name: str,
    workspace: Path | None = None,
    confirm_writes: bool = False,
    agent: str = "",
    run_state: Any = None,
) -> Any:
    """Create a CrewAI tool object for one of the built-in tools.

    File tools stay inside the project workspace. When an agent tries to reach
    beyond it, the tool asks the user for access and waits for the answer.
    With ``confirm_writes`` every write is confirmed first.
    """
    from .crewai_env import configure as configure_crewai
    from .crewai_env import import_lock

    configure_crewai()
    with import_lock():
        from crewai.tools import tool

    workspace_root = Path(workspace) if workspace else None
    read_roots: tuple[Path, ...] = (workspace_root,) if workspace_root else (UPLOADS_DIR, OUTPUTS_DIR)
    write_root: Path = workspace_root or OUTPUTS_DIR

    if name == "read_local_file":

        @tool("read_local_file")
        def read_local_file(path: str) -> str:
            """Прочитать текстовый файл из рабочей папки проекта. Аргумент path — путь или имя файла."""
            try:
                target = _safe_path(path, read_roots)
            except ValueError:
                candidate = _absolute(path, read_roots[0])
                allowed, note = _ask(run_state, "fs_read", str(candidate), "Чтение файла вне рабочей области", agent)
                if not allowed:
                    return f"Доступ к файлу не разрешён: {note}"
                target = candidate
            if not target.exists():
                return f"Файл не найден: {target}"
            if target.stat().st_size > 2_000_000:
                return "Файл слишком большой (>2 МБ), чтение отменено."
            try:
                return target.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                return f"Ошибка чтения: {exc}"

        return read_local_file

    if name == "write_local_file":

        @tool("write_local_file")
        def write_local_file(filename: str, content: str) -> str:
            """Сохранить текст в файл внутри рабочей папки проекта. Аргументы: filename — имя файла, content — содержимое."""
            raw = Path(str(filename or "").strip()).expanduser()
            if not raw.name:
                return "Некорректное имя файла."
            if getattr(run_state, "abandoned", False):
                return "Запуск отсоединён: запись отменена"
            if raw.is_absolute():
                target = raw
                outside = not _within(target, write_root)
            else:
                target = write_root / raw.name
                outside = False
            if outside:
                allowed, note = _ask(run_state, "fs_write", str(target), "Запись файла вне рабочей области", agent)
                if not allowed:
                    return f"Запись не разрешена: {note}"
            elif confirm_writes:
                allowed, note = _ask(
                    run_state, "fs_write", str(target), "Агент хочет изменить файл", agent, "folder",
                    base=str(target.parent),
                )
                if not allowed:
                    return f"Запись не подтверждена: {note}"
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                target.write_text(content, encoding="utf-8")
                return f"Файл сохранён: {target}"
            except OSError as exc:
                return f"Ошибка записи: {exc}"

        return write_local_file

    if name == "list_local_files":

        @tool("list_local_files")
        def list_local_files(folder: str = "") -> str:
            """Показать файлы в рабочей папке проекта. Аргумент folder — необязательная подпапка."""
            lines: list[str] = []
            for root in read_roots:
                if folder:
                    try:
                        base = _safe_path(folder, (root,))
                    except ValueError:
                        candidate = _absolute(folder, root)
                        allowed, note = _ask(
                            run_state, "fs_read", str(candidate), "Просмотр папки вне рабочей области", agent,
                            "folder", base=str(candidate),
                        )
                        if not allowed:
                            return f"Доступ к папке не разрешён: {note}"
                        base = candidate
                else:
                    base = root
                if not base.exists():
                    continue
                lines.append(f"[{base}]")
                for item in sorted(base.iterdir()):
                    if item.is_file():
                        lines.append(f"  {item.name} ({item.stat().st_size} байт)")
                    else:
                        lines.append(f"  {item.name}/")
            return "\n".join(lines) or "Файлов нет."

        return list_local_files

    if name == "fetch_url":

        @tool("fetch_url")
        def fetch_url(url: str) -> str:
            """Скачать веб-страницу по URL и вернуть её текст без HTML-разметки. Аргумент url — полный адрес http(s)."""
            url = str(url or "").strip()
            if getattr(run_state, "abandoned", False):
                return "Запуск отсоединён: сетевой запрос отменён"
            if not url.lower().startswith(("http://", "https://")):
                return "Нужен полный URL, начинающийся с http:// или https://"
            try:
                security.check_url(url)
            except ValueError as exc:
                return f"Запрос заблокирован: {exc}"
            opener = urllib.request.build_opener(_SafeRedirect)
            request = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (CrewAI Studio)"},
            )
            try:
                with opener.open(request, timeout=20) as response:
                    raw = response.read(1_500_000)
                    charset = response.headers.get_content_charset() or "utf-8"
                text = raw.decode(charset, errors="replace")
            except (urllib.error.URLError, OSError, ValueError) as exc:
                return f"Не удалось загрузить {url}: {exc}"
            body = _strip_html(text)
            return body[:60_000] if body else "Страница пустая."

        return fetch_url

    if name == "current_datetime":

        @tool("current_datetime")
        def current_datetime(format: str = "%Y-%m-%d %H:%M:%S") -> str:
            """Вернуть текущие дату и время. Аргумент format — необязательный strftime-формат."""
            fmt = format or "%Y-%m-%d %H:%M:%S"
            try:
                return time.strftime(fmt)
            except ValueError:
                return time.strftime("%Y-%m-%d %H:%M:%S")

        return current_datetime

    raise KeyError(name)


def optional_tools_available() -> dict[str, bool]:
    from . import crewai_env

    try:
        crewai_env.configure()
        with crewai_env.import_lock():
            importlib.invalidate_caches()
            module = importlib.import_module("crewai_tools")
    except Exception:  # noqa: BLE001 - optional dependency
        return {name: False for name in OPTIONAL_META}
    return {name: hasattr(module, name) for name in OPTIONAL_META}


def allowed_network_names(value: Any) -> set[str]:
    """Network tools the user opted into; accepts the legacy boolean as "all"."""
    if value is True:
        return set(NETWORK_TOOL_NAMES)
    if isinstance(value, (list, tuple, set, frozenset)):
        return {str(item) for item in value if str(item) in NETWORK_TOOL_NAMES}
    return set()


def _url_arguments(args: tuple, kwargs: dict) -> list[str]:
    found: list[str] = []
    for value in list(args) + list(kwargs.values()):
        if isinstance(value, str) and value.strip().lower().startswith(("http://", "https://")):
            found.append(value.strip())
    return found


def guard_network_tool(tool_obj: Any, name: str, run_state: Any) -> Any:
    """Mandatory wrapper: URL policy, abandoned check and an egress prompt per host."""
    original = getattr(tool_obj, "_run", None)
    if original is None or getattr(original, "_studio_guarded", False):
        return tool_obj

    def guarded(*args: Any, **kwargs: Any) -> Any:
        if getattr(run_state, "abandoned", False):
            return "Запуск отсоединён: сетевой запрос отменён"
        urls = _url_arguments(args, kwargs)
        hosts: list[str] = []
        for url in urls:
            try:
                security.check_url(url)
            except ValueError as exc:
                return f"Сетевой запрос заблокирован: {exc}"
            hosts.append(urllib.parse.urlparse(url).netloc)
        if not hosts:
            hosts = [f"{name} (внешний сервис)"]
        for host in hosts:
            if run_state is not None:
                allowed, note = run_state.ask_permission(
                    "net_egress",
                    host,
                    f"Инструмент «{name}» хочет обратиться в сеть",
                    agent=name,
                    timeout=300,
                )
                if not allowed:
                    return f"Сетевой запрос не разрешён: {note}"
                run_state.emit("tool_network", {"tool": name, "host": host})
        return original(*args, **kwargs)

    guarded._studio_guarded = True  # type: ignore[attr-defined]
    try:
        tool_obj._run = guarded
    except (AttributeError, ValueError):
        return tool_obj
    return tool_obj


def build_optional(name: str, env: dict[str, str], allow_network: bool = False, run_state: Any = None) -> Any:
    from .crewai_env import configure as configure_crewai
    from .crewai_env import import_lock

    if name in NETWORK_TOOL_NAMES and not allow_network:
        raise RuntimeError(
            "Сетевые инструменты сторонних разработчиков выключены: их запросы идут в обход политики доступа. "
            "Включите «Сетевые инструменты третьих сторон» в настройках, если это осознанное решение."
        )
    configure_crewai()
    with import_lock():
        module = importlib.import_module("crewai_tools")
    cls = getattr(module, name)
    required = OPTIONAL_META.get(name, ("", "", ""))[2]
    if required and not env.get(required):
        raise RuntimeError(f"Для инструмента {name} нужен {required}")
    try:
        instance = cls()
    except TypeError:
        instance = cls()
    return guard_network_tool(instance, name, run_state)


def catalogue(allowed: set[str] | None = None) -> list[dict]:
    """Everything the GUI should offer in the tool picker.

    Third-party tools are opt-in: their implementation is outside our sandbox,
    so they are listed as unavailable until the user enables them explicitly.
    """
    available_optional = optional_tools_available()
    items: list[dict] = []
    for name, (label, description, env) in BUILTIN_META.items():
        items.append(
            {
                "name": name,
                "label": label,
                "description": description,
                "requires_env": env,
                "available": True,
                "source": "builtin",
                "policy": "sandboxed",
            }
        )
    for name, (label, description, env) in OPTIONAL_META.items():
        installed = bool(available_optional.get(name))
        items.append(
            {
                "name": name,
                "label": label,
                "description": description,
                "requires_env": env,
                "available": installed and (allowed is None or name in allowed),
                "installed": installed,
                "source": "crewai-tools",
                "policy": "third-party-network",
                "warning": "Сторонний инструмент: работает вне песочницы приложения и обращается в сеть.",
            }
        )
    return items


def build_tool(
    name: str,
    env: dict[str, str],
    workspace: Path | None = None,
    confirm_writes: bool = False,
    agent: str = "",
    run_state: Any = None,
    allow_network: bool = False,
) -> Any:
    if name in BUILTIN_META:
        return build_builtin(name, workspace, confirm_writes, agent, run_state)
    if name in REMOVED_TOOLS:
        raise RuntimeError(f"Инструмент {name} отключён: {REMOVED_TOOLS[name]}")
    if name in OPTIONAL_META:
        return build_optional(name, env, allow_network, run_state)
    raise KeyError(f"Неизвестный инструмент: {name}")


def ensure_dirs() -> None:
    for path in (UPLOADS_DIR, OUTPUTS_DIR):
        path.mkdir(parents=True, exist_ok=True)


def _file_entries(root: Path) -> list[dict]:
    files: list[dict] = []
    if not root.exists():
        return files
    for item in sorted(root.rglob("*")):
        try:
            if item.is_file():
                files.append(
                    {
                        "name": item.name,
                        "path": str(item.relative_to(root)).replace("\\", "/"),
                        "size": item.stat().st_size,
                        "modified": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(item.stat().st_mtime)),
                    }
                )
        except OSError:
            continue
    return files[:500]


def tool_files_listing(workspace: Path | None = None) -> dict[str, Any]:
    ensure_dirs()
    payload: dict[str, Any] = {
        "uploads": _file_entries(UPLOADS_DIR),
        "outputs": _file_entries(OUTPUTS_DIR),
    }
    if workspace is not None:
        payload["workspace"] = {
            "path": str(workspace),
            "files": _file_entries(workspace),
        }
    return payload


def save_upload(filename: str, data: bytes, directory: Path | None = None) -> str:
    ensure_dirs()
    target_dir = directory or UPLOADS_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    safe = Path(filename).name or f"upload-{int(time.time())}.txt"
    target = target_dir / safe
    target.write_bytes(data)
    return str(target)


def read_output_file(relative: str, workspace: Path | None = None) -> str:
    roots: tuple[Path, ...] = (workspace, OUTPUTS_DIR) if workspace else (OUTPUTS_DIR,)
    target = _safe_path(relative, roots)
    if not target.exists():
        return ""
    return target.read_text(encoding="utf-8", errors="replace")


def env_preview(env: dict[str, str]) -> dict[str, bool]:
    keys = ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "OPENROUTER_API_KEY",
            "GROQ_API_KEY", "DEEPSEEK_API_KEY", "SERPER_API_KEY"]
    return {key: bool(env.get(key)) for key in keys}

# ------------------------------------------------------- optional extras install
def install_target() -> str:
    """Pin the extras package to the installed CrewAI version."""
    try:
        from .crewai_env import configure as configure_crewai

        configure_crewai()
        import crewai

        version = str(getattr(crewai, "__version__", "") or "").strip()
    except Exception:  # noqa: BLE001
        version = ""
    return f"crewai-tools=={version}" if version else "crewai-tools>=1.15,<2"


INSTALL_COMMAND: list[str] = [
    sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
]
PIP_TMP = DATA_DIR / "tmp"
PIP_CACHE = PIP_TMP / "pip-cache"

_install_lock = threading.Lock()
_install_output: deque[str] = deque(maxlen=400)
_install_state: dict[str, Any] = {"running": False, "ok": None, "started": 0.0, "finished": 0.0, "error": ""}


def install_env() -> dict[str, str]:
    """Environment for pip: its own temp and cache, writable even in restricted setups."""
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith(("PIP_", "PYTHONPATH", "PYTHONHOME", "LD_", "DYLD_", "SSL_"))
        and key.upper() not in {"REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE", "PYTHONSTARTUP", "NODE_OPTIONS"}
    }
    try:
        PIP_TMP.mkdir(parents=True, exist_ok=True)
        PIP_CACHE.mkdir(parents=True, exist_ok=True)
        env.update(
            {
                "TMP": str(PIP_TMP),
                "TEMP": str(PIP_TMP),
                "TMPDIR": str(PIP_TMP),
                "PIP_CACHE_DIR": str(PIP_CACHE),
            }
        )
    except OSError:
        pass
    env.update(
        {
            "PIP_DISABLE_PIP_VERSION_CHECK": "1",
            "PIP_NO_INPUT": "1",
            "PIP_PROGRESS_BAR": "off",
            "PYTHONIOENCODING": "utf-8",
        }
    )
    return env


def _install_command() -> list[str]:
    base = list(INSTALL_COMMAND)
    if len(base) > 1 and base[1] == "-m":
        return [*base, install_target()]
    return base


def install_status() -> dict[str, Any]:
    with _install_lock:
        end = _install_state["finished"] or time.time()
        start = _install_state["started"]
        return {
            "running": bool(_install_state["running"]),
            "ok": _install_state["ok"],
            "output": "\n".join(_install_output),
            "seconds": round(end - start, 1) if start else 0,
            "error": _install_state["error"],
            "target": install_target(),
        }


def install_extras() -> bool:
    """Start ``pip install crewai-tools`` in the background. False if already running."""
    with _install_lock:
        if _install_state["running"]:
            return False
        _install_state.update({"running": True, "ok": None, "started": time.time(), "finished": 0.0, "error": ""})
        _install_output.clear()
    threading.Thread(target=_run_install, name="pip-install-extras", daemon=True).start()
    return True


def _run_install() -> None:
    code = -1
    try:
        process = subprocess.Popen(
            _install_command(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=install_env(),
        )
        if process.stdout is not None:
            for line in process.stdout:
                text = line.rstrip()
                if text:
                    with _install_lock:
                        _install_output.append(text)
        code = process.wait()
    except Exception as exc:  # noqa: BLE001 - surface the reason to the UI
        with _install_lock:
            _install_state["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        importlib.invalidate_caches()
        with _install_lock:
            _install_state["running"] = False
            _install_state["ok"] = code == 0
            _install_state["finished"] = time.time()
