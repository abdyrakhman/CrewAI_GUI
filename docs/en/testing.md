# Tests

The suites spend no tokens: a local OpenAI-compatible mock (`tests/mock_llm.py`) replaces the provider.
Browser suites need installed Chrome and `playwright`.

Every suite is isolated: it creates its own `CREWAI_STUDIO_DATA` folder under `.setup/`, so your projects
and settings are untouched. The exception is `test_auth.py`, which exercises real accounts and sessions in
a temporary folder. All other suites set `CREWAI_STUDIO_NO_AUTH=1` and do not sign in.

## Running

```bat
:: server-side
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

:: browser (Chrome + playwright)
.venv\Scripts\python.exe tests\test_ui.py
.venv\Scripts\python.exe tests\test_ui_features.py
.venv\Scripts\python.exe tests\test_ui_workspace.py
.venv\Scripts\python.exe tests\test_ui_confirmations.py
.venv\Scripts\python.exe tests\test_ui_i18n.py
.venv\Scripts\python.exe tests\test_ui_auth_i18n.py
```

Each prints `PASS`/`FAIL` lines and a final `… RESULT: PASS`. Exit code `0` means success.
There are 22 suites in total.

## What each suite covers

| Suite | Checks |
|---|---|
| `test_runner_e2e.py` | full path: spec → CrewAI objects → event bus → snapshot; tokens, tasks, no raw chunks |
| `test_http_api.py` | REST contract, SSE, history, export, static files; SSE carries agent steps |
| `test_features_api.py` | roles (CRUD, apply), templates and their editor, duplicate/delete projects, code |
| `test_workspace_api.py` | workspace, folder browser, allowed roots, uploads |
| `test_permissions_api.py` | access requests, grants, timeout, denial, `pending_permissions`, key encryption |
| `test_tools_install.py` | `crewai-tools` installation, catalogue, statuses |
| `test_cancel.py` | cancel, watchdog, limits, orphaned runs, memory without embeddings |
| `test_hardening.py` | traversal, perimeter (Host/Origin/token/CSRF), sandbox, env allow-list, second instance, upload limit |
| `test_round4.py` | workspace on load, network tools, env, Code, grants, detached runs, terminal statuses |
| `test_braced_text.py` | text with `{id}` in a task description does not break a real run |
| `test_auth.py` | sign-in, forced password change, attempt limit, registration, session reset |
| `test_export_import.py` | project export/import, ZIP backup without logs and sessions, no account roles |
| `test_human_flag.py` | a project with the legacy `human_input` flag runs instead of hanging |
| `test_runs_pagination.py` | history pagination, filters, retention and old-run deletion |
| `test_run_limits.py` | run time limit, agent iteration cap, settings normalization |
| `test_logs_api.py` | `/api/logs/recent`, secret redaction, diagnostics modals |
| `test_ui.py` | interface: create project, run, result, cancel |
| `test_ui_features.py` | roles, templates, deleting projects |
| `test_ui_workspace.py` | workspace picker, reset, path errors |
| `test_ui_confirmations.py` | permission dialog, "until the end of the run", background run, Esc and reopen |
| `test_ui_i18n.py` | RU/EN switch and persistence |
| `test_ui_auth_i18n.py` | login and password-change pages in RU/EN |

## How they are built

- **Mock model.** `MockLLMServer` answers in OpenAI format and can delay. The port is set per suite.
- **Isolation.** `CREWAI_STUDIO_DATA` points at `.setup/<prefix>-<hex>`.
- **Browser.** Playwright launches installed Chrome (`channel="chrome"`, headless).
- **No network calls** to providers: the base URL points at the mock.

## Adding a test

1. Copy the structure of any suite: isolated folder, `check()` helper, final `RESULT`.
2. For the API — start `create_server("127.0.0.1", <port>)`; GET requests need no token, mutations need
   the `X-Studio-Token` header from the page meta tag.
3. For a model scenario — `MockLLMServer` plus `openai_base_url` in settings.
4. Name the file `test_<topic>.py` and add a row to README and to this document.
