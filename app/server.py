"""HTTP server for CrewAI Studio: REST API, server-sent events and static UI."""
from __future__ import annotations

import base64
import hmac
import json
import mimetypes
import os
import re
import secrets
import socket
import sys
import threading
import time
import traceback
import urllib.parse
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from . import config, observability, roles, security, templates, tools as tool_registry, workspace
from .runner import BusyError, RunManager, crewai_status, stream_lines
from .spec import inputs_payload, normalize_crew, resolve_llm, to_python, validate_crew
from .store import Store, as_jsonable

STATIC_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".json": "application/json; charset=utf-8",
    ".woff2": "font/woff2",
}


def _export_markdown(run: dict, crew: dict) -> str:
    result = run.get("result") or {}
    lines = [
        f"# {run.get('crew_name') or 'Crew'}",
        "",
        f"- **Статус:** {run.get('status')}",
        f"- **Модель:** {run.get('model') or crew.get('default_llm') or 'по умолчанию'}",
        f"- **Начало:** {run.get('started_at')}",
        f"- **Длительность:** {run.get('duration')} с",
    ]
    usage = result.get("token_usage") or {}
    if usage:
        lines.append(f"- **Токены:** всего {usage.get('total_tokens', 0)}, "
                     f"prompt {usage.get('prompt_tokens', 0)}, completion {usage.get('completion_tokens', 0)}")
    if run.get("inputs"):
        lines += ["", "## Входные данные", ""]
        for key, value in run["inputs"].items():
            lines.append(f"- **{key}:** {value}")
    lines += ["", "## Результат", "", result.get("raw") or run.get("error") or "(пусто)"]
    tasks = result.get("tasks") or []
    if tasks:
        lines += ["", "## По задачам", ""]
        for index, task in enumerate(tasks, start=1):
            lines.append(f"### {index}. {task.get('name') or task.get('description', '')[:60]}")
            lines.append("")
            lines.append(f"*Агент:* {task.get('agent') or '—'}")
            lines.append("")
            lines.append(task.get("output") or "")
            lines.append("")
    lines += ["", "---", "", "Сгенерировано в CrewAI Studio"]
    return "\n".join(lines)


