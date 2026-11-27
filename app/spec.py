"""Normalisation, validation and code preview for a crew specification."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .config import normalize_model
from .store import new_id

PLACEHOLDER_RE = re.compile(r"(?<!\{)\{([A-Za-z_][A-Za-z0-9_]*)\}(?!\})")
# CrewAI's own interpolator matches even inside doubled braces, so its view wins.
CREWAI_VAR_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_\-]*)\}")

AGENT_DEFAULTS: dict[str, Any] = {
    "role": "",
    "goal": "",
    "backstory": "",
    "role_id": "",
    "llm": "",
    "tools": [],
    "allow_delegation": False,
    "confirm_changes": False,
    "max_iter": 12,
    "max_execution_time": 0,
    "reasoning": False,
    "cache": True,
    "verbose": False,
}

TASK_DEFAULTS: dict[str, Any] = {
    "name": "",
    "description": "",
    "expected_output": "",
    "agent": "",
    "context": [],
    "async_execution": False,
    "human_input": False,
    "output_format": "text",  # text | markdown | file | json
    "output_file": "",
    "tools": [],
}

CREW_DEFAULTS: dict[str, Any] = {
    "name": "Новый проект",
    "description": "",
    "workspace": "",
    "process": "sequential",
    "manager_llm": "",
    "default_llm": "",
    "verbose": False,
    "memory": False,
    "cache": True,
    "max_rpm": 0,
    "planning": False,
    "agents": [],
    "tasks": [],
    "inputs": [],
}


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "да"}
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _note_unknown(payload: dict, allowed: set[str], where: str, rejected: list[dict] | None) -> None:
    if rejected is None or not isinstance(payload, dict):
        return
    for key in payload:
        if key not in allowed:
            rejected.append({"field": f"{where}.{key}", "message": f"Поле «{key}» не распознано и проигнорировано"})


def normalize_agent(agent: dict, index: int, rejected: list[dict] | None = None) -> dict:
    _note_unknown(agent, set(AGENT_DEFAULTS) | {"id"}, f"agents[{index}]", rejected)
    out = dict(AGENT_DEFAULTS)
    out.update({k: v for k, v in (agent or {}).items() if k in AGENT_DEFAULTS or k == "id"})
    out["id"] = str(out.get("id") or new_id("a-"))
    out["max_iter"] = max(1, _coerce_int(out.get("max_iter"), 12))
    out["max_execution_time"] = max(0, _coerce_int(out.get("max_execution_time"), 0))
    for key in ("allow_delegation", "reasoning", "cache", "verbose", "confirm_changes"):
        out[key] = _coerce_bool(out.get(key), AGENT_DEFAULTS[key])
    out["tools"] = _migrate_tools(out.get("tools") or [], index, rejected)
    for key in ("role", "goal", "backstory", "llm", "role_id"):
        out[key] = str(out.get(key) or "").strip()
    out["_index"] = index
    return out


def _migrate_tools(tools: list, index: int, rejected: list[dict] | None) -> list[str]:
    """Map removed third-party tools from legacy projects onto safe built-ins.

    Projects saved before the sandbox hardening carry names like ``FileReadTool``.
    Blocking those runs is worse than migrating: the built-in equivalents are
    strictly safer and keep the project working.
    """
    from .tools import DROPPED_TOOL_NAMES, TOOL_ALIASES

    result: list[str] = []
    for raw in tools:
        name = str(raw).strip()
        if not name:
            continue
        if name in TOOL_ALIASES:
            replacement = TOOL_ALIASES[name]
            if replacement not in result:
                result.append(replacement)
            if rejected is not None:
                rejected.append(
                    {
                        "field": f"agents[{index}].tools",
                        "message": f"Инструмент «{name}» заменён на встроенный «{replacement}»",
                    }
                )
            continue
        if name in DROPPED_TOOL_NAMES:
            if rejected is not None:
                rejected.append(
                    {
                        "field": f"agents[{index}].tools",
                        "message": f"Инструмент «{name}» отключён и убран из проекта",
                    }
                )
            continue
        if name not in result:
            result.append(name)
    return result


def normalize_task(task: dict, index: int, rejected: list[dict] | None = None) -> dict:
    _note_unknown(task, set(TASK_DEFAULTS) | {"id"}, f"tasks[{index}]", rejected)
    out = dict(TASK_DEFAULTS)
    out.update({k: v for k, v in (task or {}).items() if k in TASK_DEFAULTS or k == "id"})
    out["id"] = str(out.get("id") or new_id("t-"))
    out["context"] = [str(c) for c in (out.get("context") or [])]
    out["tools"] = [str(t) for t in (out.get("tools") or []) if str(t).strip()]
    for key in ("async_execution", "human_input"):
        out[key] = _coerce_bool(out.get(key), False)
    fmt = str(out.get("output_format") or "text").lower()
    out["output_format"] = fmt if fmt in {"text", "markdown", "file", "json"} else "text"
    for key in ("name", "description", "expected_output", "agent", "output_file"):
        out[key] = str(out.get(key) or "").strip()
    out["_index"] = index
    return out


def normalize_crew(crew: dict, rejected: list[dict] | None = None) -> dict:
    _note_unknown(crew, set(CREW_DEFAULTS) | {"id", "created_at", "updated_at"}, "crew", rejected)
    out = dict(CREW_DEFAULTS)
    out.update({k: v for k, v in (crew or {}).items() if k in CREW_DEFAULTS or k in {"id", "created_at", "updated_at"}})
    out["process"] = "hierarchical" if str(out.get("process", "")).lower() == "hierarchical" else "sequential"
    for key in ("verbose", "memory", "cache", "planning"):
        out[key] = _coerce_bool(out.get(key), CREW_DEFAULTS[key])
    out["max_rpm"] = max(0, _coerce_int(out.get("max_rpm"), 0))
    for key in ("name", "description", "manager_llm", "default_llm", "workspace"):
        out[key] = str(out.get(key) or "").strip()
    out["agents"] = [normalize_agent(a, i, rejected) for i, a in enumerate(crew.get("agents") or [])]
    out["tasks"] = [normalize_task(t, i, rejected) for i, t in enumerate(crew.get("tasks") or [])]
    agent_ids = {a["id"] for a in out["agents"]}
    task_ids = {t["id"] for t in out["tasks"]}
    for task in out["tasks"]:
        if task["agent"] and task["agent"] not in agent_ids:
            task["agent"] = ""
        task["context"] = [c for c in task["context"] if c in task_ids and c != task["id"]]

    inputs = []
    seen: set[str] = set()
    for item in crew.get("inputs") or []:
        if isinstance(item, str):
            item = {"key": item, "value": "", "description": ""}
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        inputs.append(
            {
                "key": key,
                "value": str(item.get("value") or ""),
                "description": str(item.get("description") or ""),
            }
        )
    out["inputs"] = inputs
    for agent in out["agents"]:
        agent.pop("_index", None)
    for task in out["tasks"]:
        task.pop("_index", None)
    return out


def inputs_for_run(crew: dict, user_inputs: dict[str, str]) -> dict[str, str]:
    """Inputs for CrewAI: undeclared placeholders are mapped to themselves.

    CrewAI's interpolator scans ``{name}`` with a regex that also matches inside
    ``{{name}}``, so escaping does not work. Mapping the missing name to the
    literal ``{name}`` keeps pasted text (JSON snippets, code, prompts) intact
    instead of failing the whole run.
    """
    declared = {str(item.get("key")) for item in (crew.get("inputs") or []) if item.get("key")}
    merged = {str(key): str(value) for key, value in (user_inputs or {}).items()}
    texts: list[str] = [str(crew.get("description") or "")]
    for agent in crew.get("agents") or []:
        texts.extend(str(agent.get(key) or "") for key in ("role", "goal", "backstory"))
    for task in crew.get("tasks") or []:
        texts.extend(str(task.get(key) or "") for key in ("name", "description", "expected_output"))
    for text in texts:
        for name in CREWAI_VAR_RE.findall(text):
            if name not in declared and name not in merged:
                merged[name] = "{" + name + "}"
    return merged


def collect_placeholders(crew: dict) -> list[str]:
    found: dict[str, int] = {}
    chunks = [crew.get("description", "")]
    for agent in crew.get("agents", []):
        chunks.extend([agent.get("role", ""), agent.get("goal", ""), agent.get("backstory", "")])
    for task in crew.get("tasks", []):
        chunks.extend([task.get("name", ""), task.get("description", ""), task.get("expected_output", "")])
    for text in chunks:
        for name in PLACEHOLDER_RE.findall(text or ""):
            found[name] = found.get(name, 0) + 1
    return sorted(found, key=lambda n: (-found[n], n))


def validate_crew(
    crew: dict,
    tools_known: set[str] | None = None,
    allow_network: set[str] | None = None,
    rejected: list[dict] | None = None,
) -> dict:
    from .tools import NETWORK_TOOL_NAMES, REMOVED_TOOLS

    errors: list[dict] = []
    warnings: list[dict] = []

    def err(field: str, message: str) -> None:
        errors.append({"field": field, "message": message})

    def warn(field: str, message: str) -> None:
        warnings.append({"field": field, "message": message})

    if not crew.get("name"):
        err("name", "Укажите название проекта")

    if not crew.get("agents"):
        err("agents", "Добавьте хотя бы одного агента")
    for i, agent in enumerate(crew.get("agents", [])):
        base = f"agents[{i}]"
        if not agent.get("role"):
            err(f"{base}.role", "Не заполнена роль агента")
        if not agent.get("goal"):
            err(f"{base}.goal", "Не заполнена цель агента")
        if not agent.get("backstory"):
            err(f"{base}.backstory", "Не заполнено описание (backstory)")
        if tools_known is not None:
            for tool in agent.get("tools") or []:
                if tool in REMOVED_TOOLS:
                    err(f"{base}.tools", f"Инструмент «{tool}» отключён: {REMOVED_TOOLS[tool]}")
                elif tool in NETWORK_TOOL_NAMES and tool not in (allow_network or set()):
                    warn(
                        f"{base}.tools",
                        f"Инструмент «{tool}» — сторонний сетевой: включите его в настройках («Сетевые инструменты третьих сторон»)",
                    )
                elif tool not in tools_known:
                    warn(f"{base}.tools", f"Инструмент «{tool}» недоступен в этом окружении")
        requested_iter = _coerce_int(agent.get("max_iter"), AGENT_DEFAULTS["max_iter"])
        if requested_iter > 12:
            warn(
                f"{base}.max_iter",
                "Больше 12 итераций: агент может долго перебирать варианты и тратить токены. "
                "Жёсткий предел задаётся настройкой «Лимит итераций агента».",
            )
        agent_time = _coerce_int(agent.get("max_execution_time"), 0)
        if agent.get("confirm_changes") and 0 < agent_time <= 600:
            warn(
                f"{base}.max_execution_time",
                "Включено подтверждение изменений, а лимит времени задачи "
                f"{agent_time} с: пока вы отвечаете, задача может истечь и запрос закроется. "
                "Увеличьте «Макс. время» (например, 900) или поставьте 0.",
            )
        if agent.get("reasoning"):
            warn(f"{base}.reasoning", "Рассуждения добавляют отдельный запрос к модели на каждом шаге — запуск идёт медленнее")

    if not crew.get("tasks"):
        err("tasks", "Добавьте хотя бы одну задачу")
    agent_ids = {a.get("id") for a in crew.get("agents", [])}
    for i, task in enumerate(crew.get("tasks", [])):
        base = f"tasks[{i}]"
        if not task.get("description"):
            err(f"{base}.description", "Не заполнено описание задачи")
        if not task.get("expected_output"):
            err(f"{base}.expected_output", "Не заполнен ожидаемый результат")
        if crew.get("process") == "sequential":
            if not task.get("agent"):
                err(f"{base}.agent", "Выберите агента-исполнителя")
            elif task.get("agent") not in agent_ids:
                err(f"{base}.agent", "Агент задачи не найден")
        if task.get("human_input"):
            warn(
                f"{base}.human_input",
                "Флаг игнорируется: CrewAI запрашивает подтверждение только в консоли, в графическом интерфейсе это не поддерживается",
            )
        if task.get("output_format") == "file" and not task.get("output_file"):
            err(f"{base}.output_file", "Укажите имя файла результата")
        if task.get("output_format") == "file" and task.get("output_file"):
            raw = str(task["output_file"])
            if raw != Path(raw).name:
                err(
                    f"{base}.output_file",
                    "Укажите только имя файла: результат всегда пишется в рабочую область проекта",
                )

    if crew.get("process") == "hierarchical" and not (crew.get("manager_llm") or crew.get("default_llm")):
        warn("manager_llm", "Для иерархического процесса нужен менеджер (LLM менеджера или модель по умолчанию)")

    workspace_value = crew.get("workspace") or ""
    if workspace_value:
        from .workspace import resolve as resolve_workspace

        workspace_path = resolve_workspace(workspace_value, crew.get("id", ""))
        if workspace_path.exists() and not workspace_path.is_dir():
            err("workspace", "Рабочая область указывает на файл, а не на папку")
        elif not workspace_path.exists():
            warn("workspace", f"Папки «{workspace_path}» пока нет — она будет создана при сохранении")

    declared = [i.get("key") for i in crew.get("inputs", [])]
    for name in collect_placeholders(crew):
        if name not in declared:
            warnings.append(
                {
                    "field": "inputs",
                    "message": f"Плейсхолдер {{{name}}} не объявлен во «Входных данных» — он останется текстом как есть. "
                    f"Добавьте поле «{name}», если туда нужно подставлять значение.",
                }
            )
    for item in rejected or []:
        warnings.append(item)
    return {"ok": not errors, "errors": errors, "warnings": warnings, "placeholders": collect_placeholders(crew)}


def resolve_llm(spec_llm: str, crew_default: str, global_default: str) -> str:
    return normalize_model(spec_llm or crew_default or global_default or "")


def inputs_payload(crew: dict) -> dict[str, str]:
    return {i["key"]: i.get("value", "") for i in crew.get("inputs", []) if i.get("key")}


def _py(value: Any) -> str:
    return repr(value)


def to_python(crew: dict, global_default: str = "", llm_timeout: int = 120) -> str:
    """Render the specification as a standalone runnable Python script.

    Values are taken from the same normalised specification the runner uses, so
    the script cannot silently drift from what the GUI actually executes.
    """
    from .tools import BUILTIN_META, OPTIONAL_META

    timeout = int(llm_timeout or 120)
    network_tools = sorted(OPTIONAL_META)
    imports = ",\n        ".join(network_tools) if network_tools else ""
    tool_map = ", ".join(f"{name!r}: {name}" for name in network_tools)

    def tool_factory(name: str) -> str | None:
        if name in BUILTIN_META:
            return f"studio_tool({name!r})"
        if name in OPTIONAL_META:
            return f"crewai_tool({name!r})"
        return None

    lines: list[str] = [
        '"""Сгенерировано CrewAI Studio — можно запустить как обычный python-скрипт."""',
        "import os",
        "",
        "from crewai import Agent, Crew, LLM, Process, Task",
        "",
        "PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))",
        "WORKSPACE = os.path.join(PROJECT_DIR, 'workspace')",
        "os.makedirs(WORKSPACE, exist_ok=True)",
        "",
        "# Инструменты CrewAI Studio в этом скрипте не воспроизводятся автоматически:",
        "# подключите свои реализации или используйте приложение.",
        "# Подтверждения изменений (confirm_changes) действуют только в интерфейсе Studio.",
        "def studio_tool(name):",
        "    raise NotImplementedError(f'Инструмент {name} доступен только в CrewAI Studio')",
        "",
        "try:",
        f"    from crewai_tools import (\n        {imports})",
        "except Exception:",
        "    def crewai_tool(name):",
        "        raise NotImplementedError(f'Установите crewai-tools для {name}')",
        "else:",
        f"    _TOOLS = {{{tool_map}}}",
        "    def crewai_tool(name):",
        "        return _TOOLS[name]()",
        "",
    ]
    lines.append("agents = {}")
    for key, agent in enumerate(crew.get("agents", []), start=1):
        var = f"agent_{key}"
        llm = resolve_llm(agent.get("llm", ""), crew.get("default_llm", ""), global_default)
        lines.append(f"{var} = Agent(")
        lines.append(f"    role={_py(agent.get('role', ''))},")
        lines.append(f"    goal={_py(agent.get('goal', ''))},")
        lines.append(f"    backstory={_py(agent.get('backstory', ''))},")
        if llm:
            lines.append(f"    llm=LLM(model={_py(llm)}, timeout={int(timeout) or 120}),")
        if agent.get("allow_delegation"):
            lines.append("    allow_delegation=True,")
        lines.append(f"    max_iter={int(agent.get('max_iter') or 12)},")
        if crew.get("verbose") or agent.get("verbose"):
            lines.append("    verbose=True,")
        if int(agent.get("max_execution_time") or 0) > 0:
            lines.append(f"    max_execution_time={int(agent['max_execution_time'])},")
        if agent.get("reasoning"):
            lines.append("    reasoning=True,")
            lines.append(f"    max_reasoning_attempts={int(agent.get('max_reasoning_attempts') or 2)},")
        if agent.get("cache") is False:
            lines.append("    cache=False,")
        tool_calls = [call for call in (tool_factory(t) for t in (agent.get("tools") or [])) if call]
        if tool_calls:
            lines.append(f"    tools=[{', '.join(tool_calls)}],")
        lines.append(")")
        lines.append(f"agents[{_py(agent.get('id'))}] = {var}")
        lines.append("")

    lines.append("tasks = []")
    for key, task in enumerate(crew.get("tasks", []), start=1):
        var = f"task_{key}"
        lines.append(f"{var} = Task(")
        if task.get("name"):
            lines.append(f"    name={_py(task.get('name'))},")
        lines.append(f"    description={_py(task.get('description', ''))},")
        lines.append(f"    expected_output={_py(task.get('expected_output', ''))},")
        agent_var = None
        for idx, agent in enumerate(crew.get("agents", []), start=1):
            if agent.get("id") == task.get("agent"):
                agent_var = f"agent_{idx}"
                break
        if agent_var and crew.get("process") != "hierarchical":
            lines.append(f"    agent={agent_var},")
        if task.get("output_format") == "markdown":
            lines.append("    markdown=True,")
        if task.get("output_format") == "file" and task.get("output_file"):
            name = Path(str(task["output_file"])).name
            lines.append(f"    output_file=os.path.join(WORKSPACE, {_py(name)}),")
        if task.get("async_execution"):
            lines.append("    async_execution=True,")
        if task.get("human_input"):
            lines.append("    human_input=True,")
        lines.append(")")
        lines.append(f"tasks.append({var})")
        lines.append("")

    lines.append("crew = Crew(")
    lines.append(f"    agents=[{', '.join(f'agent_{i}' for i in range(1, len(crew.get('agents', [])) + 1))}],")
    lines.append(f"    tasks=tasks,")
    lines.append(f"    process=Process.{crew.get('process', 'sequential')},")
    if crew.get("process") == "hierarchical":
        manager = resolve_llm(crew.get("manager_llm", ""), crew.get("default_llm", ""), global_default)
        if manager:
            lines.append(f"    manager_llm={_py(manager)},")
    if crew.get("memory"):
        lines.append("    memory=True,")
    if crew.get("planning"):
        lines.append("    planning=True,")
    if int(crew.get("max_rpm") or 0) > 0:
        lines.append(f"    max_rpm={int(crew['max_rpm'])},")
    if crew.get("cache") is False:
        lines.append("    cache=False,")
    lines.append(f"    verbose={_py(bool(crew.get('verbose')))},")
    lines.append(")")
    lines.append("")
    inputs = inputs_payload(crew)
    lines.append(f"result = crew.kickoff(inputs={json_like(inputs)})")
    lines.append("print(result.raw)")
    return "\n".join(lines)


def json_like(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, indent=4)
