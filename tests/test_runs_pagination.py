"""Run history: pagination, filters and retention."""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import urllib.request
import uuid
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DATA = ROOT / ".setup" / f"runs-{uuid.uuid4().hex[:6]}"
for sub in ("crews", "runs", "outputs", "uploads", "logs"):
    (DATA / sub).mkdir(parents=True, exist_ok=True)
os.environ["CREWAI_STUDIO_DATA"] = str(DATA)
os.environ["CREWAI_STUDIO_NO_AUTH"] = "1"

from app.server import create_server  # noqa: E402
from app.store import Store  # noqa: E402

PORT = 7902
BASE = f"http://127.0.0.1:{PORT}"
failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print(("PASS  " if condition else "FAIL  ") + name + (f" — {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(name)


def make_run(index: int, days_ago: float = 0, status: str = "completed") -> dict:
    started = datetime.now() - timedelta(days=days_ago, seconds=index)
    return {
        "id": f"run-{index:03d}",
        "crew_id": "crew-a" if index % 2 == 0 else "crew-b",
        "crew_name": f"Проект {index % 3}",
        "status": status,
        "started_at": started.strftime("%Y-%m-%dT%H:%M:%S"),
        "finished_at": started.strftime("%Y-%m-%dT%H:%M:%S"),
        "duration": index,
        "usage": {"total_tokens": index * 10},
        "events": [],
        "result": {},
    }


def get(path: str) -> tuple[int, dict]:
    try:
        with urllib.request.urlopen(BASE + path, timeout=20) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def main() -> int:
    store = Store()
    store.save_settings({"runs_retention_days": 180})
    for index in range(60):
        store.save_run(make_run(index))

    server = create_server("127.0.0.1", PORT)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    time.sleep(0.6)

    try:
        status, payload = get("/api/runs")
        check("default page is 50", status == 200 and len(payload["runs"]) == 50 and payload["total"] == 60,
              f"{status} total={payload.get('total')}")

        status, payload = get("/api/runs?limit=10&offset=50")
        check("offset page returns the tail", status == 200 and len(payload["runs"]) == 10 and payload["offset"] == 50,
              str(payload)[:120])
        check("offset page does not repeat the first page", payload["runs"][0]["id"] not in {"run-059", "run-058"},
              str(payload["runs"][0]["id"]))

        status, payload = get("/api/runs?limit=200&offset=0")
        check("limit is capped at 200", len(payload["runs"]) == 60)
        status, payload = get("/api/runs?limit=abc&offset=-5")
        check("bad limit falls back", status == 200 and payload["limit"] == 50 and payload["offset"] == 0,
              str(payload)[:120])

        store.save_run(make_run(1000, status="failed"))
        status, payload = get("/api/runs?status=failed&limit=10")
        check("status filter works", status == 200 and all(item["status"] == "failed" for item in payload["runs"])
              and payload["total"] >= 1, str(payload)[:120])

        status, payload = get("/api/runs?crew_id=crew-a&limit=100")
        check("crew filter works", status == 200 and all(item["crew_id"] == "crew-a" for item in payload["runs"]),
              str(payload)[:120])

        # retention: a 300-day-old run must disappear with a 30-day policy
        old = make_run(2000, days_ago=300)
        store.save_run(old)
        check("old run is indexed", store.get_run("run-2000") is not None)
        store.save_settings({"runs_retention_days": 30})
        result = store.prune_runs()
        check("retention deletes the old run", result["deleted"] >= 1, str(result))
        check("old run file is gone", store.get_run("run-2000") is None)

        status, payload = get("/api/runs?limit=200")
        ids = {item["id"] for item in payload["runs"]}
        check("fresh runs survive pruning", "run-000" in ids and "run-059" in ids, str(len(ids)))

        store.save_settings({"runs_retention_days": 0})
        store.save_run(make_run(3000, days_ago=900))
        result = store.prune_runs()
        check("zero days keeps everything", result["deleted"] == 0 and store.get_run("run-3000") is not None, str(result))
    finally:
        server.shutdown()
        server.server_close()

    print("\nRUNS RESULT:", "PASS" if not failures else f"FAIL ({len(failures)}): {failures}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