class StudioHandler(BaseHTTPRequestHandler):
    server_version = f"CrewAI-Studio/{config.APP_VERSION}"
    protocol_version = "HTTP/1.1"
    timeout = 20  # socketserver closes idle connections; stops slowloris holding threads

    # injected by the factory below
    store: Store
    manager: RunManager
    session_token: str = ""
    allowed_hosts: set[str] = set()

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003 - stdlib signature
        if os.environ.get("CREWAI_STUDIO_VERBOSE"):
            sys.stderr.write("[studio] " + (fmt % args) + "\n")

    # ------------------------------------------------------------- perimeter
    def _deny(self, status: int, message: str) -> None:
        self._send_json(status, {"error": message})

    def _check_perimeter(self, method: str) -> bool:
        """Host/Origin/token/Content-Type checks: the browser is the attack transport."""
        if self.headers.get("Transfer-Encoding"):
            self._deny(411, "Chunked-запросы не поддерживаются: укажите Content-Length")
            return False
        host = (self.headers.get("Host") or "").strip().lower()
        if not host or host not in self.allowed_hosts:
            self._deny(403, "Неверный заголовок Host")
            return False
        origin = self.headers.get("Origin")
        if origin:
            netloc = urllib.parse.urlparse(origin).netloc.lower()
            if netloc not in self.allowed_hosts:
                self._deny(403, "Неверный Origin")
                return False
        if method in {"POST", "PUT", "PATCH", "DELETE"}:
            token = self.headers.get("X-Studio-Token") or ""
            if not self.session_token or not hmac.compare_digest(token, self.session_token):
                self._deny(403, "Нет или неверный токен сессии")
                return False
            length_text = self.headers.get("Content-Length") or "0"
            try:
                length = int(length_text)
            except ValueError:
                self._deny(400, "Некорректный Content-Length")
                return False
            if length > security.MAX_BODY:
                self._deny(413, "Тело запроса слишком велико")
                return False
            ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if length and ctype != "application/json":
                self._deny(415, "Ожидался Content-Type: application/json")
                return False
        return True

    # ------------------------------------------------------------- utilities
    def _send_json(self, status: int, payload: Any) -> None:
        self._last_status = status
        body = json.dumps(as_jsonable(payload), ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        for header, value in security.SECURITY_HEADERS.items():
            self.send_header(header, value)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        request_id = getattr(self, "request_id", "")
        if request_id:
            self.send_header("X-Request-Id", request_id)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _error(self, status: int, message: str, **extra: Any) -> None:
        self._send_json(status, {"error": message, **extra})

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length > security.MAX_BODY:
            raise ValueError("Тело запроса слишком велико")
        if not length:
            return {}
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"Некорректный JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError("Ожидался JSON-объект")
        return data

    def _serve_file(self, path: Path, *, inject_token: bool = False) -> None:
        if not path.exists() or not path.is_file():
            self._error(404, "Файл не найден")
            return
        suffix = path.suffix.lower()
        ctype = STATIC_TYPES.get(suffix) or mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        data = path.read_bytes()
        if inject_token and suffix == ".html":
            data = data.replace(b"__STUDIO_TOKEN__", self.session_token.encode("ascii"))
        self.send_response(200)
        for header, value in security.SECURITY_HEADERS.items():
            self.send_header(header, value)
        if suffix == ".html":
            self.send_header("Content-Security-Policy", security.HTML_CSP)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _serve_web(self, relative: str) -> None:
        """Only files inside ``web/``; traversal attempts are rejected outright."""
        try:
            target = security.web_path(relative, config.WEB_DIR)
        except security.PathEscape:
            self._error(403, "Доступ запрещён")
            return
        self._serve_file(target, inject_token=target.name == "index.html")

    # ----------------------------------------------------------------- routes
    def do_GET(self) -> None:  # noqa: N802
        self._dispatch("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch("POST")

    def do_PUT(self) -> None:  # noqa: N802
        self._dispatch("PUT")

    def do_DELETE(self) -> None:  # noqa: N802
        self._dispatch("DELETE")

    def do_OPTIONS(self) -> None:  # noqa: N802
        # No CORS headers: the UI is same-origin, cross-site callers get nothing.
        if not self._check_perimeter("OPTIONS"):
            return
        self.send_response(204)
        self.send_header("Allow", "GET, POST, PUT, DELETE")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _dispatch(self, method: str) -> None:
        self.request_id = uuid.uuid4().hex[:12]
        started = time.time()
        parsed = urllib.parse.urlparse(self.path)
        # Route on the raw path: decoding first would turn %2f into a real separator.
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)
        if not self._check_perimeter(method):
            observability.log_request(method, path, 403, self.request_id, started)
            return
        try:
            if method == "GET" and not path.startswith("/api/"):
                relative = path.lstrip("/")
                if relative.startswith("static/"):
                    relative = relative[len("static/"):]
                self._serve_web(urllib.parse.unquote(relative))
                return
            if self._handle_api(method, path, query):
                return
            self._error(404, "Не найдено")
        except ValueError as exc:
            self._error(400, str(exc))
        except KeyError as exc:
            self._error(404, str(exc).strip("'"))
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception as exc:  # noqa: BLE001 - never leak internals to the client
            error_id = observability.log_error(exc, self.request_id, method, path)
            self._error(500, "Внутренняя ошибка сервера", error_id=error_id)
        finally:
            if method in {"POST", "PUT", "PATCH", "DELETE"}:
                observability.log_request(method, path, getattr(self, "_last_status", 0), self.request_id, started)

    def _handle_api(self, method: str, path: str, query: dict[str, list[str]]) -> bool:
        store, manager = self.store, self.manager
        network_allowed = tool_registry.allowed_network_names(store.get_settings().get("allow_network_tools"))

        if method == "GET" and path == "/api/info":
            settings = store.public_settings()
            self._send_json(
                200,
                {
                    "app": config.APP_NAME,
                    "version": config.APP_VERSION,
                    "crewai": crewai_status(),
                    "settings": settings,
                    "providers": config.PROVIDERS,
                    "default_llm": settings.get("default_llm") or "",
                },
            )
            return True

        if method == "GET" and path == "/api/status":
            settings = store.get_settings()
            env = store.effective_env()
            self._send_json(
                200,
                {
                    "crewai": crewai_status(),
                    "env": tool_registry.env_preview(env),
                    "busy": manager.is_busy(),
                    "active_run": manager.active_id(),
                },
            )
            return True

        if method == "GET" and path == "/api/tools":
            self._send_json(200, {"tools": tool_registry.catalogue(network_allowed)})
            return True

        if path == "/api/tools/install":
            if method == "GET":
                self._send_json(200, tool_registry.install_status())
                return True
            if method == "POST":
                self._read_json()  # drain the body: keep-alive needs it consumed
                started = tool_registry.install_extras()
                self._send_json(202 if started else 409, {"started": started, "status": tool_registry.install_status()})
                return True

        if method == "GET" and path == "/api/files":
            crew_id = (query.get("crew_id") or [""])[0]
            crew = store.get_crew(crew_id) if crew_id else None
            ws = None
            if crew is not None:
                ws, _ = workspace.for_crew(crew, workspace.allowed_roots(store.get_settings().get("fs_roots") or []))
            payload = tool_registry.tool_files_listing(ws)
            if crew is not None:
                payload["crew_id"] = crew.get("id", "")
                payload["workspace"] = {"path": str(ws) if ws else "", "files": payload.get("workspace", {}).get("files", [])}
            self._send_json(200, payload)
            return True

        if method == "GET" and path.startswith("/api/files/output/"):
            name = path[len("/api/files/output/"):]
            crew_id = (query.get("crew_id") or [""])[0]
            crew = store.get_crew(crew_id) if crew_id else None
            ws = None
            if crew is not None:
                ws, _ = workspace.for_crew(crew, workspace.allowed_roots(store.get_settings().get("fs_roots") or []))
            content = tool_registry.read_output_file(name, ws)
            self._send_json(200, {"name": name, "content": content})
            return True

        if method == "POST" and path == "/api/files":
            payload = self._read_json()
            raw = str(payload.get("data") or "")
            if "," in raw and raw.startswith("data:"):
                raw = raw.split(",", 1)[1]
            try:
                data = base64.b64decode(raw, validate=False)
            except Exception as exc:  # noqa: BLE001
                raise ValueError(f"Не удалось декодировать файл: {exc}") from exc
            target_dir = None
            crew_id = str(payload.get("crew_id") or "")
            if crew_id:
                crew = store.get_crew(crew_id)
                if crew is not None:
                    target_dir, note = workspace.for_crew(
                        crew, workspace.allowed_roots(store.get_settings().get("fs_roots") or [])
                    )
                    if note:
                        self._error(400, "Рабочая область проекта отклонена политикой")
                        return True
            target = tool_registry.save_upload(str(payload.get("name") or "upload.txt"), data, target_dir)
            self._send_json(200, {"ok": True, "path": target, "in_workspace": target_dir is not None})
            return True

        # ------------------------------------------------------------ filesystem
        if method == "GET" and path == "/api/fs":
            target = (query.get("path") or [""])[0]
            roots = workspace.allowed_roots((store.get_settings().get("fs_roots") or []))
            self._send_json(200, workspace.list_directory(target, roots))
            return True

        if method == "POST" and path == "/api/fs/mkdir":
            payload = self._read_json()
            roots = workspace.allowed_roots((store.get_settings().get("fs_roots") or []))
            created = workspace.make_directory(
                str(payload.get("parent") or ""), str(payload.get("name") or ""), roots
            )
            self._send_json(201, {"path": created})
            return True

        # ------------------------------------------------------------- crews
        if path == "/api/crews" and method == "GET":
            crews = store.list_crews()
            self._send_json(200, {"crews": crews, "broken": list(store.broken_crews)})
            return True

        if path == "/api/crews" and method == "POST":
            payload = self._read_json()
            template_key = payload.get("template")
            if template_key:
                crew = normalize_crew(templates.build_template(str(template_key)))
            else:
                rejected: list[dict] = []
                crew = normalize_crew(payload.get("crew") or {}, rejected)
            saved = store.save_crew(crew)
            self._send_json(201, {"crew": saved, "rejected": locals().get("rejected", [])})
            return True

        match = re.fullmatch(r"/api/crews/([\w-]+)", path)
        if match:
            crew_id = match.group(1)
            if method == "GET":
                crew = store.get_crew(crew_id)
                if not crew:
                    if store.is_corrupt(crew_id):
                        self._error(409, "Файл проекта повреждён; копия сохранена рядом с расширением .json.corrupt")
                    else:
                        self._error(404, "Проект не найден")
                    return True
                normalized = normalize_crew(crew)
                self._send_json(
                    200,
                    {
                        "crew": normalized,
                        "validation": validate_crew(normalized, allow_network=network_allowed),
                        "workspace": workspace.describe(normalized),
                    },
                )
                return True
            if method == "PUT":
                payload = self._read_json()
                incoming = payload.get("crew")
                if not isinstance(incoming, dict) or "agents" not in incoming or "tasks" not in incoming:
                    # PUT replaces the project; a partial body would silently erase it.
                    self._error(422, "Проект нужно передавать целиком: в теле нет agents и tasks")
                    return True
                rejected: list[dict] = []
                crew = normalize_crew({**incoming, "id": crew_id}, rejected)
                if str(crew.get("workspace") or "").strip():
                    try:
                        workspace.ensure(workspace.resolve(crew["workspace"], crew_id))
                    except OSError as exc:
                        self._error(400, f"Не удалось создать рабочую папку: {exc}")
                        return True
                saved = store.save_crew(crew)
                self._send_json(
                    200,
                    {
                        "crew": saved,
                        "rejected": rejected,
                        "validation": validate_crew(
                            saved, allow_network=network_allowed, rejected=rejected
                        ),
                    },
                )
                return True
            if method == "DELETE":
                self._send_json(200, {"ok": store.delete_crew(crew_id)})
                return True

        match = re.fullmatch(r"/api/crews/([\w-]+)/workspace", path)
        if match:
            crew_id = match.group(1)
            crew = store.get_crew(crew_id)
            if not crew:
                self._error(404, "Проект не найден")
                return True
            if method == "GET":
                self._send_json(200, {"workspace": workspace.describe(normalize_crew(crew))})
                return True
            if method in {"PUT", "POST"}:
                payload = self._read_json()
                raw = str(payload.get("path") or "").strip()
                candidate = normalize_crew({**crew, "workspace": raw})
                target = workspace.resolve(raw, crew_id)
                if raw:
                    try:
                        workspace.require_inside(
                            target, workspace.allowed_roots((store.get_settings().get("fs_roots") or []))
                        )
                    except ValueError as exc:
                        self._error(403, str(exc))
                        return True
                if target.exists() and not target.is_dir():
                    self._error(400, "Этот путь указывает на файл, а не на папку")
                    return True
                try:
                    workspace.ensure(target)
                except OSError as exc:
                    self._error(400, f"Не удалось создать папку: {exc}")
                    return True
                readable, writable_now = workspace.check_access(target)
                if not readable:
                    self._error(400, "Нет прав на чтение этой папки — агенты не смогут её открыть")
                    return True
                if not writable_now:
                    self._error(400, "Нет прав на запись в эту папку — агенты не смогут сохранять файлы")
                    return True
                saved = store.save_crew(candidate)
                self._send_json(200, {"crew": saved, "workspace": workspace.describe(saved)})
                return True

        match = re.fullmatch(r"/api/crews/([\w-]+)/(duplicate|validate|code)", path)
        if match and method in {"POST", "GET"}:
            crew_id, action = match.group(1), match.group(2)
            crew = store.get_crew(crew_id)
            if not crew:
                self._error(404, "Проект не найден")
                return True
            if action == "duplicate":
                created = store.duplicate_crew(crew_id)
                self._send_json(201, {"crew": created})
                return True
            if action == "validate":
                payload = self._read_json() if method == "POST" else {}
                candidate = normalize_crew(payload.get("crew") or crew)
                known = {t["name"] for t in tool_registry.catalogue(network_allowed) if t["available"]}
                self._send_json(200, validate_crew(candidate, known, allow_network=network_allowed))
                return True
            if action == "code":
                settings = store.get_settings()
                normalized = normalize_crew(crew)
                known = {t["name"] for t in tool_registry.catalogue(network_allowed) if t["available"]}
                validation = validate_crew(normalized, known, allow_network=network_allowed)
                if not validation["ok"]:
                    # The generated script runs outside the sandbox: refuse a spec
                    # that carries tools the app itself no longer allows.
                    self._error(422, "Проект не проходит проверку — код не сгенерирован", validation=validation)
                    return True
                self._send_json(
                    200,
                    {
                        "code": to_python(
                            normalized,
                            settings.get("default_llm", ""),
                            int(settings.get("llm_timeout") or 120),
                        ),
                        "warnings": validation.get("warnings") or [],
                    },
                )
                return True

        # --------------------------------------------------------- templates
        if path == "/api/templates" and method == "GET":
            self._send_json(200, {"templates": templates.list_templates()})
            return True

        if path == "/api/templates" and method == "POST":
            payload = self._read_json()
            crew_id = str(payload.get("crew_id") or "")
            crew = store.get_crew(crew_id) if crew_id else None
            if crew is None and isinstance(payload.get("crew"), dict):
                crew = payload["crew"]
            if crew is None:
                self._error(400, "Проект не найден")
                return True
            title = str(payload.get("title") or "").strip()
            if not title:
                self._error(400, "Укажите название шаблона")
                return True
            entry = templates.save_custom_template(crew, title, str(payload.get("description") or ""))
            self._send_json(201, {"template": {k: entry[k] for k in ("key", "title", "subtitle", "description", "badge", "custom")}})
            return True

        match = re.fullmatch(r"/api/templates/([\w-]+)", path)
        if match and method == "DELETE":
            self._send_json(200, {"ok": templates.delete_custom_template(match.group(1))})
            return True
        if match and method == "PUT":
            payload = self._read_json()
            title = str(payload.get("title") or "").strip()
            if not title:
                self._error(400, "Укажите название шаблона")
                return True
            entry = templates.update_custom_template(
                match.group(1), title, payload.get("description")
            )
            if entry is None:
                self._error(404, "Шаблон не найден")
                return True
            self._send_json(200, {"template": {k: entry.get(k) for k in ("key", "title", "subtitle", "description", "badge", "custom")}})
            return True

        # ------------------------------------------------------------- roles
        if path == "/api/roles" and method == "GET":
            self._send_json(200, {"roles": roles.load_roles()})
            return True

        if path == "/api/roles" and method == "POST":
            payload = self._read_json()
            self._send_json(201, {"role": roles.create_role(payload)})
            return True

        if path == "/api/roles/reset" and method == "POST":
            self._read_json()  # drain the body for keep-alive connections
            self._send_json(200, {"roles": roles.reset_roles()})
            return True

        match = re.fullmatch(r"/api/roles/([\w-]+)", path)
        if match:
            role_id = match.group(1)
            if method == "PUT":
                payload = self._read_json()
                self._send_json(200, {"role": roles.update_role(role_id, payload)})
                return True
            if method == "DELETE":
                self._send_json(200, {"ok": roles.delete_role(role_id)})
                return True

        # ---------------------------------------------------------- settings
        if path == "/api/settings" and method == "GET":
            self._send_json(200, {"settings": store.public_settings(), "providers": config.PROVIDERS})
            return True
        if path == "/api/settings" and method == "PUT":
            payload = self._read_json()
            store.save_settings(payload.get("settings") or payload)
            self._send_json(
                200,
                {"settings": store.public_settings(), "blocked_env": list(store.last_blocked_env)},
            )
            return True

        # --------------------------------------------------------------- runs
        if path == "/api/runs" and method == "GET":
            self._send_json(200, {"runs": store.list_runs()})
            return True

        if path == "/api/runs" and method == "POST":
            payload = self._read_json()
            crew_id = str(payload.get("crew_id") or "")
            if not crew_id:
                # An inline spec could smuggle its own workspace/output paths.
                self._error(422, "Запускать можно только сохранённый проект (укажите crew_id)")
                return True
            crew = store.get_crew(crew_id)
            if crew is None:
                self._error(404, "Проект не найден")
                return True
            crew = normalize_crew(crew)
            settings = store.get_settings()
            known = {t["name"] for t in tool_registry.catalogue(network_allowed) if t["available"]}
            validation = validate_crew(crew, known, allow_network=network_allowed)
            if not validation["ok"]:
                self._error(422, "Проверьте настройки проекта", validation=validation)
                return True
            inputs = payload.get("inputs")
            if not isinstance(inputs, dict) or not inputs:
                inputs = inputs_payload(crew)
            inputs = {str(k): str(v) for k, v in inputs.items()}
            try:
                state = manager.start(crew, inputs, settings)
            except BusyError as exc:
                self._error(409, str(exc))
                return True
            self._send_json(201, {"run_id": state.id, "crew_name": state.crew_name})
            return True

        if path == "/api/runs/active" and method == "GET":
            self._send_json(200, {"run_id": manager.active_id()})
            return True

        match = re.fullmatch(r"/api/runs/([\w-]+)/permissions/([\w-]+)", path)
        if match and method == "POST":
            run_id, request_id = match.group(1), match.group(2)
            payload = self._read_json()
            answered = manager.answer_permission(
                run_id,
                request_id,
                bool(payload.get("allow")),
                str(payload.get("scope") or "once"),
            )
            self._send_json(200 if answered else 409, {"ok": answered})
            return True

        match = re.fullmatch(r"/api/runs/([\w-]+)", path)
        if match:
            run_id = match.group(1)
            state = manager.get(run_id)
            if method == "GET":
                if state is not None:
                    self._send_json(200, {"run": state.snapshot(), "live": True})
                    return True
                run = store.get_run(run_id)
                if not run:
                    self._error(404, "Запуск не найден")
                    return True
                self._send_json(200, {"run": run, "live": False})
                return True
            if method == "DELETE":
                self._send_json(200, {"ok": store.delete_run(run_id)})
                return True

        match = re.fullmatch(r"/api/runs/([\w-]+)/(cancel|detach|events|export)", path)
        if match:
            run_id, action = match.group(1), match.group(2)
            if action == "cancel" and method == "POST":
                self._read_json()
                self._send_json(200, {"ok": manager.cancel(run_id)})
                return True
            if action == "detach" and method == "POST":
                self._read_json()
                self._send_json(200, {"ok": manager.detach(run_id)})
                return True
            if action == "events" and method == "GET":
                self._stream_events(run_id)
                return True
            if action == "export" and method == "GET":
                run = store.get_run(run_id)
                state = manager.get(run_id)
                if state is not None:
                    run = state.snapshot()
                if not run:
                    self._error(404, "Запуск не найден")
                    return True
                fmt = (query.get("format") or ["md"])[0].lower()
                crew = run.get("crew") or {}
                if fmt == "json":
                    body = json.dumps(run, ensure_ascii=False, indent=2).encode("utf-8")
                    name, ctype = f"run-{run_id}.json", "application/json; charset=utf-8"
                else:
                    body = _export_markdown(run, crew).encode("utf-8")
                    name, ctype = f"run-{run_id}.md", "text/markdown; charset=utf-8"
                self.send_response(200)
                for header, value in security.SECURITY_HEADERS.items():
                    self.send_header(header, value)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Disposition", f'attachment; filename="{name}"')
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
                return True

        # ------------------------------------------------------------ llm test
        if path == "/api/llm/test" and method == "POST":
            payload = self._read_json()
            model = resolve_llm(str(payload.get("model") or ""), "", store.get_settings().get("default_llm", ""))
            if not model:
                self._error(400, "Укажите модель")
                return True
            result = test_llm(model, store.effective_env())
            self._send_json(200 if result.get("ok") else 400, result)
            return True

        return False

    # ------------------------------------------------------------------- SSE
    def _stream_events(self, run_id: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-transform")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        self.close_connection = True
        try:
            last_event_id = (self.headers.get("Last-Event-ID") or "0").strip()
            after = int(last_event_id) if last_event_id.isdigit() else 0
        except (TypeError, ValueError):
            after = 0
        try:
            for chunk in stream_lines(self.manager, run_id, after=after):
                self.wfile.write(chunk.encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass


def test_llm(model: str, env: dict[str, str]) -> dict:
    """One tiny round-trip to verify credentials and connectivity."""
    from .runner import env_lock

    started = time.time()
    try:
        with env_lock():
            saved = {k: os.environ.get(k) for k in env}
            os.environ.update({k: v for k, v in env.items() if v})
            try:
                from crewai import LLM

                llm = LLM(model=model, temperature=0)
                answer = llm.call([{"role": "user", "content": "Ответь одним словом: работает"}])
            finally:
                for key, old in saved.items():
                    if old is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = old
        text = answer if isinstance(answer, str) else str(getattr(answer, "content", answer))
        return {
            "ok": True,
            "model": model,
            "latency": round(time.time() - started, 2),
            "answer": text[:400],
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "model": model,
            "latency": round(time.time() - started, 2),
            "error": f"{type(exc).__name__}: {exc}",
        }


def find_free_port(preferred: int, host: str) -> int:
    for port in [preferred, *range(preferred + 1, preferred + 25), 0]:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((host, port))
                return sock.getsockname()[1]
            except OSError:
                continue
    raise RuntimeError("Не удалось найти свободный порт")


class StudioServer(ThreadingHTTPServer):
    """Bounded thread pool: a burst of connections must not spawn unbounded threads."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, *args: Any, max_connections: int = 64, **kwargs: Any) -> None:
        self._slots = threading.BoundedSemaphore(max_connections)
        super().__init__(*args, **kwargs)

    def process_request(self, request: Any, client_address: Any) -> None:
        if not self._slots.acquire(blocking=False):
            try:
                request.close()
            except OSError:
                pass
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self._slots.release()
            raise

    def process_request_thread(self, request: Any, client_address: Any) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()


def create_server(host: str, port: int) -> StudioServer:
    store = Store()
    manager = RunManager(store)

    handler = type(
        "BoundStudioHandler",
        (StudioHandler,),
        {"store": store, "manager": manager, "session_token": "", "allowed_hosts": set()},
    )
    server = StudioServer((host, port), handler)
    actual_port = server.server_address[1]
    handler.session_token = secrets.token_urlsafe(24)
    hosts = {f"{name}:{actual_port}" for name in {host, "127.0.0.1", "localhost", "[::1]"}}
    handler.allowed_hosts = hosts
    return server


def serve(
    host: str = "127.0.0.1",
    port: int = 7860,
    open_browser: bool = True,
) -> None:
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit(
            "Отказ запуска: у интерфейса нет пароля, поэтому он слушает только 127.0.0.1.\n"
            "Удалённый доступ не поддерживается."
        )
    actual_port = find_free_port(port, host)
    server = create_server(host, actual_port)
    url = f"http://{host}:{actual_port}"
    # Warm the CrewAI import in the background so the first page load is instant.
    threading.Thread(target=crewai_status, name="crewai-warmup", daemon=True).start()
    print(f"\n  CrewAI Studio запущен: {url}\n")
    status = crewai_status()
    if status["installed"]:
        print(f"  CrewAI {status['version']} · Python {status['python']}")
    else:
        print(f"  ВНИМАНИЕ: CrewAI не установлен ({status['error']})")
        print("  Запустите start.bat — он создаст окружение и установит зависимости.\n")
    print("  Остановить: Ctrl+C\n")
    if open_browser:
        def _open() -> None:
            time.sleep(0.8)
            try:
                import webbrowser

                webbrowser.open(url)
            except Exception:  # noqa: BLE001
                pass

        threading.Thread(target=_open, daemon=True).start()
    try:
        server.serve_forever(poll_interval=0.3)
    except KeyboardInterrupt:
        print("\n  Остановлено.")
    finally:
        server.shutdown()
