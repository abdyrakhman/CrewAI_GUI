# Tests

The suites spend no tokens: a local OpenAI-compatible mock (`tests/mock_llm.py`) replaces
the provider. Every suite is isolated — it creates its own `CREWAI_STUDIO_DATA` folder under
`.setup/`, so your projects and settings are untouched.

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

:: browser (Chrome + playwright)
.venv\Scripts\python.exe tests\test_ui.py
.venv\Scripts\python.exe tests\test_ui_features.py
.venv\Scripts\python.exe tests\test_ui_workspace.py
.venv\Scripts\python.exe tests\test_ui_confirmations.py
.venv\Scripts\python.exe tests\test_ui_i18n.py
```

Each prints `PASS`/`FAIL` lines and a final `… RESULT: PASS`. Exit code `0` means success.

## What each suite covers

| Suite | Checks |
|---|---|
| `test_runner_e2e.py` | full path: spec → CrewAI objects → event bus → saved snapshot; tokens, tasks, streaming |
| `test_http_api.py` | REST contract, SSE, history, export, static files |
| `test_features_api.py` | roles (CRUD, apply), templates, duplicate and delete projects, code generation |
| `test_workspace_api.py` | workspace, folder browser, allowed roots, uploads |
| `test_permissions_api.py` | access requests, grants, timeout, denial, key encryption |
| `test_tools_install.py` | `crewai-tools` installation, catalogue, statuses |
| `test_cancel.py` | cancel, watchdog, limits, orphaned runs, memory without embeddings |
| `test_hardening.py` | traversal (9 variants), perimeter (Host/Origin/token/CSRF), sandbox, env allow-list, pip pin, code parity, index speed |
| `test_round4.py` | workspace on load, network tools, env, Code, grants, service folders, detached runs, terminal statuses |
| `test_braced_text.py` | text with `{id}` in a task description does not break a real run |
| `test_ui.py` | interface: create project, run, live output, cancel |
| `test_ui_features.py` | roles, templates, deleting projects |
| `test_ui_workspace.py` | workspace picker, reset, path errors |
| `test_ui_confirmations.py` | permission dialog, "until the end of the run", background run |
| `test_ui_i18n.py` | RU/EN switch and persistence |

## How they are built

- **Mock model.** `MockLLMServer` answers in OpenAI format, can delay and stream.
- **Isolation.** `CREWAI_STUDIO_DATA` points at `.setup/<prefix>-<hex>`.
- **Browser.** Playwright launches installed Chrome (`channel="chrome"`, headless).
- **No network calls** to providers: the base URL points at the mock.

## Adding a test

1. Copy the structure of any suite: isolated folder, `check()` helper, final `RESULT`.
2. For API tests start `create_server("127.0.0.1", <port>)` and read the token from
   `server.RequestHandlerClass.session_token`.
3. For model scenarios use `MockLLMServer` and point `openai_base_url` at it.
4. Name the file `test_<topic>.py` and add it to this document and the README.
