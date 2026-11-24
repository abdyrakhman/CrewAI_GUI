# Как контрибьютить

Работа идёт через ветки и пул-реквесты. Прямые коммиты в `main` не принимаются:
владелец репозитория просматривает PR и мержит сам.

## Правила

1. **Одна ветка — одна тема.** Имена: `feat/кратко`, `fix/кратко`, `docs/кратко`,
   `chore/кратко`. Например `fix/brace-placeholders`, `docs/api-examples`.
2. **В `main` не пушим.** Локальный хук `.git/hooks/pre-push` блокирует такой push;
   установить его: `powershell -ExecutionPolicy Bypass -File scripts\install-hooks.ps1`.
3. **Коммит — законченное изменение.** Сообщение в императиве, первая строка до 72
   символов, тело — зачем, а не что.
4. **Перед PR прогоняются тесты** (см. ниже). В описании PR указывается, что именно
   запускалось.
5. **Секреты не коммитятся.** Папка `data/` (проекты, история, ключи), `.venv`,
   `.env`, внутренние заметки — в `.gitignore`. Если сомневаетесь, проверьте
   `git status` перед коммитом.
6. **Стиль кода.** Python — 4 пробела, типы по возможности, комментарии по-английски,
   пользовательские строки по-русски. Фронтенд — без сборки и фреймворков.

## Тесты перед PR

```bat
.venv\Scripts\python.exe -m compileall -q app
.venv\Scripts\python.exe tests\test_http_api.py
.venv\Scripts\python.exe tests\test_features_api.py
.venv\Scripts\python.exe tests\test_workspace_api.py
.venv\Scripts\python.exe tests\test_cancel.py
.venv\Scripts\python.exe tests\test_runner_e2e.py
.venv\Scripts\python.exe tests\test_braced_text.py
```

Полный список — в [docs/testing.md](docs/testing.md). Браузерные наборы требуют
Chrome и `playwright`; в CI они не запускаются.

## Создать PR

```bat
git checkout -b fix/theme
:: ... правки ...
git add -A
git commit -m "Исправить переключение темы"
python scripts\open_pr.py
```

Скрипт запушит ветку, создаст PR в `main` и напечатает ссылку. Токен берётся из
`GITHUB_TOKEN`, а если переменной нет — из Git Credential Manager.

## Ревью и мерж

- Владелец смотрит diff, при необходимости просит правки в той же ветке.
- Мерж — squash или merge commit, решает владелец.
- После мержа ветку можно удалить: `git branch -d <ветка>`.

## CI

На каждый PR запускается `.github/workflows/tests.yml` — серверные тесты на
Ubuntu. Красный CI означает, что мержить нельзя.
