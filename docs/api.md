# REST API

Интерфейс общается с сервером по HTTP/1.1 на `http://127.0.0.1:<порт>`. Все ответы —
JSON (кроме статики, SSE и экспорта). Тот же API доступен программно: этого достаточно,
чтобы автоматизировать запуски или встроить Studio в другой инструмент.

## Периметр

| Проверка | Правило |
|---|---|
| `Host` | только `127.0.0.1:<порт>`, `localhost:<порт>`, `[::1]:<порт>` |
| `Origin` | если передан — должен совпадать с разрешённым хостом |
| Токен | все `POST`/`PUT`/`DELETE` требуют заголовок `X-Studio-Token` |
| `Content-Type` | при непустом теле — `application/json` |
| Размер тела | не больше 64 МБ |
| `Transfer-Encoding` | chunked не поддерживается, нужен `Content-Length` |
| CORS | заголовков нет, кросс-доменные запросы не работают |

Токен печатается в HTML-страницу:

```html
<meta name="studio-token" content="…">
```

Он меняется при каждом перезапуске сервера. Пример вызова:

```bash
TOKEN=$(curl -s http://127.0.0.1:7860/ | grep -o 'studio-token" content="[^"]*' | cut -d'"' -f3)
curl -s http://127.0.0.1:7860/api/crews -H "X-Studio-Token: $TOKEN"
```

```powershell
$page  = Invoke-WebRequest 'http://127.0.0.1:7860/' -UseBasicParsing
$token = [regex]::Match($page.Content, 'studio-token" content="([^"]+)"').Groups[1].Value
$h = @{ 'X-Studio-Token' = $token; 'Content-Type' = 'application/json' }
Invoke-RestMethod 'http://127.0.0.1:7860/api/crews' -Headers $h
```

## Авторизация

Интерфейс закрыт паролем. Все эндпоинты, кроме перечисленных ниже, требуют сессию: без неё
`401 {"auth": true}`; пока не выполнена обязательная смена пароля — `403 {"password_change_required": true}`.

| Метод | Путь | Тело | Ответ |
|---|---|---|---|
| GET | `/api/auth/state` | — | `{has_users, user}` |
| POST | `/api/auth/login` | `{username, password}` | `{user, must_change}` + `Set-Cookie` |
| POST | `/api/auth/register` | `{username, password}` | `201 {user, must_change}` + `Set-Cookie` |
| POST | `/api/auth/logout` | — | `{ok}` и сброс cookie |
| POST | `/api/auth/logout-all` | — | `{ok, dropped_sessions}` — завершает все сессии пользователя |
| GET | `/api/auth/me` | — | `{user}` или 401 |
| POST | `/api/auth/password` | `{current, new}` | `{ok, dropped_sessions}`; нужна сессия, остальные сессии закрываются |

Сессия — cookie `studio_session` (HttpOnly, SameSite=Lax); срок задаётся настройкой `session_ttl_hours`.
Изменяющие запросы дополнительно требуют `X-Studio-Token` (он в мета-теге страницы), кроме `/api/auth/*`.

## Коды ошибок

| Код | Когда |
|---|---|
| `400` | некорректные данные запроса |
| `403` | неверный `Host`/`Origin`, нет токена, путь вне разрешённых |
| `404` | объект не найден |
| `409` | уже идёт запуск, битый проект, повторный ответ на запрос доступа |
| `411` | chunked-тело |
| `413` | тело больше лимита |
| `415` | не `application/json` |
| `422` | проект не прошёл проверку, частичный `PUT`, код не сгенерирован |
| `500` | внутренняя ошибка; в ответе `error_id`, детали — в `data/logs` |

## Служебные

| Метод | Путь | Ответ |
|---|---|---|
| `GET` | `/api/info` | версия приложения, статус CrewAI, настройки (без секретов), провайдеры |
| `GET` | `/api/status` | занятость слота, активный запуск, превью окружения |

## Проекты

| Метод | Путь | Тело | Ответ |
|---|---|---|---|
| `GET` | `/api/crews` | — | `{"crews":[…],"broken":[…]}` |
| `POST` | `/api/crews` | `{"crew":{…}}` или `{"template":"tpl-…"}` | `201 {"crew":…,"rejected":[…]}` |
| `GET` | `/api/crews/{id}` | — | `{"crew":…,"validation":…,"workspace":…}` |
| `PUT` | `/api/crews/{id}` | `{"crew":{…}}` — **целиком** | `{"crew":…,"rejected":[…],"validation":…}` |
| `DELETE` | `/api/crews/{id}` | — | `{"ok":true}` |
| `POST` | `/api/crews/{id}/duplicate` | — | `201 {"crew":…}` |
| `POST` | `/api/crews/{id}/validate` | `{"crew":…}` (необязательно) | `{"ok":…,"errors":…,"warnings":…}` |
| `GET` | `/api/crews/{id}/code` | — | `{"code":"…","warnings":[…]}` или `422` |

