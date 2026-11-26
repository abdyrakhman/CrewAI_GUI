"""Paths, defaults and small helpers shared by the CrewAI Studio backend."""
from __future__ import annotations

import os
from typing import Any
from pathlib import Path

APP_NAME = "CrewAI Studio"
APP_VERSION = "1.0.0"

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("CREWAI_STUDIO_DATA") or (ROOT / "data")).expanduser().resolve()
CREWS_DIR = DATA_DIR / "crews"
RUNS_DIR = DATA_DIR / "runs"
OUTPUTS_DIR = DATA_DIR / "outputs"
UPLOADS_DIR = DATA_DIR / "uploads"
WEB_DIR = ROOT / "web"
SETTINGS_FILE = DATA_DIR / "settings.json"
LEGACY_ENV_FILE = ROOT / ".env"

for _p in (DATA_DIR, CREWS_DIR, RUNS_DIR, OUTPUTS_DIR, UPLOADS_DIR):
    _p.mkdir(parents=True, exist_ok=True)

DEFAULT_SETTINGS: dict = {
    "default_llm": "",
    "openai_api_key": "",
    "openai_base_url": "",
    "anthropic_api_key": "",
    "gemini_api_key": "",
    "openrouter_api_key": "",
    "groq_api_key": "",
    "deepseek_api_key": "",
    "serper_api_key": "",
    "extra_env": {},
    "live_stream": False,
    "max_rpm": 0,
    "llm_timeout": 120,
    "fs_roots": [],
    "allow_network_tools": [],
    "ui_language": "ru",
    "session_ttl_hours": 12,
    "runs_retention_days": 180,
    "run_timeout_minutes": 60,
    "max_iter_cap": 20,
    "theme": "dark",
}

# provider id -> (label, api-key setting field, base-url setting field, env vars to export)
PROVIDERS: list[dict] = [
    {
        "id": "openai",
        "label": "OpenAI",
        "key_field": "openai_api_key",
        "base_field": "openai_base_url",
        "env": ["OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_API_BASE"],
        "models": ["openai/gpt-4o", "openai/gpt-4o-mini", "openai/gpt-4.1", "openai/o3-mini"],
    },
    {
        "id": "anthropic",
        "label": "Anthropic",
        "key_field": "anthropic_api_key",
        "base_field": "",
        "env": ["ANTHROPIC_API_KEY"],
        "models": [
            "anthropic/claude-sonnet-4-5",
            "anthropic/claude-haiku-4-5",
            "anthropic/claude-opus-4-1",
        ],
    },
    {
        "id": "gemini",
        "label": "Google Gemini",
        "key_field": "gemini_api_key",
        "base_field": "",
        "env": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
        "models": ["gemini/gemini-2.5-pro", "gemini/gemini-2.5-flash"],
    },
    {
        "id": "openrouter",
        "label": "OpenRouter",
        "key_field": "openrouter_api_key",
        "base_field": "",
        "env": ["OPENROUTER_API_KEY"],
        "models": [
            "openrouter/openai/gpt-4o-mini",
            "openrouter/anthropic/claude-sonnet-4.5",
            "openrouter/deepseek/deepseek-chat",
        ],
    },
    {
        "id": "deepseek",
        "label": "DeepSeek",
        "key_field": "deepseek_api_key",
        "base_field": "",
        "env": ["DEEPSEEK_API_KEY"],
        "models": ["deepseek/deepseek-chat", "deepseek/deepseek-reasoner"],
    },
    {
        "id": "groq",
        "label": "Groq",
        "key_field": "groq_api_key",
        "base_field": "",
        "env": ["GROQ_API_KEY"],
        "models": ["groq/llama-3.3-70b-versatile"],
    },
    {
        "id": "ollama",
        "label": "Ollama (локально)",
        "key_field": "",
        "base_field": "",
        "env": [],
        "models": ["ollama/llama3.1", "ollama/qwen2.5", "ollama/mistral"],
    },
    {
        "id": "lmstudio",
        "label": "LM Studio / vLLM (OpenAI-совместимый)",
        "key_field": "",
        "base_field": "openai_base_url",
        "env": ["OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_API_BASE"],
        "models": ["openai/local-model"],
    },
]

PROVIDER_BY_ID = {p["id"]: p for p in PROVIDERS}


def ensure_dirs() -> None:
    for p in (DATA_DIR, CREWS_DIR, RUNS_DIR, OUTPUTS_DIR, UPLOADS_DIR):
        p.mkdir(parents=True, exist_ok=True)


_legacy_env_cache: dict[str, Any] = {"mtime": -1.0, "values": {}, "path": None}


def read_legacy_env() -> dict[str, str]:
    """Read KEY=VALUE pairs from an optional .env in the project root (cached by mtime)."""
    try:
        mtime = LEGACY_ENV_FILE.stat().st_mtime if LEGACY_ENV_FILE.exists() else 0.0
    except OSError:
        return {}
    if _legacy_env_cache["mtime"] == mtime and _legacy_env_cache["path"] == str(LEGACY_ENV_FILE):
        return dict(_legacy_env_cache["values"])
    values: dict[str, str] = {}
    if mtime:
        try:
            for raw in LEGACY_ENV_FILE.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip().removeprefix("export ").strip()
                val = val.strip().strip('"').strip("'")
                if key:
                    values[key] = val
        except OSError:
            values = {}
    _legacy_env_cache.update({"mtime": mtime, "values": values, "path": str(LEGACY_ENV_FILE)})
    return dict(values)


def guess_provider(model: str) -> str:
    """Best-effort provider id for a bare model name."""
    m = (model or "").lower()
    if m.startswith(("gpt-", "o1", "o3", "o4", "chatgpt", "text-embedding")):
        return "openai"
    if m.startswith("claude"):
        return "anthropic"
    if m.startswith("gemini"):
        return "gemini"
    if m.startswith("deepseek"):
        return "deepseek"
    if m.startswith(("llama", "mixtral", "qwen", "phi")):
        return "ollama"
    return "openai"


def normalize_model(model: str) -> str:
    """CrewAI wants provider-prefixed model ids: ``openai/gpt-4o``."""
    model = (model or "").strip()
    if not model:
        return model
    if "/" in model:
        return model
    return f"{guess_provider(model)}/{model}"


def is_configured_for(model: str, settings: dict) -> bool:
    """Whether a model can plausibly run with the current credentials."""
    model = (model or "").strip()
    if not model:
        return False
    provider = model.split("/", 1)[0] if "/" in model else guess_provider(model)
    if provider in {"ollama", "lmstudio"}:
        return True
    if provider == "openai" and "/" in model and model.startswith("openai/"):
        return bool(settings.get("openai_api_key")) or bool(os.environ.get("OPENAI_API_KEY"))
    spec = PROVIDER_BY_ID.get(provider)
    if spec is None:
        return True
    if not spec["key_field"]:
        return True
    return bool(settings.get(spec["key_field"])) or any(bool(os.environ.get(e)) for e in spec["env"])
