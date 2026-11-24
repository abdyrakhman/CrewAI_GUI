"""Role library: reusable role + goal + experience + character presets.

The GUI lets a user pick a role for an agent and have goal and backstory filled
in automatically, so the same role can be reused across projects and templates.
"""
from __future__ import annotations

import json
import re
import threading
import time
import uuid
from typing import Any

from .config import DATA_DIR

ROLES_FILE = DATA_DIR / "roles.json"
_lock = threading.RLock()

# Seeded on first use; the user can edit or delete any of them afterwards.
DEFAULT_ROLES: list[dict] = [
    {
        "id": "role-researcher",
        "name": "Исследователь",
        "goal": "Собрать проверенные факты по теме и отделить важное от второстепенного",
        "experience": "12 лет в аналитике и журналистике: работа с первоисточниками, интервью, фактчекинг.",
        "character": "Дотошный, не доверяет пересказам, любит цифры и не терпит воды.",
        "tools": ["fetch_url", "current_datetime"],
    },
    {
        "id": "role-analyst",
        "name": "Аналитик",
        "goal": "Превратить факты в структурированные выводы, риски и возможности",
        "experience": "Бывший стратег продуктовой команды: раскладывает тему на драйверы, риски и проверяемые шаги.",
        "character": "Спокойный, опирается на данные, избегает категоричных выводов без оснований.",
        "tools": ["current_datetime"],
    },
    {
        "id": "role-strategist",
        "name": "Стратег",
        "goal": "Определить угол подачи, приоритеты и план действий",
        "experience": "Строил стратегии для продуктов и медиа: сегменты, позиционирование, приоритизация.",
        "character": "Мыслит крупно, но требует, чтобы каждый вывод заканчивался действием.",
        "tools": [],
    },
    {
        "id": "role-writer",
        "name": "Автор",
        "goal": "Написать текст по плану живым и понятным языком",
        "experience": "Пишет статьи и лонгриды, которые дочитывают: короткие абзацы, примеры, честные ограничения.",
        "character": "Внимателен к ритму текста, ненавидит канцелярит и клише.",
        "tools": [],
    },
    {
        "id": "role-editor",
        "name": "Редактор",
        "goal": "Отредактировать текст: убрать воду, проверить логику и факты",
        "experience": "Требовательный редактор с опытом в журналистике: сокращает на 20% без потери смысла.",
        "character": "Прямолинейный, замечает противоречия, защищает читателя от лишней работы.",
        "tools": [],
    },
    {
        "id": "role-critic",
        "name": "Критик",
        "goal": "Найти слабые места решения и сформулировать возражения по существу",
        "experience": "Работал ревьюером и красной командой: ищет допущения, которые никто не проверял.",
        "character": "Скептичный, но конструктивный: к каждой претензии прикладывает вариант исправления.",
        "tools": [],
    },
    {
        "id": "role-architect",
        "name": "Архитектор",
        "goal": "Оценить архитектуру и риски решения",
        "experience": "Проектирует системы под нагрузку: границы модулей, состояние, ошибки, наблюдаемость.",
        "character": "Прагматичный, не любит преждевременных абстракций, думает о сопровождении.",
        "tools": [],
    },
    {
        "id": "role-developer",
        "name": "Разработчик",
        "goal": "Реализовать решение и объяснить ключевые технические компромиссы",
        "experience": "Пишет продакшн-код и умеет объяснять решения без жаргона.",
        "character": "Аккуратный, предпочитает простое рабочее решение сложному красивому.",
        "tools": ["read_local_file", "write_local_file"],
    },
    {
        "id": "role-qa",
        "name": "Тестировщик",
        "goal": "Составить план проверки и найти граничные случаи",
        "experience": "Ломает системы намеренно: пустые значения, гонки, таймауты, большие объёмы.",
        "character": "Методичный, описывает ожидаемый результат до проверки.",
        "tools": [],
    },
    {
        "id": "role-marketer",
        "name": "Маркетолог",
        "goal": "Сформулировать ценность продукта и каналы продвижения",
        "experience": "Запускал кампании в B2B и B2C: сегменты, офферы, воронки, метрики.",
        "character": "Ориентирован на результат, считает стоимость лида и не верит в «виральность».",
        "tools": [],
    },
    {
        "id": "role-support",
        "name": "Специалист поддержки",
        "goal": "Разобрать обращение и дать ответ, после которого не пишут второй раз",
        "experience": "Работает в поддержке SaaS: признаёт проблему, даёт шаги и срок.",
        "character": "Вежливый и конкретный, не обещает того, что не может выполнить.",
        "tools": [],
    },
    {
        "id": "role-pm",
        "name": "Менеджер проекта",
        "goal": "Собрать план, назначить ответственных и отследить риски",
        "experience": "Ведёт несколько команд: декомпозиция, зависимости, срезы статуса.",
        "character": "Структурный, любит явные сроки и владельцев задач.",
        "tools": [],
    },
]


