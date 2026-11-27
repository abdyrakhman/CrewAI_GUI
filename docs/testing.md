# Тесты

Наборы не тратят токены: вместо провайдера поднимается локальный OpenAI-совместимый сервер
`tests/mock_llm.py`. Браузерным тестам нужен установленный Chrome и `playwright`.

Все наборы изолированы: создают свою папку `CREWAI_STUDIO_DATA` в `.setup/`, поэтому не трогают ваши
проекты и настройки. Исключение — `test_auth.py`: он работает с настоящими аккаунтами и сессиями
во временной папке. Остальные наборы выставляют `CREWAI_STUDIO_NO_AUTH=1`, чтобы не логиниться в каждом.

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
.venv\Scripts\python.exe tests\test_auth.py
.venv\Scripts\python.exe tests\test_export_import.py
.venv\Scripts\python.exe tests\test_human_flag.py
.venv\Scripts\python.exe tests\test_runs_pagination.py
.venv\Scripts\python.exe tests\test_run_limits.py
.venv\Scripts\python.exe tests\test_logs_api.py
.venv\Scripts\python.exe tests\test_installer.py
.venv\Scripts\python.exe tests\test_docs.py

:: браузерные (Chrome + playwright)
.venv\Scripts\python.exe tests\test_ui.py
.venv\Scripts\python.exe tests\test_ui_features.py
.venv\Scripts\python.exe tests\test_ui_workspace.py
.venv\Scripts\python.exe tests\test_ui_confirmations.py
.venv\Scripts\python.exe tests\test_ui_i18n.py
.venv\Scripts\python.exe tests\test_ui_auth_i18n.py
```

Каждый печатает строки `PASS`/`FAIL` и итог `… RESULT: PASS`. Код возврата `0` — успех, `1` — есть падения.
Всего 24 набора.

## Что покрывает каждый набор

| Набор | Проверяет |
|---|---|
| `test_runner_e2e.py` | полный путь: спека → объекты CrewAI → event bus → снимок; токены, задачи, события без сырых чанков |
| `test_http_api.py` | REST-контракт, SSE, история, экспорт, статика; SSE несёт шаги агента |
| `test_features_api.py` | роли (CRUD, применение), шаблоны и их редактирование, дублирование/удаление проектов, код |
| `test_workspace_api.py` | рабочая область, проводник, разрешённые корни, загрузка файлов |
| `test_permissions_api.py` | запросы доступа, гранты, таймаут, отказ, `pending_permissions`, шифрование ключей |
| `test_tools_install.py` | установка `crewai-tools`, каталог, статусы |
| `test_cancel.py` | отмена, watchdog, лимиты, осиротевшие запуски, память без эмбеддингов |
| `test_hardening.py` | traversal, периметр (Host/Origin/токен/CSRF), песочница, env allow-list, второй экземпляр, лимит загрузки |
| `test_round4.py` | рабочая область при загрузке, сетевые инструменты, env, «Код», гранты, отсоединённый прогон |
| `test_braced_text.py` | текст с `{id}` в описании задачи не ломает реальный прогон |
| `test_auth.py` | вход, обязательная смена пароля, лимит попыток, регистрация, сброс сессий, смена пароля |
| `test_export_import.py` | экспорт/импорт проекта, ZIP-бэкап без логов и сессий, отсутствие ролей у аккаунтов |
| `test_human_flag.py` | проект с устаревшим флагом `human_input` запускается и не виснет |
| `test_runs_pagination.py` | пагинация истории, фильтры, retention и удаление старых запусков |
| `test_run_limits.py` | лимит времени прогона, предел итераций агента, нормализация настроек |
| `test_logs_api.py` | журнал `/api/logs/recent`, редакция секретов, модалки диагностики |
| `test_installer.py` | синтаксис `install.ps1`, параметры, отсутствие пароля по умолчанию, состав копируемых файлов |
| `test_docs.py` | тесты перечислены в документации, счётчики совпадают, ссылки и пары RU/EN корректны |
| `test_ui.py` | интерфейс: создание проекта, запуск, результат, отмена |
| `test_ui_features.py` | роли, шаблоны, удаление проектов |
| `test_ui_workspace.py` | выбор рабочей области, сброс, ошибки пути |
| `test_ui_confirmations.py` | окно подтверждения, «до конца запуска», фон, закрытие по Esc и возврат к запросу |
| `test_ui_i18n.py` | переключение языка RU/EN и сохранение выбора |
| `test_ui_auth_i18n.py` | язык страниц входа и смены пароля (RU/EN) |

## Как устроены тесты

- **Мок-модель.** `MockLLMServer` отвечает в формате OpenAI, умеет задерживать ответ. Порт задаётся в наборе.
- **Изоляция.** `CREWAI_STUDIO_DATA` указывает на `.setup/<prefix>-<hex>`; после прогона папку можно удалить.
- **Браузер.** Playwright запускает установленный Chrome (`channel="chrome"`, headless).
- **Без сетевых вызовов** к провайдерам: base URL указывает на мок.

## Добавить тест

1. Скопируйте структуру любого набора: изолированная папка, `check()`-хелпер, итог `RESULT`.
2. Для API — поднимите `create_server("127.0.0.1", <порт>)`, GET-запросы не требуют токена,
   изменяющие — заголовок `X-Studio-Token` из мета-тега страницы.
3. Для сценария с моделью — `MockLLMServer` и настройка `openai_base_url` на него.
4. Назовите файл `test_<тема>.py` и добавьте строку в README и в этот документ.
