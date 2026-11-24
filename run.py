"""Точка входа CrewAI Studio.

Запуск:
    python run.py                # http://127.0.0.1:7860
    python run.py --port 8080 --no-browser
"""
from __future__ import annotations

import argparse
import sys

from app import config
from app.server import serve


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        # Windows consoles often default to cp866; UTF-8 keeps Russian readable.
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass
    parser = argparse.ArgumentParser(description="CrewAI Studio — графический интерфейс для CrewAI")
    parser.add_argument("--host", default="127.0.0.1", help="адрес прослушивания (по умолчанию только локально)")
    parser.add_argument("--port", type=int, default=7860, help="порт (по умолчанию 7860, занятый порт сдвигается)")
    parser.add_argument("--no-browser", action="store_true", help="не открывать браузер автоматически")
    args = parser.parse_args()

    print(f"\n  {config.APP_NAME} v{config.APP_VERSION}")
    print(f"  Проект: {config.ROOT}")
    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        print("  Отказ: интерфейс без пароля слушает только 127.0.0.1. Удалённый доступ не поддерживается.")
        return 2
    serve(host=args.host, port=args.port, open_browser=not args.no_browser)
    return 0


if __name__ == "__main__":
    sys.exit(main())