def _normalize(role: dict, index: int = 0) -> dict:
    tools = role.get("tools") or []
    if isinstance(tools, str):
        tools = [t.strip() for t in tools.split(",") if t.strip()]
    return {
        "id": str(role.get("id") or f"role-{uuid.uuid4().hex[:8]}"),
        "name": str(role.get("name") or f"Роль {index + 1}").strip(),
        "goal": str(role.get("goal") or "").strip(),
        "experience": str(role.get("experience") or "").strip(),
        "character": str(role.get("character") or "").strip(),
        "tools": [str(t) for t in tools if str(t).strip()],
        "updated_at": role.get("updated_at") or time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


def backstory(role: dict) -> str:
    """Compose the agent backstory CrewAI uses from experience + character."""
    parts = [str(role.get("experience") or "").strip(), str(role.get("character") or "").strip()]
    return " ".join(part for part in parts if part)


def _write(roles: list[dict]) -> None:
    ROLES_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = ROLES_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"roles": roles}, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(ROLES_FILE)


def load_roles() -> list[dict]:
    """Read roles, seeding the defaults on first use."""
    with _lock:
        if not ROLES_FILE.exists():
            roles = [_normalize(dict(r), i) for i, r in enumerate(DEFAULT_ROLES)]
            _write(roles)
            return roles
        try:
            data = json.loads(ROLES_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return [_normalize(dict(r), i) for i, r in enumerate(DEFAULT_ROLES)]
        raw = data.get("roles") if isinstance(data, dict) else data
        if not isinstance(raw, list):
            return []
        return [_normalize(role, index) for index, role in enumerate(raw) if isinstance(role, dict)]


def save_roles(roles: list[dict]) -> list[dict]:
    with _lock:
        cleaned = [_normalize(role, index) for index, role in enumerate(roles)]
        _write(cleaned)
        return cleaned


def find_role(role_id: str) -> dict | None:
    for role in load_roles():
        if role["id"] == role_id:
            return role
    return None


def find_role_by_name(name: str) -> dict | None:
    target = (name or "").strip().lower()
    for role in load_roles():
        if role["name"].strip().lower() == target:
            return role
    return None


def create_role(payload: dict) -> dict:
    with _lock:
        if not str(payload.get("name") or "").strip():
            raise ValueError("Укажите название роли")
        roles = load_roles()
        role = _normalize({**payload, "id": f"role-{uuid.uuid4().hex[:8]}"}, len(roles))
        roles.append(role)
        save_roles(roles)
        return role


def update_role(role_id: str, payload: dict) -> dict:
    with _lock:
        if "name" in payload and not str(payload.get("name") or "").strip():
            raise ValueError("Укажите название роли")
        roles = load_roles()
        for index, role in enumerate(roles):
            if role["id"] == role_id:
                merged = _normalize({**role, **payload, "id": role_id}, index)
                roles[index] = merged
                save_roles(roles)
                return merged
    raise KeyError("Роль не найдена")


def delete_role(role_id: str) -> bool:
    with _lock:
        roles = load_roles()
        remaining = [role for role in roles if role["id"] != role_id]
        if len(remaining) == len(roles):
            return False
        save_roles(remaining)
        return True


def reset_roles() -> list[dict]:
    with _lock:
        roles = [_normalize(dict(r), i) for i, r in enumerate(DEFAULT_ROLES)]
        _write(roles)
        return roles


def apply_to_agent(role: dict, agent: dict, merge_tools: bool = True) -> dict:
    """Fill an agent specification from a role preset."""
    updated = dict(agent)
    updated["role"] = role.get("name") or updated.get("role", "")
    updated["goal"] = role.get("goal") or updated.get("goal", "")
    composed = backstory(role)
    if composed:
        updated["backstory"] = composed
    if merge_tools:
        tools = list(updated.get("tools") or [])
        for tool in role.get("tools") or []:
            if tool not in tools:
                tools.append(tool)
        updated["tools"] = tools
    updated["role_id"] = role.get("id", "")
    return updated


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
