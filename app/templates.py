"""Ready-to-run crew templates shown in the «Шаблоны» section."""
from __future__ import annotations

import json
import re
import time
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any

from .config import DATA_DIR
from .spec import normalize_crew
from .store import new_id

_BASE = {
    "process": "sequential",
    "manager_llm": "",
    "default_llm": "",
    "verbose": False,
    "memory": False,
    "cache": True,
    "max_rpm": 0,
    "planning": False,
}


def _crew(name: str, description: str, agents: list[dict], tasks: list[dict], inputs: list[dict], **extra) -> dict:
    payload = deepcopy(_BASE)
    payload.update({"name": name, "description": description, "agents": agents, "tasks": tasks, "inputs": inputs})
    payload.update(extra)
    return payload


def _agent(role: str, goal: str, backstory: str, tools: list[str] | None = None, **kw) -> dict:
    return {
        "id": new_id("a-"),
        "role": role,
        "goal": goal,
        "backstory": backstory,
        "llm": "",
        "tools": tools or [],
        "allow_delegation": kw.get("allow_delegation", False),
        "max_iter": kw.get("max_iter", 12),
        "reasoning": kw.get("reasoning", False),
        "cache": True,
        "verbose": False,
    }


def _task(name: str, description: str, expected: str, agent_index: int, context: list[int] | None = None, **kw) -> dict:
    return {
        "id": new_id("t-"),
        "name": name,
        "description": description,
        "expected_output": expected,
        "agent": f"__agent_{agent_index}__",
        "context": [f"__task_{i}__" for i in (context or [])],
        "async_execution": kw.get("async_execution", False),
        "human_input": kw.get("human_input", False),
        "output_format": kw.get("output_format", "markdown"),
        "output_file": kw.get("output_file", ""),
        "tools": kw.get("tools", []),
    }


def _link(crew: dict) -> dict:
    """Replace the __agent_N__/__task_N__ placeholders with real ids."""
    agent_ids = [a["id"] for a in crew["agents"]]
    task_ids = [t["id"] for t in crew["tasks"]]
    for task in crew["tasks"]:
        agent = task["agent"]
        if isinstance(agent, str) and agent.startswith("__agent_"):
            index = int(agent.removeprefix("__agent_").removesuffix("__"))
            task["agent"] = agent_ids[index] if index < len(agent_ids) else ""
        task["context"] = [
            task_ids[int(c.removeprefix("__task_").removesuffix("__"))]
            for c in task.get("context", [])
            if c.startswith("__task_")
        ]
    return crew


def research_brief() -> dict:
    agents = [
        _agent(
            "Старший исследователь",
            "Собрать проверенные факты по теме «{topic}» и отделить важное от второстепенного",
            "Вы 12 лет работаете аналитиком в консалтинге и умеете находить первоисточники, "
            "а не пересказы. Любите цифры и не терпите воды.",
            tools=["fetch_url", "current_datetime"],
        ),
        _agent(
            "Аналитик-стратег",
            "Превратить факты в структурированные выводы, риски и возможности",
            "Вы бывший стратег продуктовой команды: раскладываете любую тему на драйверы, "
            "риски и следующие шаги, которые можно проверить.",
            tools=["current_datetime"],
        ),
        _agent(
            "Бизнес-редактор",
            "Написать короткий и ясный бриф для руководителя",
            "Вы пишете для занятых людей: сначала вывод, потом аргументы. Ни одного лишнего слова, "
            "только польза для решения.",
        ),
    ]
    tasks = [
        _task(
            "Сбор фактов",
            "Изучи тему «{topic}». Составь список из 8–12 ключевых фактов: что происходит, кто участники, "
            "какие цифры и даты известны. Для каждого факта укажи, насколько он надёжен и откуда взят. "
            "Если чего-то не хватает — честно перечисли пробелы в данных.",
            "Маркированный список фактов с оценкой надёжности и открытыми вопросами.",
            0,
        ),
        _task(
            "Анализ и выводы",
            "На основе фактов сделай анализ: 3 главных драйвера, 3 риска, 2 возможности. "
            "Для каждого пункта — короткое обоснование и индикатор, за которым стоит следить.",
            "Таблица «драйверы / риски / возможности» с обоснованием и индикаторами.",
            1,
            context=[0],
        ),
        _task(
            "Итоговый бриф",
            "Собери бриф для руководителя: 1 абзац сути, 3 вывода, 3 рекомендованных действия с приоритетом, "
            "и раздел «что мы пока не знаем». Объём — до 500 слов, деловой тон, без вступлений.",
            "Готовый бриф в Markdown: суть, выводы, действия, открытые вопросы.",
            2,
            context=[0, 1],
            output_file="brief.md",
        ),
    ]
    return _link(
        _crew(
            "Исследование темы → бриф",
            "Последовательная команда: исследователь собирает факты, аналитик делает выводы, редактор пишет бриф.",
            agents,
            tasks,
            [{"key": "topic", "value": "Искусственный интеллект в среднем бизнесе", "description": "Тема исследования"}],
        )
    )


