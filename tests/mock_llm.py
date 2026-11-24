"""Minimal OpenAI-compatible chat endpoint used by the automated tests.

It lets the whole stack (CrewAI → LLM → Studio events) run without network
access or a real API key.
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CHUNK_DELAY = float(os.environ.get("MOCK_DELAY", "0.004"))


class MockLLMHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):  # noqa: A003 - silence test noise
        pass

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        if self.path.rstrip("/").endswith("/models"):
            self._json(200, {"object": "list", "data": [{"id": "mock-model", "object": "model"}]})
            return
        self._json(404, {"error": {"message": "not found"}})

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._json(400, {"error": {"message": "bad json"}})
            return
        messages = payload.get("messages") or []
        prompt = "\n".join(str(m.get("content", "")) for m in messages if isinstance(m, dict))
        answer = build_answer(prompt)
        if payload.get("stream"):
            self._stream(answer, payload)
        else:
            self._complete(answer, prompt)

    def _complete(self, answer: str, prompt: str) -> None:
        self._json(
            200,
            {
                "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": "mock-model",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": answer},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": max(1, len(prompt) // 4),
                    "completion_tokens": max(1, len(answer) // 4),
                    "total_tokens": max(2, (len(prompt) + len(answer)) // 4),
                },
            },
        )

    def _stream(self, answer: str, payload: dict) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        chunk_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
        for piece in _split(answer, 18):
            data = {
                "id": chunk_id,
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": "mock-model",
                "choices": [{"index": 0, "delta": {"content": piece}, "finish_reason": None}],
            }
            self.wfile.write(f"data: {json.dumps(data)}\n\n".encode())
            self.wfile.flush()
            time.sleep(CHUNK_DELAY)
        final = {
            "id": chunk_id,
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": "mock-model",
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 120, "completion_tokens": 90, "total_tokens": 210},
        }
        self.wfile.write(f"data: {json.dumps(final)}\n\n".encode())
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()
        self.close_connection = True


def _split(text: str, size: int) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)] or [""]


def build_answer(prompt: str) -> str:
    """Return a ReAct-style completion whose final answer looks like real output."""
    lowered = prompt.lower()
    if "итогов" in lowered or "final" in lowered and "report" in lowered:
        body = (
            "## Итог\n\n"
            "Команда отработала сценарий целиком. Ниже — сводка, собранная из результатов предыдущих шагов.\n\n"
            "### Ключевые выводы\n"
            "1. Собранные факты подтверждают основную гипотезу.\n"
            "2. Основной риск — нехватка данных по двум метрикам.\n"
            "3. Рекомендуется пилот на одном сегменте.\n\n"
            "### Следующие шаги\n"
            "- Проверить метрики на выборке за квартал.\n"
            "- Согласовать бюджет пилота.\n"
        )
    else:
        body = (
            "## Результат работы агента\n\n"
            "Собраны и структурированы материалы по теме.\n\n"
            "- Факт 1: направление растёт двузначными темпами.\n"
            "- Факт 2: основные игроки инвестируют в автоматизацию.\n"
            "- Факт 3: данных по малому бизнесу недостаточно.\n\n"
            "**Вывод:** тема перспективна, но требует проверки на узком сегменте.\n"
        )
    return f"Thought: I have enough information to answer.\nFinal Answer: {body}"


class MockLLMServer:
    def __init__(self, port: int = 8899) -> None:
        self.port = port
        self.server = ThreadingHTTPServer(("127.0.0.1", port), MockLLMHandler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/v1"

    def start(self) -> "MockLLMServer":
        self.thread.start()
        return self

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()


if __name__ == "__main__":
    server = MockLLMServer(8899).start()
    print(f"Mock LLM on {server.base_url}")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        server.stop()
