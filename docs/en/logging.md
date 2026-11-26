# Logging and diagnostics

## Where the logs live

- `data/logs/app-YYYYMMDD.jsonl` — one file per day, JSON Lines, UTF-8.
- Size rotation: at 10 MB the file becomes `app-YYYYMMDD.jsonl.1`.
- Retention: 30 days; older files are removed at start.
- Logs are local and never sent anywhere.

## What is recorded

- `{"kind": "request", "request_id", "method", "path", "status", "ms"}` — every HTTP request.
- `{"kind": "error", "error_id", "request_id", "method", "path", "error", "traceback"}` — unhandled
  exceptions; the traceback is limited to 20 frames.
- `{"kind": "event", ...}` — individual application events.
- Request and response bodies are not logged.

## Secrets

- Keys, tokens and passwords are stripped: `sk-…`, `Bearer …`, `api_key/token/secret=…` become
  `[redacted]`; strings are truncated to 8,000 characters.
- Keys saved in Settings never reach the log.
- Still, do not publish a whole log: error text may contain file names and data fragments.

## Error id

- Internal failures return `500` with `{"error": "...", "error_id": "a1b2c3d4"}` and the `X-Request-Id` header.
- The UI shows the code in the error message.
- Find it:

```powershell
Select-String -Path data\logs\app-*.jsonl -Pattern '"error_id":"a1b2c3d4"'
```

- `request_id` links the error to a specific request in the same file.

## Run logs

- `data/runs/<id>.json` — status, events, streamed answers, warnings, result and token usage.
- `data/runs/index.jsonl` — compact history for the «Run history» list.
- In the UI: run history, live run events and the `.md` report.
- Validation warnings and task errors are shown in the check panel and on the run page.

## Response codes

| Code | Meaning |
|---|---|
| 400 | bad data: validation, folder, settings |
| 401 | no session — sign in |
| 403 | missing session token, blocked path or password change required |
| 404 | not found |
| 409 | conflict: a run is already going, folder busy |
| 422 | invalid project code or partial save |
| 429 | too many requests |
| 500 | internal error — look it up by `error_id` |

## Cleanup

With the app stopped you can delete `data/logs/*`; run history and settings are not affected.
