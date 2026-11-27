# Troubleshooting

## The app does not start

**`CrewAI is not installed` in the console.** Run `start.bat`: it creates `.venv` and installs
dependencies. If installation fails, check that Python 3.11+ is on `PATH`.

**`Refusing to start: the interface without a password listens on 127.0.0.1 only`.** This is
protection, not an error. Remove `--host` or pass `127.0.0.1`.

**Port is busy.** The app takes the next free port and prints the address; look for
`CrewAI Studio запущен: …`.

**`[Errno 13] Permission denied` during package installation.** The process cannot write to
temporary folders. Studio redirects `TMP`/`TEMP` and the pip cache to `data/tmp`; if it
persists, run `start.bat` as a normal user and check permissions on `%TEMP%`.

## Page and session

**`The session expired or the request was rejected`.** The server restarted and the token
changed. Reload the page with **Ctrl+F5**.

**Blank page or old styles.** Hard reload with **Ctrl+F5** — also needed after an update.

**Another port in the browser.** If 7860 was busy the address is different; the old tab points
at a server that is not there.

## Running

**`Wait for the current run to finish`.** Only one run at a time. If the previous one hangs,
press Detach in its window or restart the app: unfinished runs are marked on startup.

**`Missing required template variable … in description`.** The task text contains `{name}`
with no matching input. In current versions such braces stay as text and the run does not
fail; the check panel warns you. Add the field in Inputs if a value should be substituted.
Doubling braces does not help — CrewAI matches `{name}` inside them too.

**`401 AuthenticationError` although the key is correct.** Check the model/provider and the
base URL. If the key changed during a run, save settings and restart the app.

**A run takes very long.** Look at the first log line (effective parameters) and reduce:

- Max iterations — 8–10 is usually enough;
- Time limit — a hard cap per agent;
- Reasoning — an extra model request on every step;
- Confirm changes — every write waits for you up to five minutes.

**`Memory disabled: no embeddings key`.** CrewAI memory needs embeddings (OpenAI or Gemini).
Without them the team runs without memory and warns — this is not an error.

**`PDFSearchTool`/`FileReadTool` is unavailable.** File and RAG tools from `crewai-tools` were
removed: they read files outside the sandbox. Use the built-in Read file, Write file and List
files tools — they stay in the workspace and ask for access.

**A third-party network tool cannot be enabled.** It is off by default. Enable it by name in
Settings → Third-party network tools; every call asks for permission.

**I enabled human confirmation and the run hung.** The `human_input` flag is not supported in the GUI: CrewAI asks for confirmation through the console `input()`. Current versions ignore the flag and do not block the run; the check panel shows a warning.

## Workspace and files

**`Folder outside allowed roots`.** Add the root in Settings → Folder access (one path per
line) or choose a folder inside your home or project directory.

**`Folder … is a service folder — cannot be chosen`.** `Windows\System32`, `Startup`, `.ssh`,
`site-packages`, `app`, `web`, `data\crews`, `data\runs` are forbidden: protection against
writing to autostart or application code.

**The project opens with an empty agent and task.** It was saved by a partial request before
the guard existed. Restore the team from a template or create agents again. A partial `PUT`
is now rejected with `422`.

**`Project is damaged` (409).** The project file is not valid JSON; it was renamed to
`data/crews/<id>.json.corrupt` at startup. Fix it by hand or create the project again.

**The agent answers `Access denied`.** The permission dialog timed out (five minutes) or you
pressed Deny. Run again and answer the request.

## Tests

**`playwright` cannot find Chrome.** Install Google Chrome, or run
`playwright install chromium` and change `channel="chrome"` to `channel="chromium"`.

**Tests fail on ports.** Ports are fixed (78xx/89xx). Close old Python processes or change
`PORT` at the top of the file.

## Logs

If an error is unclear, open `data/logs/app-YYYYMMDD.jsonl`: it contains `request_id`,
`error_id` and the traceback. A `500` response carries an `error_id` too.


## Forgot the password

1. Stop the app.
2. Delete `data/users.json` (and `data/sessions.json` to drop sessions).
3. Start again: `admin` is recreated with a random password printed in the console and shown on the login
   page (or the `CREWAI_STUDIO_ADMIN_*` values are used).

This removes all accounts: passwords are stored irreversibly. Then change the password in Settings → Account.

## 500 error and error_id

The response carries `error_id` and the `X-Request-Id` header. Find the record:

```powershell
Select-String -Path data\logs\app-*.jsonl -Pattern '"error_id":"a1b2c3d4"'
```

It contains the traceback; `request_id` points to the exact request. See [logging.md](logging.md).
