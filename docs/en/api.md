# REST API

The UI talks to the server over HTTP/1.1 on `http://127.0.0.1:<port>`. All responses are
JSON except static files, SSE and exports. The same API is available to scripts.

## Perimeter

| Check | Rule |
|---|---|
| `Host` | `127.0.0.1:<port>`, `localhost:<port>`, `[::1]:<port>` |
| `Origin` | if present, must match an allowed host |
| Token | every `POST`/`PUT`/`DELETE` needs `X-Studio-Token` |
| `Content-Type` | `application/json` when the body is not empty |
| Body size | at most 64 MB |
| `Transfer-Encoding` | chunked is rejected; send `Content-Length` |
| CORS | no headers, cross-origin calls fail |

The token is embedded into the HTML page:

```html
<meta name="studio-token" content="…">
```

It changes on every server restart.

```powershell
$page  = Invoke-WebRequest 'http://127.0.0.1:7860/' -UseBasicParsing
$token = [regex]::Match($page.Content, 'studio-token" content="([^"]+)"').Groups[1].Value
$h = @{ 'X-Studio-Token' = $token; 'Content-Type' = 'application/json' }
Invoke-RestMethod 'http://127.0.0.1:7860/api/crews' -Headers $h
```

```bash
TOKEN=$(curl -s http://127.0.0.1:7860/ | grep -o 'studio-token" content="[^"]*' | cut -d'"' -f3)
curl -s http://127.0.0.1:7860/api/crews -H "X-Studio-Token: $TOKEN"
```

## Errors

| Code | When |
|---|---|
| `400` | invalid request data |
| `403` | bad Host/Origin, missing token, path outside allowed roots |
| `404` | not found |
| `409` | a run is already active, damaged project, duplicate answer |
| `411` | chunked body |
| `413` | body too large |
| `415` | not `application/json` |
| `422` | project failed validation, partial `PUT`, code refused |
| `500` | internal error; the response carries `error_id`, details in `data/logs` |

## Service

| Method | Path | Response |
|---|---|---|
| `GET` | `/api/info` | app version, CrewAI status, settings without secrets, providers |
| `GET` | `/api/status` | slot state, active run, environment preview |

## Projects

| Method | Path | Body | Response |
|---|---|---|---|
| `GET` | `/api/crews` | — | `{"crews":[…],"broken":[…]}` |
| `POST` | `/api/crews` | `{"crew":{…}}` or `{"template":"tpl-…"}` | `201 {"crew":…,"rejected":[…]}` |
| `GET` | `/api/crews/{id}` | — | `{"crew":…,"validation":…,"workspace":…}` |
| `PUT` | `/api/crews/{id}` | `{"crew":{…}}` — complete | `{"crew":…,"rejected":[…],"validation":…}` |
| `DELETE` | `/api/crews/{id}` | — | `{"ok":true}` |
| `POST` | `/api/crews/{id}/duplicate` | — | `201 {"crew":…}` |
| `POST` | `/api/crews/{id}/validate` | `{"crew":…}` optional | `{"ok":…,"errors":…,"warnings":…}` |
| `GET` | `/api/crews/{id}/code` | — | `{"code":"…","warnings":[…]}` or `422` |

A `PUT` without `agents` and `tasks` is rejected: a partial body would erase the project.

Minimal project:

```json
{
  "crew": {
    "name": "Review triage",
    "default_llm": "deepseek/deepseek-chat",
    "agents": [
      {"role": "Analyst", "goal": "Find the cause", "backstory": "Experienced analyst", "max_iter": 8}
    ],
    "tasks": [
      {"name": "Analysis", "description": "Analyse the review: {review}", "expected_output": "List of causes"}
    ],
    "inputs": [{"key": "review", "label": "Review", "default": ""}]
  }
}
```

## Workspace

| Method | Path | Body | Response |
|---|---|---|---|
| `GET` | `/api/crews/{id}/workspace` | — | `{"workspace":{"path","is_default","exists","writable","note",…}}` |
| `PUT/POST` | `/api/crews/{id}/workspace` | `{"path":"D:\\Project"}` or `{"path":""}` | `{"crew":…,"workspace":…}` |

An empty `path` restores the default folder.

## Folder browser

| Method | Path | Response |
|---|---|---|
| `GET` | `/api/fs?path=…` | `{"path","parent","dirs","files","roots","drives","writable"}` |
| `POST` | `/api/fs/mkdir` | `{"parent":"…","name":"…"}` → `201 {"path":…}` |