def blog_post() -> dict:
    agents = [
        _agent(
            "Контент-стратег",
            "Определить угол подачи и структуру статьи по теме «{topic}»",
            "Вы ведёте контент-стратегию в B2B-медиа и знаете, что читают до конца: "
            "конкретика, истории, отсутствие общих слов.",
        ),
        _agent(
            "Автор",
            "Написать статью по утверждённому плану, живым языком",
            "Вы пишете статьи, которые цитируют: короткие абзацы, примеры, честные ограничения.",
        ),
        _agent(
            "Редактор",
            "Отредактировать текст: убрать воду, проверить логику и факты, улучшить заголовок",
            "Вы требовательный редактор с опытом в журналистике. Сокращаете на 20% без потери смысла.",
        ),
    ]
    tasks = [
        _task(
            "План статьи",
            "Тема: «{topic}». Придумай 3 варианта угла подачи, выбери лучший и обоснуй. "
            "Составь план: заголовок, лид, 4–6 разделов с тезисами, вывод, призыв к действию. "
            "Аудитория — практики, которым нужны решения, а не теория.",
            "План статьи с выбранным углом, тезисами разделов и целевой аудиторией.",
            0,
        ),
        _task(
            "Черновик",
            "Напиши статью по плану. Объём 900–1200 слов. Каждый раздел — минимум один конкретный пример. "
            "Избегай канцелярита и клише, не выдумывай статистику: если данных нет, пиши качественные оценки.",
            "Полный черновик статьи в Markdown.",
            1,
            context=[0],
        ),
        _task(
            "Редактура",
            "Отредактируй статью: сократи минимум на 15%, усиль заголовок и подзаголовки, "
            "проверь связность и отсутствие выдуманных фактов. Верни финальный текст и список правок.",
            "Финальная статья в Markdown + краткий список внесённых правок.",
            2,
            context=[0, 1],
            output_file="article.md",
        ),
    ]
    return _link(
        _crew(
            "Статья для блога",
            "Стратег придумывает план, автор пишет черновик, редактор доводит текст до публикации.",
            agents,
            tasks,
            [{"key": "topic", "value": "Как автоматизировать отчётность с помощью ИИ-агентов", "description": "Тема статьи"}],
        )
    )


