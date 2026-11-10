"""Provider-neutral Nonilion webhook adapter.

The INNOVORTEX brief describes custom webhook/Bot API integration routes but does
not publish a concrete callback payload schema. This adapter therefore exposes a
small, documented normalized contract for mapping from Nonilion's import UI/API.
"""
from __future__ import annotations

import base64
import binascii
import re
from pathlib import Path
from typing import Any

from app.core.config import MAX_UPLOAD_MB, UPLOAD_DIR

ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".pdf", ".html", ".htm", ".txt", ".docx", ".json"}


def _safe_filename(name: str) -> str:
    cleaned = Path(str(name)).name
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", cleaned)
    return cleaned[:120] or "feedback.csv"


def extract_message(payload: dict[str, Any]) -> str:
    for key in ("message", "text", "content", "prompt"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def save_base64_attachment(attachment: dict[str, Any], job_id: str) -> Path:
    filename = _safe_filename(attachment.get("filename", "feedback.csv"))
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise ValueError("Attachment must be CSV, XLSX, PDF, HTML, TXT, DOCX or JSON.")
    encoded = attachment.get("content_base64")
    if not isinstance(encoded, str) or not encoded:
        raise ValueError("Attachment is missing content_base64.")
    max_encoded_chars = ((MAX_UPLOAD_MB * 1024 * 1024 + 2) // 3) * 4
    if len(encoded) > max_encoded_chars:
        raise ValueError(f"Attachment exceeds the {MAX_UPLOAD_MB} MB upload limit.")
    try:
        content = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("Attachment content_base64 is invalid.") from exc
    if len(content) > MAX_UPLOAD_MB * 1024 * 1024:
        raise ValueError(f"Attachment exceeds the {MAX_UPLOAD_MB} MB upload limit.")
    if not content:
        raise ValueError("Attachment is empty.")
    folder = UPLOAD_DIR / job_id
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / filename
    path.write_bytes(content)
    return path


def build_nonilion_reply(
    message: str,
    *,
    job_id: str | None = None,
    artifacts: list[dict] | None = None,
    ai_breakdown: dict[str, Any] | None = None,
    trend_analysis: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
    problem_clusters: dict[str, Any] | None = None,
    segment_analysis: dict[str, Any] | None = None,
    decision_summary: dict[str, Any] | None = None,
) -> dict:
    """Return a stable, machine-readable reply for the Nonilion adapter contract."""
    reply = {
        "response": message,
        "job_id": job_id,
        "artifacts": artifacts or [],
        "format": "signaldesk.nonilion.reply.v1",
    }
    if ai_breakdown is not None:
        reply["ai_breakdown"] = ai_breakdown
    if trend_analysis is not None:
        reply["trend_analysis"] = trend_analysis
    if warnings:
        reply["warnings"] = warnings
    if problem_clusters is not None:
        reply["problem_clusters"] = problem_clusters
    if segment_analysis is not None:
        reply["segment_analysis"] = segment_analysis
    if decision_summary is not None:
        reply["decision_summary"] = decision_summary
    return reply
