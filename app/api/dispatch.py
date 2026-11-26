"""API dispatcher: every /api route except auth and SSE."""
from __future__ import annotations

import base64
import json
import re
import urllib.parse
import urllib.request
import uuid

from .. import auth, config, observability, roles, security, templates, tools as tool_registry, workspace
from ..runner import BusyError, RunManager, crewai_status, stream_lines
from ..spec import inputs_payload, normalize_crew, resolve_llm, to_python, validate_crew
from ..store import as_jsonable


def _export_markdown(*args, **kwargs):
    from ..server import _export_markdown as impl

    return impl(*args, **kwargs)


def _test_llm(*args, **kwargs):
    from ..server import test_llm

    return test_llm(*args, **kwargs)


def handle(api, method: str, path: str, query: dict[str, list[str]]) -> bool:
    """Dispatch one API request; returns True when it was handled."""
    store, manager = api.store, api.manager
    network_allowed = tool_registry.allowed_network_names(api.store.get_settings().get("allow_network_tools"))

    if method == "GET" and path == "/api/info":
        settings = api.store.public_settings()
        api._send_json(
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
        settings = api.store.get_settings()
        env = api.store.effective_env()
        api._send_json(
            200,
            {
                "crewai": crewai_status(),
                "env": tool_registry.env_preview(env),
                "busy": api.manager.is_busy(),
                "active_run": api.manager.active_id(),
            },
        )
        return True

    if method == "GET" and path == "/api/tools":
        api._send_json(200, {"tools": tool_registry.catalogue(network_allowed)})
        return True

    if path == "/api/tools/install":
        if method == "GET":
            api._send_json(200, tool_registry.install_status())
            return True
        if method == "POST":
            api._read_json()  # drain the body: keep-alive needs it consumed
            started = tool_registry.install_extras()
            api._send_json(202 if started else 409, {"started": started, "status": tool_registry.install_status()})
            return True

    if method == "GET" and path == "/api/files":
        crew_id = (query.get("crew_id") or [""])[0]
        crew = api.store.get_crew(crew_id) if crew_id else None
        ws = None
        if crew is not None:
            ws, _ = workspace.for_crew(crew, workspace.allowed_roots(api.store.get_settings().get("fs_roots") or []))
        payload = tool_registry.tool_files_listing(ws)
        if crew is not None:
            payload["crew_id"] = crew.get("id", "")
            payload["workspace"] = {"path": str(ws) if ws else "", "files": payload.get("workspace", {}).get("files", [])}
        api._send_json(200, payload)
        return True

    if method == "GET" and path.startswith("/api/files/output/"):
        name = path[len("/api/files/output/"):]
        crew_id = (query.get("crew_id") or [""])[0]
        crew = api.store.get_crew(crew_id) if crew_id else None
        ws = None
        if crew is not None:
            ws, _ = workspace.for_crew(crew, workspace.allowed_roots(api.store.get_settings().get("fs_roots") or []))
        content = tool_registry.read_output_file(name, ws)
        api._send_json(200, {"name": name, "content": content})
        return True

    if method == "POST" and path == "/api/files":
        payload = api._read_json()
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
            crew = api.store.get_crew(crew_id)
            if crew is not None:
                target_dir, note = workspace.for_crew(
                    crew, workspace.allowed_roots(api.store.get_settings().get("fs_roots") or [])
                )
                if note:
                    api._error(400, "Рабочая область проекта отклонена политикой")
                    return True
        target = tool_registry.save_upload(str(payload.get("name") or "upload.txt"), data, target_dir)
        api._send_json(200, {"ok": True, "path": target, "in_workspace": target_dir is not None})
        return True

    # ------------------------------------------------------------ filesystem
    if method == "GET" and path == "/api/fs":
        target = (query.get("path") or [""])[0]
        roots = workspace.allowed_roots((api.store.get_settings().get("fs_roots") or []))
        api._send_json(200, workspace.list_directory(target, roots))
        return True

    if method == "POST" and path == "/api/fs/mkdir":
        payload = api._read_json()
        roots = workspace.allowed_roots((api.store.get_settings().get("fs_roots") or []))
        created = workspace.make_directory(
            str(payload.get("parent") or ""), str(payload.get("name") or ""), roots
        )
        api._send_json(201, {"path": created})
        return True

    # ------------------------------------------------------------- crews
    if path == "/api/crews" and method == "GET":
        crews = api.store.list_crews()
        api._send_json(200, {"crews": crews, "broken": list(api.store.broken_crews)})
        return True

    if path == "/api/crews" and method == "POST":
        payload = api._read_json()
        template_key = payload.get("template")
        if template_key:
            crew = normalize_crew(templates.build_template(str(template_key)))
        else:
            rejected: list[dict] = []
            crew = normalize_crew(payload.get("crew") or {}, rejected)
        saved = api.store.save_crew(crew)
        api._send_json(201, {"crew": saved, "rejected": locals().get("rejected", [])})
        return True

    match = re.fullmatch(r"/api/crews/([\w-]+)", path)
    if match:
        crew_id = match.group(1)
        if method == "GET":
            crew = api.store.get_crew(crew_id)
            if not crew:
                if api.store.is_corrupt(crew_id):
                    api._error(409, "Файл проекта повреждён; копия сохранена рядом с расширением .json.corrupt")
                else:
                    api._error(404, "Проект не найден")
                return True
            normalized = normalize_crew(crew)
            api._send_json(
                200,
                {
                    "crew": normalized,
                    "validation": validate_crew(normalized, allow_network=network_allowed),
                    "workspace": workspace.describe(normalized),
                },
            )
            return True
        if method == "PUT":
            payload = api._read_json()
            incoming = payload.get("crew")
            if not isinstance(incoming, dict) or "agents" not in incoming or "tasks" not in incoming:
                # PUT replaces the project; a partial body would silently erase it.
                api._error(422, "Проект нужно передавать целиком: в теле нет agents и tasks")
                return True
            rejected: list[dict] = []
            crew = normalize_crew({**incoming, "id": crew_id}, rejected)
            if str(crew.get("workspace") or "").strip():
                try:
                    workspace.ensure(workspace.resolve(crew["workspace"], crew_id))
                except OSError as exc:
                    api._error(400, f"Не удалось создать рабочую папку: {exc}")
                    return True
            saved = api.store.save_crew(crew)
            api._send_json(
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
            api._send_json(200, {"ok": api.store.delete_crew(crew_id)})
            return True

    match = re.fullmatch(r"/api/crews/([\w-]+)/workspace", path)
    if match:
        crew_id = match.group(1)
        crew = api.store.get_crew(crew_id)
        if not crew:
            api._error(404, "Проект не найден")
            return True
        if method == "GET":
            api._send_json(200, {"workspace": workspace.describe(normalize_crew(crew))})
            return True
        if method in {"PUT", "POST"}:
            payload = api._read_json()
            raw = str(payload.get("path") or "").strip()
            candidate = normalize_crew({**crew, "workspace": raw})
            target = workspace.resolve(raw, crew_id)
            if raw:
                try:
                    workspace.require_inside(
                        target, workspace.allowed_roots((api.store.get_settings().get("fs_roots") or []))
                    )
                except ValueError as exc:
                    api._error(403, str(exc))
                    return True
            if target.exists() and not target.is_dir():
                api._error(400, "Этот путь указывает на файл, а не на папку")
                return True
            try:
                workspace.ensure(target)
            except OSError as exc:
                api._error(400, f"Не удалось создать папку: {exc}")
                return True
            readable, writable_now = workspace.check_access(target)
            if not readable:
                api._error(400, f"Нет прав на чтение папки {target} — агенты не смогут её открыть")
                return True
            if not writable_now:
                api._error(400, f"Нет прав на запись в {target} — Windows не разрешает создавать файлы. Выберите другую папку, например внутри E:\\CrewAI, или папку по умолчанию.")
                return True
            saved = api.store.save_crew(candidate)
            api._send_json(200, {"crew": saved, "workspace": workspace.describe(saved)})
            return True

    match = re.fullmatch(r"/api/crews/([\w-]+)/(duplicate|validate|code)", path)
    if match and method in {"POST", "GET"}:
        crew_id, action = match.group(1), match.group(2)
        crew = api.store.get_crew(crew_id)
        if not crew:
            api._error(404, "Проект не найден")
            return True
        if action == "duplicate":
            created = api.store.duplicate_crew(crew_id)
            api._send_json(201, {"crew": created})
            return True
        if action == "validate":
            payload = api._read_json() if method == "POST" else {}
            candidate = normalize_crew(payload.get("crew") or crew)
            known = {t["name"] for t in tool_registry.catalogue(network_allowed) if t["available"]}
            api._send_json(200, validate_crew(candidate, known, allow_network=network_allowed))
            return True
        if action == "code":
            settings = api.store.get_settings()
            normalized = normalize_crew(crew)
            known = {t["name"] for t in tool_registry.catalogue(network_allowed) if t["available"]}
            validation = validate_crew(normalized, known, allow_network=network_allowed)
            if not validation["ok"]:
                # The generated script runs outside the sandbox: refuse a spec
                # that carries tools the app itself no longer allows.
                api._error(422, "Проект не проходит проверку — код не сгенерирован", validation=validation)
                return True
            api._send_json(
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
        api._send_json(200, {"templates": templates.list_templates()})
        return True

    if path == "/api/templates" and method == "POST":
        payload = api._read_json()
        crew_id = str(payload.get("crew_id") or "")
        crew = api.store.get_crew(crew_id) if crew_id else None
        if crew is None and isinstance(payload.get("crew"), dict):
            crew = payload["crew"]
        if crew is None:
            api._error(400, "Проект не найден")
            return True
        title = str(payload.get("title") or "").strip()
        if not title:
            api._error(400, "Укажите название шаблона")
            return True
        entry = templates.save_custom_template(crew, title, str(payload.get("description") or ""))
        api._send_json(201, {"template": {k: entry[k] for k in ("key", "title", "subtitle", "description", "badge", "custom")}})
        return True

    match = re.fullmatch(r"/api/templates/([\w-]+)", path)
    if match and method == "GET":
        entry = templates.get_custom_template(match.group(1))
        if entry is None:
            api._error(404, "Шаблон не найден")
            return True
        api._send_json(200, {"template": entry})
        return True
    if match and method == "DELETE":
        api._send_json(200, {"ok": templates.delete_custom_template(match.group(1))})
        return True
    if match and method == "PUT":
        payload = api._read_json()
        title = str(payload.get("title") or "").strip()
        if not title:
            api._error(400, "Укажите название шаблона")
            return True
        entry = templates.update_custom_template(
            match.group(1), title, payload.get("description"), payload.get("crew")
        )
        if entry is None:
            api._error(404, "Шаблон не найден")
            return True
        api._send_json(200, {"template": {k: entry.get(k) for k in ("key", "title", "subtitle", "description", "badge", "custom")}})
        return True

    # ------------------------------------------------------------- roles
    if path == "/api/roles" and method == "GET":
        api._send_json(200, {"roles": roles.load_roles()})
        return True

    if path == "/api/roles" and method == "POST":
        payload = api._read_json()
        api._send_json(201, {"role": roles.create_role(payload)})
        return True

    if path == "/api/roles/reset" and method == "POST":
        api._read_json()  # drain the body for keep-alive connections
        api._send_json(200, {"roles": roles.reset_roles()})
        return True

    match = re.fullmatch(r"/api/roles/([\w-]+)", path)
    if match:
        role_id = match.group(1)
        if method == "PUT":
            payload = api._read_json()
            api._send_json(200, {"role": roles.update_role(role_id, payload)})
            return True
        if method == "DELETE":
            api._send_json(200, {"ok": roles.delete_role(role_id)})
            return True

    # ---------------------------------------------------------- settings
    if path == "/api/settings" and method == "GET":
        api._send_json(200, {"settings": api.store.public_settings(), "providers": config.PROVIDERS})
        return True
    if path == "/api/settings" and method == "PUT":
        payload = api._read_json()
        api.store.save_settings(payload.get("settings") or payload)
        api._send_json(
            200,
            {"settings": api.store.public_settings(), "blocked_env": list(api.store.last_blocked_env)},
        )
        return True

    # --------------------------------------------------------------- runs
    if path == "/api/runs" and method == "GET":
        api._send_json(200, {"runs": api.store.list_runs()})
        return True

    if path == "/api/runs" and method == "POST":
        payload = api._read_json()
        crew_id = str(payload.get("crew_id") or "")
        if not crew_id:
            # An inline spec could smuggle its own workspace/output paths.
            api._error(422, "Запускать можно только сохранённый проект (укажите crew_id)")
            return True
        crew = api.store.get_crew(crew_id)
        if crew is None:
            api._error(404, "Проект не найден")
            return True
        crew = normalize_crew(crew)
        settings = api.store.get_settings()
        known = {t["name"] for t in tool_registry.catalogue(network_allowed) if t["available"]}
        validation = validate_crew(crew, known, allow_network=network_allowed)
        if not validation["ok"]:
            api._error(422, "Проверьте настройки проекта", validation=validation)
            return True
        inputs = payload.get("inputs")
        if not isinstance(inputs, dict) or not inputs:
            inputs = inputs_payload(crew)
        inputs = {str(k): str(v) for k, v in inputs.items()}
        try:
            state = api.manager.start(crew, inputs, settings)
        except BusyError as exc:
            api._error(409, str(exc))
            return True
        api._send_json(201, {"run_id": state.id, "crew_name": state.crew_name})
        return True

    if path == "/api/runs/active" and method == "GET":
        api._send_json(200, {"run_id": api.manager.active_id()})
        return True

    match = re.fullmatch(r"/api/runs/([\w-]+)/permissions/([\w-]+)", path)
    if match and method == "POST":
        run_id, request_id = match.group(1), match.group(2)
        payload = api._read_json()
        answered = api.manager.answer_permission(
            run_id,
            request_id,
            bool(payload.get("allow")),
            str(payload.get("scope") or "once"),
        )
        api._send_json(200 if answered else 409, {"ok": answered})
        return True

    match = re.fullmatch(r"/api/runs/([\w-]+)", path)
    if match:
        run_id = match.group(1)
        state = api.manager.get(run_id)
        if method == "GET":
            if state is not None:
                api._send_json(200, {"run": state.snapshot(), "live": True})
                return True
            run = api.store.get_run(run_id)
            if not run:
                api._error(404, "Запуск не найден")
                return True
            api._send_json(200, {"run": run, "live": False})
            return True
        if method == "DELETE":
            api._send_json(200, {"ok": api.store.delete_run(run_id)})
            return True

    match = re.fullmatch(r"/api/runs/([\w-]+)/(cancel|detach|events|export)", path)
    if match:
        run_id, action = match.group(1), match.group(2)
        if action == "cancel" and method == "POST":
            api._read_json()
            api._send_json(200, {"ok": api.manager.cancel(run_id)})
            return True
        if action == "detach" and method == "POST":
            api._read_json()
            api._send_json(200, {"ok": api.manager.detach(run_id)})
            return True
        if action == "events" and method == "GET":
            api._stream_events(run_id)
            return True
        if action == "export" and method == "GET":
            run = api.store.get_run(run_id)
            state = api.manager.get(run_id)
            if state is not None:
                run = state.snapshot()
            if not run:
                api._error(404, "Запуск не найден")
                return True
            fmt = (query.get("format") or ["md"])[0].lower()
            crew = run.get("crew") or {}
            if fmt == "json":
                body = json.dumps(run, ensure_ascii=False, indent=2).encode("utf-8")
                name, ctype = f"run-{run_id}.json", "application/json; charset=utf-8"
            else:
                body = _export_markdown(run, crew).encode("utf-8")
                name, ctype = f"run-{run_id}.md", "text/markdown; charset=utf-8"
            api.send_response(200)
            for header, value in security.SECURITY_HEADERS.items():
                api.send_header(header, value)
            api.send_header("Content-Type", ctype)
            api.send_header("Content-Disposition", f'attachment; filename="{name}"')
            api.send_header("Content-Length", str(len(body)))
            api.send_header("Cache-Control", "no-store")
            api.end_headers()
            api.wfile.write(body)
            return True

    # ------------------------------------------------------------ llm test
    if path == "/api/llm/test" and method == "POST":
        payload = api._read_json()
        model = resolve_llm(str(payload.get("model") or ""), "", api.store.get_settings().get("default_llm", ""))
        if not model:
            api._error(400, "Укажите модель")
            return True
        result = _test_llm(model, api.store.effective_env())
        api._send_json(200 if result.get("ok") else 400, result)
        return True

    return False
    return False
