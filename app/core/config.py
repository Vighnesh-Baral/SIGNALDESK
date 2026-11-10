"""Application configuration for SIGNALDESK."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

APP_NAME = os.getenv("SIGNALDESK_APP_NAME", "SIGNALDESK")
APP_VERSION = "1.1.0"
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:4b")
OLLAMA_TIMEOUT_SECONDS = max(30, int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "240")))
# Conservative defaults for 6 GB VRAM GPUs. Override in .env only after benchmarking.
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
# Unauthenticated access is permitted only for local development with no public URL configured.
ALLOW_UNAUTHENTICATED_LOCAL = os.getenv("ALLOW_UNAUTHENTICATED_LOCAL", "true").strip().lower() in {"1", "true", "yes", "on"}
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "20"))
OUTPUT_DIR = Path(os.getenv("SIGNALDESK_OUTPUT_DIR", str(PROJECT_ROOT / "outputs")))
UPLOAD_DIR = Path(os.getenv("SIGNALDESK_UPLOAD_DIR", str(PROJECT_ROOT / "data" / "uploads")))
DEMO_DATA_DIR = PROJECT_ROOT / "data" / "sample"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
