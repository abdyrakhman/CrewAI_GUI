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

from . import auth, config, observability, roles, security, templates, tools as tool_registry, workspace
from .api import dispatch
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

    def handle_one_request(self) -> None:
        try:
            super().handle_one_request()
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, TimeoutError):
            # a browser tab closed mid-request must not print a traceback to the console
            self.close_connection = True

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003 - stdlib signature
        if os.environ.get("CREWAI_STUDIO_VERBOSE"):
            sys.stderr.write("[studio] " + (fmt % args) + "\n")

    # ------------------------------------------------------------- perimeter
    def _deny(self, status: int, message: str) -> None:
        self._send_json(status, {"error": message})

    def _check_perimeter(self, method: str, path: str = "") -> bool:
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
        if method in {"POST", "PUT", "PATCH", "DELETE"} and not path.startswith("/api/auth/"):
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
        retry_after = getattr(self, "_retry_after", "")
        if retry_after:
            self.send_header("Retry-After", retry_after)
        request_id = getattr(self, "request_id", "")
        if request_id:
            self.send_header("X-Request-Id", request_id)
        cookie = getattr(self, "_session_cookie", "")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _send_download(self, filename: str, body: bytes, content_type: str) -> None:
        self._last_status = 200
        self.send_response(200)
        for header, value in security.SECURITY_HEADERS.items():
            self.send_header(header, value)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

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
        if not self._check_perimeter(method, path):
            observability.log_request(method, path, 403, self.request_id, started)
            return
        try:
            if method == "GET" and path == "/login":
                self._serve_web("login.html")
                return
            if method == "GET" and path in {"/login.js", "/login.css", "/change-password.html", "/change-password.js"}:
                self._serve_web(path.lstrip("/"))
                return
            if method == "GET" and path.startswith("/static/"):
                self._serve_web(urllib.parse.unquote(path[len("/static/"):]))
                return
            if path.startswith("/api/auth/"):
                self._handle_auth(method, path)
                return

            user = self._session_user()
            self.current_user = user or ""
            if not user:
                if path.startswith("/api/"):
                    self._error(401, "Требуется вход", auth=True)
                else:
                    self._redirect("/login")
                return
            if auth.must_change(user):
                if path.startswith("/api/"):
                    self._send_json(403, {
                        "error": "Сначала смените пароль",
                        "password_change_required": True,
                    })
                else:
                    self._redirect("/change-password.html")
                return

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

    def _session_user(self) -> str | None:
        if os.environ.get("CREWAI_STUDIO_NO_AUTH") == "1":
            return "local"
        token = auth.cookie_value(self.headers.get("Cookie", ""))
        return auth.session_user(token)

    def _redirect(self, location: str) -> None:
        self.send_response(302)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        for header, value in security.SECURITY_HEADERS.items():
            self.send_header(header, value)
        self.end_headers()

    def _set_session_cookie(self, token: str, ttl_hours: float) -> None:
        seconds = int(max(1.0, float(ttl_hours)) * 3600)
        self._session_cookie = (
            f"{auth.COOKIE_NAME}={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age={seconds}"
        )

    def _session_ttl(self) -> float:
        try:
            return float(self.store.get_settings().get("session_ttl_hours", auth.DEFAULT_TTL_HOURS))
        except (TypeError, ValueError):
            return auth.DEFAULT_TTL_HOURS

    def _handle_auth(self, method: str, path: str) -> bool:
        store = self.store
        if path == "/api/auth/state" and method == "GET":
            user = self._session_user()
            try:
                language = str(self.store.get_settings().get("ui_language") or "ru")
            except Exception:  # noqa: BLE001 - settings must not break sign-in
                language = "ru"
            self._send_json(200, {
                "has_users": auth.has_users(),
                "user": user,
                "language": "en" if language == "en" else "ru",
                "bootstrap": auth.bootstrap_credentials(),
            })
            return True

        if path == "/api/auth/login" and method == "POST":
            ip = self.client_address[0] if self.client_address else "?"
            wait = _login_blocked(ip)
            if wait:
                self._retry_after = str(int(wait))
                self._error(429, f"Слишком много попыток входа. Повторите через {int(wait // 60) + 1} мин.")
                return True
            payload = self._read_json()
            username = str(payload.get("username") or "").strip()
            password = str(payload.get("password") or "")
            record = auth.get_user(username)
            if not record or not auth.verify_password(password, record):
                _login_failed(ip)
                self._error(401, "Неверный логин или пароль")
                return True
            _login_succeeded(ip)
            ttl = self._session_ttl()
            token = auth.create_session(username, ttl)
            self._set_session_cookie(token, ttl)
            self._send_json(200, {
                "user": username,
                "must_change": auth.must_change(username),
            })
            return True

        if path == "/api/auth/register" and method == "POST":
            payload = self._read_json()
            username = str(payload.get("username") or "").strip()
            password = str(payload.get("password") or "")
            try:
                created = auth.create_user(username, password)
            except ValueError as exc:
                self._error(400, str(exc))
                return True
            ttl = self._session_ttl()
            token = auth.create_session(created["username"], ttl)
            self._set_session_cookie(token, ttl)
            self._send_json(201, {"user": created["username"], "must_change": False})
            return True

        if path == "/api/auth/logout" and method == "POST":
            token = auth.cookie_value(self.headers.get("Cookie", ""))
            auth.drop_session(token)
            self._session_cookie = f"{auth.COOKIE_NAME}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0"
            self._send_json(200, {"ok": True})
            return True

        if path == "/api/auth/password" and method == "POST":
            token = auth.cookie_value(self.headers.get("Cookie", ""))
            username = auth.session_user(token)
            if not username:
                self._error(401, "Требуется вход", auth=True)
                return True
            payload = self._read_json()
            try:
                auth.change_password(
                    username, str(payload.get("current") or ""), str(payload.get("new") or "")
                )
            except ValueError as exc:
                self._error(400, str(exc))
                return True
            dropped = auth.drop_user_sessions(username, keep_token=token)
            self._send_json(200, {"ok": True, "dropped_sessions": dropped})
            return True

        if path == "/api/auth/logout-all" and method == "POST":
            token = auth.cookie_value(self.headers.get("Cookie", ""))
            username = auth.session_user(token)
            if not username:
                self._error(401, "Требуется вход", auth=True)
                return True
            removed = auth.drop_user_sessions(username)
            self._session_cookie = f"{auth.COOKIE_NAME}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0"
            self._send_json(200, {"ok": True, "dropped_sessions": removed})
            return True

        if path == "/api/auth/me" and method == "GET":
            user = self._session_user()
            if not user:
                self._error(401, "Требуется вход", auth=True)
                return True
            self._send_json(200, {"user": user})
            return True

        self._error(404, "Не найдено")
        return True

    def _handle_api(self, method: str, path: str, query: dict[str, list[str]]) -> bool:
        return dispatch.handle(self, method, path, query)

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
            self.connection.settimeout(120)
        except OSError:
            pass
        try:
            for chunk in stream_lines(self.manager, run_id, after=after, heartbeat=5.0):
                self.wfile.write(chunk.encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, TimeoutError, OSError):
            # a slow or closed tab must not produce a 500 in the log
            self.close_connection = True


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


