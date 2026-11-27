# Sign-in, accounts and password

The app listens on loopback only, but the interface is password-protected: other people on the same
machine should not see your projects or change your settings.

## First run

- If `data/users.json` is missing or empty, the administrator **admin** is created with a random
  password. Login and password are printed once in the console — save them and change the password
  at sign-in.
- Override with `CREWAI_STUDIO_ADMIN_USER` and `CREWAI_STUDIO_ADMIN_PASSWORD` (used only while no accounts exist).
- That account is marked `must_change`.

When upgrading from an older version, the published password `123admin!` is replaced with a random
one and the new password is printed in the console; the old one stops working.

## Forced password change

- After the first sign-in the app opens `/change-password.html`.
- Until the password is changed, pages redirect there and `/api/*` (except `/api/auth/*`) returns
  `403 {"password_change_required": true}`.
- Requirements: at least 8 characters, different from the current one, entered twice.
- When done the flag is cleared and later sign-ins are normal.
- Accounts created before the flag existed are migrated to `must_change` at start.

## Changing the password

- **Settings → Account**: current password, new password, **Change**.
- The same `/change-password.html` screen is used when the app requires it.
- After a password change **every other session is terminated**; the current one stays active.
- **Sign out everywhere** in Settings → Account ends all sessions of the user.

## Session lifetime

- **Settings → Account → Session lifetime**: 1, 8, 12, 24, 72 or 168 hours (12 by default).
- The value (`session_ttl_hours`) becomes the cookie `Max-Age` and the session expiry in `data/sessions.json`.
- It applies to new sign-ins; the current session is not cut. Sign out and in to apply it immediately.
- The server accepts 1–720 hours and ignores anything else.

## Brute-force protection

- After 5 failed sign-ins from one address, sign-in is blocked for 10 minutes (`429` with `Retry-After`).
- A successful sign-in resets the counter.

## Registration

- **Register** on `/login`: login 3–32 characters (`A–Z`, `a–z`, digits, `.`, `_`, `-`), password 8+.
- A registered user is signed in automatically.
- All accounts are equal: there are no roles and no permission split. The first administrator exists
  only for the initial setup and password change.

## Forgot the password

1. Stop the app.
2. Delete `data/users.json` (optionally `data/sessions.json`).
3. Start again: `admin` is recreated with a random password printed in the console
   (or use the environment variables).

This resets **all** accounts. There is no other recovery: passwords are stored irreversibly.

## How secrets are stored

- Password: PBKDF2-HMAC-SHA256, 200,000 iterations, per-user salt. A one-way hash, not encryption:
  the original password is never stored and cannot be recovered.
- Session: a random token in the `studio_session` cookie (HttpOnly, SameSite=Lax); only its SHA-256 is on disk.
- The cookie is not readable from JavaScript; mutating requests also require the `X-Studio-Token` header.

## API

Public (no session): `GET /api/auth/state`, `POST /api/auth/login`, `POST /api/auth/register`,
`POST /api/auth/logout`, `POST /api/auth/logout-all`, `GET /api/auth/me`, `POST /api/auth/password`.
Sign-in and registration return only `{user, must_change}` — no role.

Every other `/api/*` call needs a session: otherwise `401 {"auth": true}`, and while the password change
is pending `403 {"password_change_required": true}`. See [api.md](api.md).

## Tests

`tests/test_auth.py`: first run, sign-in, wrong password, cookie and lifetime, forced change, registration,
duplicate, weak password, sign-out.
