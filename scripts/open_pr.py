"""Открыть пул-реквест из текущей ветки.

Запуск из рабочей папки репозитория:

    python scripts\\open_pr.py
    python scripts\\open_pr.py --title "Исправить тему" --body "..."

Что делает:
1. проверяет, что вы не в main и есть коммиты, которых нет в origin/main;
2. пушит ветку;
3. создаёт PR в main (или печатает ссылку на существующий);
4. печатает URL.

Токен: переменная окружения GITHUB_TOKEN, иначе Git Credential Manager.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

REPO = "abdyrakhman/CrewAI_GUI"
API = f"https://api.github.com/repos/{REPO}"
BASE = "main"


def git(*args: str) -> str:
    result = subprocess.run(["git", *args], capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        raise SystemExit(f"git {' '.join(args)}: {result.stderr.strip() or result.stdout.strip()}")
    return result.stdout.strip()


def token_from_credentials() -> str:
    payload = "protocol=https\nhost=github.com\n\n"
    result = subprocess.run(
        ["git", "-c", "credential.helper=wincred", "credential", "fill"],
        input=payload,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    for line in (result.stdout or "").splitlines():
        if line.startswith("password="):
            return line.split("=", 1)[1].strip()
    return ""


def api(path: str, token: str, method: str = "GET", body: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        API + path,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "crewai-studio",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"error": raw.decode("utf-8", "replace")[:400]}
        return exc.code, payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Создать пул-реквест в CrewAI_GUI")
    parser.add_argument("--title", help="заголовок PR (по умолчанию — тема последнего коммита)")
    parser.add_argument("--body", help="описание PR (по умолчанию — шаблон и список коммитов)")
    parser.add_argument("--base", default=BASE)
    parser.add_argument("--draft", action="store_true")
    args = parser.parse_args()

    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    if branch in {"main", "master"}:
        print("Вы в main: создайте ветку (git checkout -b fix/...)", file=sys.stderr)
        return 2

    git("fetch", "origin", args.base, "--quiet")
    ahead = git("rev-list", "--count", f"origin/{args.base}..HEAD")
    if ahead == "0":
        print("В ветке нет коммитов сверх origin/" + args.base, file=sys.stderr)
        return 2

    git("push", "--set-upstream", "origin", branch)

    token = os.environ.get("GITHUB_TOKEN") or token_from_credentials()
    if not token:
        print("Нет токена: задайте GITHUB_TOKEN или войдите через Git Credential Manager.", file=sys.stderr)
        return 2

    title = args.title or git("log", "-1", "--pretty=%s")
    if args.body:
        body = args.body
    else:
        commits = git("log", f"origin/{args.base}..HEAD", "--pretty=- %s")
        body = f"## Что меняется\n\n{commits}\n\n## Как проверено\n\nСм. чек-лист в CONTRIBUTING.md.\n"

    existing_status, existing = api(f"/pulls?head=abdyrakhman:{branch}&state=open", token)
    if existing_status == 200 and existing:
        print("PR уже открыт:", existing[0]["html_url"])
        return 0

    status, payload = api(
        "/pulls",
        token,
        "POST",
        {"title": title, "head": branch, "base": args.base, "body": body, "draft": args.draft},
    )
    if status not in {200, 201}:
        print(f"Не удалось создать PR ({status}): {payload}", file=sys.stderr)
        return 1
    print("PR создан:", payload.get("html_url"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
