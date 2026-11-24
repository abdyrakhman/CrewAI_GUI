# Security

The app is local, but it handles two sensitive things: files on disk and provider API keys.
This document describes the trust model, what is covered and what remains.

## Trust model

| Subject | Trust |
|---|---|
| The user at this computer | full: owns `data/` and the settings |
| The Studio page | trusted, but gets the session token from HTML |
| Another tab or site in the same browser | **not trusted** |
| The model and its answers | **not trusted**: model text is data, not commands |
| File and web content | **not trusted** |
| Third-party `crewai-tools` | **not trusted**: their code is outside our control |

Principle: any path from a request, project, template, copied `data/` folder or tool argument
goes through the policy; any tool touching files or network is created through a wrapper.

## What is covered

### HTTP perimeter

- Listens on `127.0.0.1` only; any other address is refused.
- `Host` and `Origin` checks defend against DNS rebinding.
- A session token (`hmac.compare_digest`) on every mutating request defends against CSRF.
- Only `application/json` with `Content-Length`; chunked is rejected.
- No CORS headers: another page cannot read responses.
- `nosniff`, `Referrer-Policy`, `X-Frame-Options`, a CSP for HTML.
- 20-second socket timeout and a 64-connection semaphore against slowloris.
- Request body limited to 64 MB.

### File system

- Static files only from `web/`: `..`, `\`, NUL, drives and absolute paths are rejected
  (covered by tests on nine traversal variants).
- The workspace is checked on save **and** on run: a project imported with `data/` and a
  service folder falls back to the default folder with a warning.
- Service directories (`Windows\System32`, `Startup`, `.ssh`, `site-packages`,
  `node_modules`, `app`, `web`, `data\crews`, `data\runs`) are forbidden on the **resolved**
  path, so a symlink or junction does not help.
- `output_file` is a file name only and always lands in the workspace.
- Tools are confined to the workspace; going outside needs confirmation, service folders are
  refused without a dialog.

### Network

- `fetch_url`: private, loopback, link-local, reserved and multicast addresses are blocked;
  up to three redirects are re-checked; 20-second timeout; at most 1.5 MB read.
- Third-party network tools are off by default and enabled per name; every call checks URL
  arguments, asks for permission and emits a `tool_network` event.
- `file://`, `ftp://` and other schemes are rejected.

### Data

- API keys are encrypted: Windows DPAPI (bound to the account) or Fernet with
  `data/.secret.key` (mode 0600).
- Only masks and "key saved" flags reach the browser.
- Logs redact `sk-…`, `Bearer …` and `api_key=…`; retention is 30 days.
- Saved runs redact errors and final text.
- Environment variables are allow-listed: `*_API_KEY`, `*_BASE_URL`, `STUDIO_*`. `PATH`,
  `PYTHONPATH`, `LD_*`, `SSL_*`, `PIP_*` and similar are rejected.

### Runs

- One run at a time: the CrewAI event bus is global.
- The slot is released only in `finally`; `force_stopping` does not release it while the
  thread lives.
- A cancelled run is never marked `completed`.
- A detached run cannot write files, use the network or receive permission answers.
- Grants are per file or per folder — exactly what the dialog says.

## Residual risks

| Risk | Why it remains | Mitigation |
|---|---|---|
| **DNS rebinding** between check and connect | `check_url` resolves, `urllib` resolves again; needs a hostile DNS with a short TTL | block outbound traffic with a firewall; use a separate network/container |
| **Third-party tool executes its own code** | the wrapper checks arguments and asks permission, not behaviour | enable per name consciously; do not enable where the workspace holds secrets |
| **A run lives inside the app process** | no hard isolation | run Studio under a dedicated account for untrusted material |
| **Keys are decrypted in memory** | needed to call providers | do not run under a shared Windows account |
| **Generated Python runs outside Studio** | separate artefact; no built-in tools, but full model and network access | review the code before running |
| **pip install from the UI** installs into the working venv | convenience over strictness | install `crewai-tools` during setup, not mid-session |

## Operational advice

1. Never expose the port to a network: the API has no password.
2. Work under your own Windows account — DPAPI is bound to it.
3. For untrusted material disable write tools and enable **Confirm changes**.
4. Keep `data/settings.json` and `data/.secret.key` out of shared repositories and backups.
5. Clear run history from time to time: prompts and answers are stored there.

## Reporting a vulnerability

Do not open a public issue. Describe reproduction steps privately to the repository owner,
including the version (`/api/info`) and the `error_id` from the response if applicable.