_LOGIN_LOCK = threading.Lock()
_LOGIN_ATTEMPTS: dict[str, list[float]] = {}
LOGIN_MAX_FAILURES = 5
LOGIN_WINDOW = 600.0


def _login_blocked(ip: str) -> float:
    """Seconds to wait before another attempt, or 0 when allowed."""
    now = time.time()
    with _LOGIN_LOCK:
        attempts = [stamp for stamp in _LOGIN_ATTEMPTS.get(ip, []) if now - stamp < LOGIN_WINDOW]
        _LOGIN_ATTEMPTS[ip] = attempts
        if len(attempts) >= LOGIN_MAX_FAILURES:
            return max(1.0, LOGIN_WINDOW - (now - attempts[0]))
    return 0.0


def _login_failed(ip: str) -> None:
    with _LOGIN_LOCK:
        _LOGIN_ATTEMPTS.setdefault(ip, []).append(time.time())


def _login_succeeded(ip: str) -> None:
    with _LOGIN_LOCK:
        _LOGIN_ATTEMPTS.pop(ip, None)


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
    created_admin = auth.ensure_default_admin()
    store = Store()
    store.prune_runs()
    manager = RunManager(store)

    handler = type(
        "BoundStudioHandler",
        (StudioHandler,),
        {"store": store, "manager": manager, "session_token": "", "allowed_hosts": set()},
    )
    server = StudioServer((host, port), handler)
    if created_admin:
        server.generated_admin = created_admin
        if created_admin.get("rotated"):
            print("  Прежний пароль администратора по умолчанию сброшен на случайный.")
        else:
            print("  Создан администратор.")
        print(f"  Логин:  {created_admin['username']}")
        print(f"  Пароль: {created_admin['password']}")
        print("  Пароль также показан на экране входа, пока его не сменят.")
        print("  При первом входе приложение попросит задать новый пароль.")
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