## Roles

| Method | Path | Body | Response |
|---|---|---|---|
| `GET` | `/api/roles` | — | `{"roles":[…]}` |
| `POST` | `/api/roles` | `{"name","goal","experience","character","tools"}` | `201 {"role":…}` |
| `PUT` | `/api/roles/{id}` | same fields | `{"role":…}` |
| `DELETE` | `/api/roles/{id}` | — | `{"ok":true}` |
| `POST` | `/api/roles/reset` | — | `{"roles":[…]}` |

## Templates

| Method | Path | Body | Response |
|---|---|---|---|
| `GET` | `/api/templates` | — | `{"templates":[…]}` |
| `POST` | `/api/templates` | `{"crew_id":"…","title":"…"}` or `{"title":…,"crew":{…}}` | `201 {"template":…}` |
| `PUT` | `/api/templates/{key}` | `{"title","description"}` | `{"template":…}` |
| `DELETE` | `/api/templates/{key}` | — | `{"ok":true}` |

## Runs

| Method | Path | Body | Response |
|---|---|---|---|
| `POST` | `/api/runs` | `{"crew_id":"…","inputs":{…}}` | `201 {"run_id","crew_name"}` |
| `GET` | `/api/runs` | — | `{"runs":[…]}` (index, up to 100) |
| `GET` | `/api/runs/active` | — | `{"run_id":…}` |
| `GET` | `/api/runs/{id}` | — | `{"run":…,"live":true|false}` |
| `DELETE` | `/api/runs/{id}` | — | `{"ok":true}` |
| `POST` | `/api/runs/{id}/cancel` | — | `{"ok":true}` |
| `POST` | `/api/runs/{id}/detach` | — | `{"ok":true}` |
| `POST` | `/api/runs/{id}/permissions/{req}` | `{"allow":true,"scope":"once"|"run"}` | `{"ok":true}` |
| `GET` | `/api/runs/{id}/export?format=md|json` | — | file |
| `GET` | `/api/runs/{id}/events` | — | SSE |

### SSE

```
event: hello
data: {"run_id":"…"}

id: 12
event: info
data: {"ts":…,"type":"info","data":{"message":"…"}}
```

`Last-Event-ID` resumes after a reconnect; if the requested sequence was already evicted
from the ring buffer, a `dropped` event arrives.

Event types: `run_started`, `task_started`, `task_done`, `tool_start`, `tool_end`,
`tool_network`, `llm_chunk`, `info`, `warning`, `error`, `permission_request`,
`permission_resolved`, `permission_denied`, `cancel_requested`, `force_stopping`,
`run_done`, `run_cancelled`, `stream_end`.

## Tools

| Method | Path | Response |
|---|---|---|
| `GET` | `/api/tools` | `{"tools":[{"name","label","available","installed","policy","warning",…}]}` |
| `GET` | `/api/tools/install` | `{"running","ok","output","target","seconds"}` |
| `POST` | `/api/tools/install` | `202 {"started":true}` or `409` |

`policy` is `sandboxed` (built-in) or `third-party-network` (off by default).

## Files

| Method | Path | Response |
|---|---|---|
| `GET` | `/api/files?crew_id=…` | workspace and task results |
| `GET` | `/api/files/output/{name}?crew_id=…` | result file contents |
| `POST` | `/api/files` | `{"name","data":"base64","crew_id"}` → `{"ok","path"}` |

## Settings

| Method | Path | Body | Response |
|---|---|---|---|
| `GET` | `/api/settings` | — | `{"settings":…,"providers":[…]}`, keys masked |
| `PUT` | `/api/settings` | `{"settings":{…}}` | `{"settings":…,"blocked_env":[…]}` |

Secrets: an empty string keeps the stored value, `"__clear__"` deletes it. Environment
variables are allow-listed (`*_API_KEY`, `*_BASE_URL`, `STUDIO_*`); the rest is returned in
`blocked_env`.

| Method | Path | Body | Response |
|---|---|---|---|
| `POST` | `/api/llm/test` | `{"model":"…"}` | `{"ok","model","latency","answer"}` or `{"ok":false,"error"}` |

## Static

`GET /` serves the UI with the token injected; `GET /static/*` serves files from `web/`.
Everything else is `404`; escaping `web/` is `403`.

## Script example

```python
import json, time, urllib.request

BASE = "http://127.0.0.1:7860"
token = ...  # from the HTML page

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