def code_review() -> dict:
    agents = [
        _agent(
            "Архитектор",
            "Оценить архитектуру и риски кода: «{task}»",
            "Вы проектируете системы под нагрузку и знаете, где обычно рвётся: границы модулей, "
            "состояние, ошибки, наблюдаемость.",
        ),
        _agent(
            "Ревьюер кода",
            "Найти конкретные дефекты и предложить правки с примерами",
            "Вы ревьюите десятки PR в неделю. Замечания формулируете как «что не так → почему важно → как исправить».",
        ),
        _agent(
            "Инженер по тестам",
            "Составить план проверки и список тест-кейсов, включая граничные случаи",
            "Вы ломаете системы намеренно: пустые значения, гонки, таймауты, большие объёмы.",
        ),
    ]
    tasks = [
        _task(
            "Архитектурная оценка",
            "Задача: {task}. Код или описание: {code}. Оцени архитектуру: границы, зависимости, "
            "потоки данных, узкие места, риски сопровождения. Дай 3–5 выводов с приоритетом.",
            "Список архитектурных наблюдений с приоритетами и обоснованием.",
            1,
        ),
        _task(
            "Поиск дефектов",
            "Найди конкретные проблемы в коде: ошибки, утечки, необработанные исключения, "
            "проблемы безопасности и читаемости. Для каждого пункта — строка/фрагмент, риск, исправление.",
            "Список дефектов в формате «проблема → риск → исправление».",
            1,
            context=[0],
        ),
        _task(
            "План тестирования",
            "Составь план проверки: unit, интеграционные, граничные случаи, негативные сценарии. "
            "Оформи как чек-лист с ожидаемым результатом.",
            "Чек-лист тест-кейсов с ожидаемыми результатами.",
            2,
            context=[0, 1],
            output_format="markdown",
        ),
    ]
    return _link(
        _crew(
            "Ревью кода",
            "Архитектор оценивает решение, ревьюер ищет дефекты, инженер по тестам готовит план проверки.",
            agents,
            tasks,
            [
                {"key": "task", "value": "Проверить сервис обработки заказов", "description": "Что проверяем"},
                {"key": "code", "value": "Вставьте сюда код или ссылку на репозиторий", "description": "Код или описание"},
            ],
        )
    )


def support_triage() -> dict:
    agents = [
        _agent(
            "Классификатор обращений",
            "Разобрать обращение клиента «{message}» и определить тип, срочность и эмоцию",
            "Вы работаете в поддержке SaaS и с первого абзаца понимаете, что на самом деле нужно клиенту.",
        ),
        _agent(
            "Специалист поддержки",
            "Подготовить ответ клиенту и внутреннюю заметку для команды",
            "Вы отвечаете так, чтобы клиент не писал второй раз: признаёте проблему, даёте шаги, ставите срок.",
        ),
    ]
    tasks = [
        _task(
            "Разбор обращения",
            "Обращение: «{message}». Определи: тип (баг / вопрос / оплата / доработка / другое), "
            "срочность (P1–P4), эмоциональный фон, чего клиент хочет на самом деле, каких данных не хватает.",
            "Карточка обращения: тип, срочность, эмоция, скрытая потребность, недостающие данные.",
            0,
        ),
        _task(
            "Ответ и заметка",
            "Напиши ответ клиенту (вежливо, по делу, с шагами и сроком) и внутреннюю заметку: "
            "что проверить, кому передать, какой риск эскалации.",
            "Ответ клиенту + внутренняя заметка для команды.",
            1,
            context=[0],
        ),
    ]
    return _link(
        _crew(
            "Разбор обращений в поддержку",
            "Классификатор разбирает обращение, специалист готовит ответ и внутреннюю заметку.",
            agents,
            tasks,
            [
                {
                    "key": "message",
                    "value": "Здравствуйте! После обновления отчёты перестали выгружаться в Excel, "
                    "а нам завтра сдавать цифры руководству. Срочно!",
                    "description": "Текст обращения клиента",
                }
            ],
        )
    )


TEMPLATES: dict[str, dict] = {
    "research-brief": {
        "key": "research-brief",
        "title": "Исследование → бриф",
        "subtitle": "3 агента · последовательно",
        "description": "Исследователь собирает факты, аналитик делает выводы, редактор пишет бриф руководителю.",
        "badge": "Популярное",
        "build": research_brief,
    },
    "blog-post": {
        "key": "blog-post",
        "title": "Статья для блога",
        "subtitle": "3 агента · последовательно",
        "description": "Стратег, автор и редактор превращают тему в готовую статью с редактурой.",
        "badge": "",
        "build": blog_post,
    },
    "code-review": {
        "key": "code-review",
        "title": "Ревью кода",
        "subtitle": "3 агента · последовательно",
        "description": "Архитектурная оценка, поиск дефектов и план тестирования одним запуском.",
        "badge": "",
        "build": code_review,
    },
    "support-triage": {
        "key": "support-triage",
        "title": "Разбор обращений",
        "subtitle": "2 агента · последовательно",
        "description": "Классификация обращения, срочность и готовый ответ клиенту.",
        "badge": "",
        "build": support_triage,
    },
}


