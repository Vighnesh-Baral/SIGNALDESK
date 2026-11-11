"""Centralised SIGNALDESK configuration.

Secrets are read from environment variables and are never exposed through health APIs.
Local development defaults to SQLite + project-local files; production should set
DATABASE_URL and SIGNALDESK_STORAGE_ROOT=/var/data on Render.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

APP_NAME = os.getenv("SIGNALDESK_APP_NAME", "SIGNALDESK")
APP_VERSION = "1.3.0"

# Storage root: set to /var/data on Render and mount a persistent disk there.
def _configured_path(name: str, default: Path) -> Path:
    value = os.getenv(name, "").strip()
    return Path(value).expanduser().resolve() if value else default.expanduser().resolve()


STORAGE_ROOT = _configured_path("SIGNALDESK_STORAGE_ROOT", PROJECT_ROOT)
UPLOAD_DIR = _configured_path("SIGNALDESK_UPLOAD_DIR", STORAGE_ROOT / "data" / "uploads")
OUTPUT_DIR = _configured_path("SIGNALDESK_OUTPUT_DIR", STORAGE_ROOT / "outputs")
PROCESSED_DIR = _configured_path("SIGNALDESK_PROCESSED_DIR", STORAGE_ROOT / "data" / "processed")
TEMP_DIR = _configured_path("SIGNALDESK_TEMP_DIR", STORAGE_ROOT / "temp")
RETAIN_SOURCE_UPLOADS = os.getenv("RETAIN_SOURCE_UPLOADS", "true").strip().lower() in {"1", "true", "yes", "on"}
SOURCE_UPLOAD_RETENTION_DAYS = max(1, min(int(os.getenv("SOURCE_UPLOAD_RETENTION_DAYS", "30")), 3650))
ARTIFACT_RETENTION_DAYS = max(1, min(int(os.getenv("ARTIFACT_RETENTION_DAYS", "90")), 3650))
TEMP_RETENTION_HOURS = max(1, min(int(os.getenv("TEMP_RETENTION_HOURS", "24")), 720))

for directory in (UPLOAD_DIR, OUTPUT_DIR, PROCESSED_DIR, TEMP_DIR):
    directory.mkdir(parents=True, exist_ok=True)

# LLM provider settings. Supported providers: ollama, groq, openrouter.
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama").strip().lower()
LLM_API_KEY = os.getenv("LLM_API_KEY", "").strip()
LLM_MODEL = os.getenv("LLM_MODEL", "").strip()
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "").strip().rstrip("/")
LLM_TIMEOUT_SECONDS = max(10, min(int(os.getenv("LLM_TIMEOUT_SECONDS", "120")), 600))
LLM_MAX_TOKENS = max(128, min(int(os.getenv("LLM_MAX_TOKENS", "2048")), 8192))
LLM_SITE_URL = os.getenv("LLM_SITE_URL", "").strip()
LLM_SITE_NAME = os.getenv("LLM_SITE_NAME", APP_NAME).strip()
LLM_FALLBACK_PROVIDER = os.getenv("LLM_FALLBACK_PROVIDER", "").strip().lower()
LLM_FALLBACK_API_KEY = os.getenv("LLM_FALLBACK_API_KEY", "").strip()
LLM_FALLBACK_MODEL = os.getenv("LLM_FALLBACK_MODEL", "").strip()
LLM_FALLBACK_BASE_URL = os.getenv("LLM_FALLBACK_BASE_URL", "").strip().rstrip("/")

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:4b")
OLLAMA_TIMEOUT_SECONDS = max(30, int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "240")))
OLLAMA_BATCH_SIZE = max(1, min(int(os.getenv("OLLAMA_BATCH_SIZE", "5")), 20))
OLLAMA_NUM_CTX = max(2048, min(int(os.getenv("OLLAMA_NUM_CTX", "4096")), 32768))
OLLAMA_NUM_BATCH = max(32, min(int(os.getenv("OLLAMA_NUM_BATCH", "128")), 2048))
OLLAMA_NUM_PREDICT = max(128, min(int(os.getenv("OLLAMA_NUM_PREDICT", "512")), 4096))
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "5m")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "").strip()
SIMILARITY_THRESHOLD = max(0.50, min(float(os.getenv("SIMILARITY_THRESHOLD", "0.62")), 0.98))
OLLAMA_EMBED_SIMILARITY_THRESHOLD = max(0.60, min(float(os.getenv("OLLAMA_EMBED_SIMILARITY_THRESHOLD", "0.78")), 0.99))
CLUSTERING_MAX_RECORDS = max(100, min(int(os.getenv("CLUSTERING_MAX_RECORDS", "2500")), 10000))
PDF_OCR_ENABLED = os.getenv("PDF_OCR_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}

SIGNALDESK_API_TOKEN = os.getenv("SIGNALDESK_API_TOKEN", "")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
ALLOW_UNAUTHENTICATED_LOCAL = os.getenv("ALLOW_UNAUTHENTICATED_LOCAL", "true").strip().lower() in {"1", "true", "yes", "on"}
MAX_UPLOAD_MB = max(1, min(int(os.getenv("MAX_UPLOAD_MB", "20")), 200))

# Database. PostgreSQL is recommended for hosted deployments; SQLite is the local
# development default. Supabase's pooled or direct PostgreSQL URL can be supplied.
def _normalise_database_url(value: str) -> str:
    url = value.strip()
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url

_default_db = f"sqlite:///{(STORAGE_ROOT / 'data' / 'signaldesk.db').as_posix()}"
DATABASE_URL = _normalise_database_url(os.getenv("DATABASE_URL", "").strip() or _default_db)
DATABASE_REQUIRED = os.getenv("DATABASE_REQUIRED", "false").strip().lower() in {"1", "true", "yes", "on"}
DATABASE_POOL_SIZE = max(1, min(int(os.getenv("DATABASE_POOL_SIZE", "5")), 20))
DATABASE_MAX_OVERFLOW = max(0, min(int(os.getenv("DATABASE_MAX_OVERFLOW", "5")), 50))

DEMO_DATA_DIR = PROJECT_ROOT / "data" / "sample"
