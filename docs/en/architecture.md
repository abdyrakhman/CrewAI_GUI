# Architecture

How the application is built: layers, modules, the run lifecycle, storage and the
constraints behind them.

## Overview

```
Browser (web/index.html + app.js + i18n.js + styles.css)
        │  REST + SSE, session token, 127.0.0.1 only
        ▼
app/server.py            HTTP transport, routes, SSE, static files
        │
        ├── app/spec.py          normalisation and validation
        ├── app/workspace.py     workspace policy
        ├── app/tools.py         agent tools
        ├── app/roles.py         role library
        ├── app/templates.py     project templates
        ├── app/store.py         JSON storage
        └── app/runner.py        CrewAI run in a worker thread
                    │
                    ▼
                CrewAI (Agent, Task, Crew, LLM) + event bus
```

One process, no external services, no frontend build step: `app.js` is a plain script.

## Modules

| Module | Responsibility |
|---|---|
| `config.py` | Paths, defaults, providers, model normalisation, legacy `.env` |
| `security.py` | Path confinement, SSRF checks, security headers, body limit |
| `store.py` | Projects, settings, run history, indexes, secret encryption |
| `secrets.py` | Key encryption: Windows DPAPI, otherwise Fernet |
| `spec.py` | Project schema, validation, placeholders, Python generation |
| `workspace.py` | Allowed roots, service directories, folder browser |
| `tools.py` | Built-in tools, third-party catalogue, extras install |
| `roles.py` | 12 built-in roles plus custom ones |
| `templates.py` | 4 built-in scenarios plus custom templates |
| `runner.py` | Run slot, execution thread, events, permissions, cancel |
| `statuses.py` | Single set of terminal and active statuses |
| `observability.py` | JSONL logs, secret redaction, retention |
| `crewai_env.py` | Redirects CrewAI folders into `data/`, import lock |

## Run lifecycle

1. **Validation** — `POST /api/runs` loads the project by `crew_id`, normalises and
   validates it; errors return `422`. Inline specs are rejected.
2. **Slot** — `RunManager.start` takes the single slot; a parallel run gets `409` because
   the CrewAI event bus is process-global.
3. **Execution** — the `run-<id>` thread applies provider keys to `os.environ`, resolves the
   workspace through the policy, builds `Agent`/`Task`/`Crew`, subscribes to CrewAI events
   and calls `crew.kickoff`.
4. **Events** — each event gets a monotonic `seq` and enters a ring buffer (12,000 records).
   `GET /api/runs/{id}/events` streams SSE with `id:` and supports `Last-Event-ID`.
5. **Finish** — the slot is released only in `finally`; a cancelled or detached run is never
   marked `completed`.

### Statuses

`queued`, `running`, `cancelling`, `force_stopping`, `completed`, `failed`, `cancelled`.

`TERMINAL = {completed, failed, cancelled, force_stopping}` is used for memory eviction,
orphan marking and closing SSE.

### Cancel and detach

- `cancel()` sets `cancelled`, wakes pending permissions and starts a 12-second watchdog.
- The watchdog moves the run to `force_stopping` and keeps the slot: a new run must not
  overwrite a live one.
- `detach()` frees the slot, marks the run `abandoned` and blocks its writes, network calls
  and permission answers.

## Events

`state.emit` is the only progress channel: model text, tool calls, warnings, errors,
permission requests. Snapshots are built from the same stream; `llm_chunk` events are not
persisted, aggregated text is. A checkpoint is written every ~30 seconds or 200 events.

## Permissions

`RunState.ask_permission()` creates a request, emits `permission_request`, and blocks on a
`threading.Event` for up to 5 minutes. The answer arrives via
`POST /api/runs/{id}/permissions/{req}`.

Grant scope is honest: a write outside the workspace grants a **file**, a confirmed write
inside grants a **folder** (shown in the dialog), and listing a folder grants that folder,
not its parent. Tools receive the `RunState` at creation time, not through a global.

## Storage

```
data/
  crews/<id>.json          project
  runs/<id>.json           run snapshot
  runs/index.jsonl         history index (compacted)
  roles.json               role library
  templates/<key>.json     custom templates
  workspaces/<id>/         default workspace
  uploads/, outputs/       files
  settings.json            settings, keys encrypted
  logs/app-*.jsonl         requests and errors
```

Writes are atomic (temp file + `os.replace`). The history index is append-only and is
rewritten when it grows (every 500 appends or above 1 MB at startup).

## Path policy

- `confine(path, root)` — resolves and checks `relative_to`, rejects NUL.
- `web_path` — only files under `web/`, no `..`, `\`, drives or absolute paths.
- `assert_safe_target` — service directories, checked on the **resolved** path so symlinks
  and junctions do not bypass it.
- `authorize_or_default` — applied both on save and on run.

Tools are additionally confined to the workspace: relative names always land there,
absolute ones require confirmation.

## Network policy

Built-in `fetch_url` blocks private, loopback, link-local, reserved and multicast addresses,
re-checks up to three redirects, uses a 20-second timeout and reads at most 1.5 MB.

Third-party `crewai-tools` run their own code, therefore: file and RAG tools are removed,
network tools are off by default, opt-in per name, wrapped by `guard_network_tool` (URL
checks, abandoned-run block, egress confirmation, `tool_network` event).

## Frontend

One file (`web/app.js`) without a framework: state in `state`, rendering through template
strings, delegated `data-action` handlers. SSE via `EventSource`; reconnects with
`Last-Event-ID`.

Things to know:

- the session token is read from `<meta name="studio-token">` and sent on every mutation;
- autosave is debounced by 900 ms and carries a generation counter so an old response cannot
  overwrite a newer change;
- after a server restart the token changes — reload the page;
- `web/i18n.js` translates rendered text nodes and attributes; originals are remembered, so
  switching back to Russian restores them exactly.

## Constraints

- One run at a time — the CrewAI event bus is global.
- A run lives inside the application process: no hard isolation, which is why Detach and
  `os.environ` are carefully handled.
- History is JSON, not SQLite: enough for a local tool, worth revisiting at scale.