TEMPLATES_DIR: Path = DATA_DIR / "templates"


def _plural(count: int, forms: tuple[str, str, str]) -> str:
    n = abs(int(count or 0))
    tail, digit = n % 100, n % 10
    if 10 < tail < 20:
        return forms[2]
    if 1 < digit < 5:
        return forms[1]
    if digit == 1:
        return forms[0]
    return forms[2]


def _subtitle(crew: dict) -> str:
    agents = len(crew.get("agents") or [])
    tasks = len(crew.get("tasks") or [])
    return f"{agents} {_plural(agents, ('агент', 'агента', 'агентов'))} · {tasks} {_plural(tasks, ('задача', 'задачи', 'задач'))}"


def _custom_path(key: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", key or ""):
        raise ValueError("incorrect template id")
    return TEMPLATES_DIR / f"{key}.json"


def _load_custom() -> list[dict]:
    if not TEMPLATES_DIR.exists():
        return []
    entries: list[dict] = []
    for path in sorted(TEMPLATES_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict) and data.get("key") and isinstance(data.get("crew"), dict):
            entries.append(data)
    entries.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return entries


def save_custom_template(crew: dict, title: str, description: str = "") -> dict:
    """Store a copy of a project as a reusable template."""
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    spec = normalize_crew(deepcopy(crew))
    spec.pop("id", None)
    spec.pop("created_at", None)
    spec.pop("updated_at", None)
    # Templates must not carry a workspace: it belongs to the project, not the template.
    spec["workspace"] = ""
    key = f"tpl-{uuid.uuid4().hex[:8]}"
    entry = {
        "key": key,
        "title": (title or spec.get("name") or "Мой шаблон").strip()[:120],
        "description": (description or spec.get("description") or "").strip()[:400],
        "subtitle": _subtitle(spec),
        "badge": "мой",
        "custom": True,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "crew": spec,
    }
    path = _custom_path(key)
    path.write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")
    return entry


def delete_custom_template(key: str) -> bool:
    try:
        path = _custom_path(key)
    except ValueError:
        return False
    if not path.exists():
        return False
    path.unlink()
    return True


def update_custom_template(key: str, title: str, description: str | None = None) -> dict | None:
    try:
        path = _custom_path(key)
    except ValueError:
        return None
    if not path.exists():
        return None
    try:
        entry = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if title:
        entry["title"] = title.strip()[:120]
    if description is not None:
        entry["description"] = description.strip()[:400]
    entry["subtitle"] = _subtitle(normalize_crew(entry.get("crew") or {}))
    path.write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")
    return entry


def list_templates() -> list[dict]:
    custom = [
        {
            "key": entry["key"],
            "title": entry.get("title", "Мой шаблон"),
            "subtitle": entry.get("subtitle", ""),
            "description": entry.get("description", ""),
            "badge": entry.get("badge", ""),
            "custom": True,
        }
        for entry in _load_custom()
    ]
    builtin = [
        {
            "key": key,
            "title": value["title"],
            "subtitle": value["subtitle"],
            "description": value["description"],
            "badge": value["badge"],
            "custom": False,
        }
        for key, value in TEMPLATES.items()
    ]
    return custom + builtin


def build_template(key: str) -> dict:
    if key in TEMPLATES:
        return TEMPLATES[key]["build"]()
    for entry in _load_custom():
        if entry["key"] == key:
            crew = normalize_crew(deepcopy(entry["crew"]))
            crew.pop("id", None)
            crew["name"] = entry.get("title") or crew.get("name") or "Мой шаблон"
            crew["description"] = entry.get("description") or crew.get("description", "")
            return crew
    raise KeyError(f"Шаблон не найден: {key}")


def custom_template_exists(key: str) -> bool:
    try:
        return _custom_path(key).exists()
    except ValueError:
        return False


def template_payload(key: str) -> dict[str, Any] | None:
    for entry in _load_custom():
        if entry["key"] == key:
            return entry
    return None