`PUT` без `agents` и `tasks` отклоняется: частичное тело затёрло бы проект.

Минимальный проект:

```json
{
  "crew": {
    "name": "Разбор отзыва",
    "default_llm": "deepseek/deepseek-chat",
    "agents": [
      {"role": "Аналитик", "goal": "Найти причину", "backstory": "Опытный аналитик", "max_iter": 8}
    ],
    "tasks": [
      {"name": "Анализ", "description": "Разбери отзыв: {review}", "expected_output": "Список причин"}
    ],
    "inputs": [{"key": "review", "label": "Отзыв", "default": ""}]
  }
}
```

## Рабочая область

| Метод | Путь | Тело | Ответ |
|---|---|---|---|
| `GET` | `/api/crews/{id}/workspace` | — | `{"workspace":{"path","is_default","exists","writable","note",…}}` |
| `PUT/POST` | `/api/crews/{id}/workspace` | `{"path":"D:\\Проект"}` или `{"path":""}` | `{"crew":…,"workspace":…}` |

Пустой `path` возвращает папку по умолчанию. Путь проверяется по разрешённым корням
и служебным каталогам.

## Проводник

| Метод | Путь | Ответ |
|---|---|---|
| `GET` | `/api/fs?path=…` | `{"path","parent","dirs","files","roots","drives","writable"}` |
| `POST` | `/api/fs/mkdir` | `{"parent":"…","name":"…"}` → `201 {"path":…}` |

Без `path` открывается домашняя папка. Корни: домашняя, папка проекта и
`fs_roots` из настроек.

## Роли

| Метод | Путь | Тело | Ответ |
|---|---|---|---|
| `GET` | `/api/roles` | — | `{"roles":[…]}` |
| `POST` | `/api/roles` | `{"name","goal","experience","character","tools"}` | `201 {"role":…}` |
| `PUT` | `/api/roles/{id}` | те же поля | `{"role":…}` |
| `DELETE` | `/api/roles/{id}` | — | `{"ok":true}` |
| `POST` | `/api/roles/reset` | — | `{"roles":[…]}` — вернуть встроенные |

## Шаблоны

| Метод | Путь | Тело | Ответ |
|---|---|---|---|
| `GET` | `/api/templates` | — | `{"templates":[…]}` |
| `POST` | `/api/templates` | `{"crew_id":"…","title":"…","description":"…"}` или `{"title":…,"crew":{…}}` | `201 {"template":…}` |
| `PUT` | `/api/templates/{key}` | `{"title","description"}` | `{"template":…}` |
| `DELETE` | `/api/templates/{key}` | — | `{"ok":true}` |

Из шаблона рабочая область не переносится: она принадлежит проекту.

## Запуски

`GET /api/runs` отдаёт страницу истории:

| Параметр | Значение |
|---|---|
| `limit` | 1–200, по умолчанию 50 |
| `offset` | смещение, по умолчанию 0 |
| `status` | `completed`, `failed`, `cancelled` |
| `crew_id` | только запуски проекта |

Ответ: `{runs, total, limit, offset}`. Старые запуски удаляются по настройке
`runs_retention_days` (по умолчанию 180 дней) при старте приложения, максимум хранится 5000 записей.


| Метод | Путь | Тело | Ответ |
|---|---|---|---|
| `POST` | `/api/runs` | `{"crew_id":"…","inputs":{"k":"v"}}` | `201 {"run_id","crew_name"}` |
| `GET` | `/api/runs` | — | `{"runs":[…]}` (индекс, до 100) |
| `GET` | `/api/runs/active` | — | `{"run_id":…}` |
| `GET` | `/api/runs/{id}` | — | `{"run":…,"live":true/false}` |
| `DELETE` | `/api/runs/{id}` | — | `{"ok":true}` |
| `POST` | `/api/runs/{id}/cancel` | — | `{"ok":true}` |
| `POST` | `/api/runs/{id}/detach` | — | `{"ok":true}` |
| `POST` | `/api/runs/{id}/permissions/{req}` | `{"allow":true,"scope":"once"|"run"}` | `{"ok":true}` |
| `GET` | `/api/runs/{id}/export?format=md|json` | — | файл |
| `GET` | `/api/runs/{id}/events` | — | SSE |

