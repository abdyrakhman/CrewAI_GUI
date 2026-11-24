# Тесты

Наборы не тратят токены: вместо провайдера поднимается локальный OpenAI-совместимый
сервер `tests/mock_llm.py`. Браузерным тестам нужен установленный Chrome и
`playwright` (он уже входит в зависимости разработки; при необходимости
`pip install playwright`).

Все наборы изолированы: создают свою папку `CREWAI_STUDIO_DATA` в `.setup/`, поэтому
не трогают ваши проекты и настройки.

## Запуск

```bat
:: серверные
.venv\Scripts\python.exe tests\test_runner_e2e.py
.venv\Scripts\python.exe tests\test_http_api.py
.venv\Scripts\python.exe tests\test_features_api.py
.venv\Scripts\python.exe tests\test_workspace_api.py
.venv\Scripts\python.exe tests\test_permissions_api.py
.venv\Scripts\python.exe tests\test_tools_install.py
.venv\Scripts\python.exe tests\test_cancel.py
.venv\Scripts\python.exe tests\test_hardening.py
.venv\Scripts\python.exe tests\test_round4.py
.venv\Scripts\python.exe tests\test_braced_text.py

:: браузерные
.venv\Scripts\python.exe tests\test_ui.py
.venv\Scripts\python.exe tests\test_ui_features.py
.venv\Scripts\python.exe tests\test_ui_workspace.py
.venv\Scripts\python.exe tests\test_ui_confirmations.py
```

Каждый печатает строки `PASS`/`FAIL` и итог `… RESULT: PASS`. Код возврата `0` —
успех, `1` — есть падения.

## Что покрывает каждый набор

| Набор | Проверяет |
|---|---|
| `test_runner_e2e.py` | полный путь: спека → объекты CrewAI → event bus → сохранённый снимок; токены, задачи, стриминг |
| `test_http_api.py` | REST-контракт, SSE, история, экспорт, статика |
| `test_features_api.py` | роли (CRUD, применение), шаблоны, дублирование и удаление проектов, генерация кода |
| `test_workspace_api.py` | рабочая область, проводник, разрешённые корни, загрузка файлов |
| `test_permissions_api.py` | запросы доступа, гранты, таймаут, отказ, шифрование ключей |
| `test_tools_install.py` | установка `crewai-tools`, каталог, статусы |
| `test_cancel.py` | отмена, watchdog, лимиты, осиротевшие запуски, память без эмбеддингов |
| `test_hardening.py` | traversal (9 вариантов), периметр (Host/Origin/токен/CSRF), песочница, env allow-list, пин pip, паритет кода, скорость индекса |
| `test_round4.py` | R-1…R-8: рабочая область при загрузке, сетевые инструменты, env, «Код», гранты, служебные каталоги, отсоединённый прогон, терминальные статусы |
| `test_braced_text.py` | текст с `{id}` в описании задачи не ломает реальный прогон |
| `test_ui.py` | интерфейс: создание проекта, запуск, живой вывод, отмена |
| `test_ui_features.py` | роли, шаблоны, удаление проектов |
| `test_ui_workspace.py` | выбор рабочей области, сброс, ошибки пути |
| `test_ui_confirmations.py` | окно подтверждения, «до конца запуска», фоновый запуск |

## Как устроены тесты

- **Мок-модель.** `MockLLMServer` отвечает в формате OpenAI, умеет задерживать
  ответ и отдавать поток. Порт задаётся в каждом наборе.
- **Изоляция.** `CREWAI_STUDIO_DATA` указывает на `.setup/<prefix>-<hex>`; после
  прогона папку можно удалить.
- **Браузер.** Playwright запускает установленный Chrome
  (`channel="chrome"`, headless). Если Chrome не найден — набор упадёт с понятной
  ошибкой.
- **Никаких сетевых вызовов** к провайдерам: base URL указывает на мок.

## Добавить тест

1. Скопируйте структуру любого набора: изолированная папка, `check()`-хелпер,
   итог `RESULT`.
2. Для API — поднимите `create_server("127.0.0.1", <порт>)` и возьмите токен из
   `server.RequestHandlerClass.session_token`.
3. Для сценария с моделью — `MockLLMServer` и настройки `openai_base_url` на него.
4. Назовите файл `test_<тема>.py` и добавьте строку в README и в этот документ.