### Ожидающие подтверждения

`GET /api/runs/active` и `GET /api/runs/{id}` возвращают `pending_permissions`: список запросов,
на которых запуск сейчас стоит (`id`, `kind`, `target`, `grant`, `base`). Пустой список — запуск
не ждёт ответа.

### SSE

```
event: hello
data: {"run_id":"…"}

id: 12
event: info
data: {"ts":…,"type":"info","data":{"message":"…"}}
```

Заголовок `Last-Event-ID` позволяет продолжить с места разрыва; если запрошенный
номер уже вытеснен из кольцевого буфера, приходит событие `dropped`.

Типы событий: `run_started`, `task_started`, `task_done`, `tool_start`, `tool_end`,
`tool_network`, `llm_chunk`, `info`, `warning`, `error`, `permission_request`,
`permission_resolved`, `permission_denied`, `cancel_requested`, `force_stopping`,
`run_done`, `run_cancelled`, `stream_end`.

## Инструменты

| Метод | Путь | Ответ |
|---|---|---|
| `GET` | `/api/tools` | `{"tools":[{"name","label","available","installed","policy","warning",…}]}` |
| `GET` | `/api/tools/install` | `{"running","ok","output","target","seconds"}` |
| `POST` | `/api/tools/install` | `202 {"started":true}` или `409` |

`policy` — `sandboxed` (встроенный) или `third-party-network` (сторонний, по
умолчанию недоступен).

## Файлы

| Метод | Путь | Ответ |
|---|---|---|
| `GET` | `/api/files?crew_id=…` | рабочая область и результаты |
| `GET` | `/api/files/output/{name}?crew_id=…` | содержимое файла результата |
| `POST` | `/api/files` | `{"name","data":"base64","crew_id"}` → `{"ok","path"}` |

## Экспорт, импорт и бэкап

| Метод | Путь | Что делает |
|---|---|---|
| GET | `/api/crews/{id}/export` | файл `project-<id>.json` с проектом для переноса |
| POST | `/api/crews/import` | `{crew}` или сам объект проекта → создаёт новый проект (новый id, пустая рабочая область) |
| GET | `/api/backup` | ZIP: проекты, роли, шаблоны, настройки, аккаунты; `?runs=1` добавляет историю запусков |

В бэкап не входят логи и сессии. Зашифрованные ключи API остаются привязанными к машине.

## Журнал

| Метод | Путь | Параметры |
|---|---|---|
| GET | /api/logs/recent | limit (1–500), errors=1 — только записи об ошибках |

Ответ: {file, lines, count}. Секреты в строках уже отредактированы.

## Настройки

| Метод | Путь | Тело | Ответ |
|---|---|---|---|
| `GET` | `/api/settings` | — | `{"settings":…,"providers":[…]}`, ключи замаскированы |
| `PUT` | `/api/settings` | `{"settings":{…}}` | `{"settings":…,"blocked_env":[…]}` |

Секреты: пустая строка — «оставить как есть», `"__clear__"` — удалить. Переменные
окружения принимаются по allow-list (`*_API_KEY`, `*_BASE_URL`, `STUDIO_*`),
остальные возвращаются в `blocked_env`.

| Метод | Путь | Тело | Ответ |
|---|---|---|---|
| `POST` | `/api/llm/test` | `{"model":"…"}` | `{"ok","model","latency","answer"}` или `{"ok":false,"error"}` |

## Статика

`GET /` — интерфейс (с подставленным токеном), `GET /static/*` — файлы из `web/`.
Всё остальное — `404`. Выход за пределы `web/` — `403`.

## Пример: запуск из скрипта

```python
import json, time, urllib.request

BASE = "http://127.0.0.1:7860"
token = ...  # из HTML, см. выше

def call(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("X-Studio-Token", token)
    if data:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read() or b"{}")

run = call("/api/runs", "POST", {"crew_id": "crew-…", "inputs": {"review": "…"}})
while True:
    snapshot = call(f"/api/runs/{run['run_id']}")["run"]
    if snapshot["status"] in {"completed", "failed", "cancelled"}:
        break
    time.sleep(1)
print(snapshot["result"])
```
