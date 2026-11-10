"""SIGNALDESK FastAPI application and webhook entry point."""
from __future__ import annotations

import json
import logging
import re
import secrets
import shutil
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import requests
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from app.core.config import (
    ALLOW_UNAUTHENTICATED_LOCAL, APP_NAME, APP_VERSION, MAX_UPLOAD_MB,
    OLLAMA_BASE_URL, OLLAMA_BATCH_SIZE, OLLAMA_KEEP_ALIVE, OLLAMA_MODEL,
    OLLAMA_NUM_BATCH, OLLAMA_NUM_CTX, OLLAMA_NUM_PREDICT, OLLAMA_EMBED_MODEL,
    OUTPUT_DIR, PUBLIC_BASE_URL, SIGNALDESK_API_TOKEN, UPLOAD_DIR,
)
from app.integrations.nonilion import build_nonilion_reply, extract_message, save_base64_attachment
import pandas as pd

from app.services.agent import analyze_dataframe, analyze_file
from app.services.llm_service import OllamaError
from app.services.report_generator import generate_reports
from app.services.research_assistant import answer_research_question
from app.services.comparison_engine import compare_analyses
from app.integrations.product_tools import (
    integration_status, build_provider_preview, create_provider_item,
    IntegrationNotConfiguredError, IntegrationProviderError,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("signaldesk")

app = FastAPI(
    title="SIGNALDESK API",
    description=(
        "Evidence-first customer research agent. Processes CSV, XLSX, PDF, HTML, TXT, DOCX and JSON uploads, "
        "plus pasted or single customer feedback; classifies themes with a local Ollama model, "
        "calculates counts in Python, "
        "and generates source-traceable reports."
    ),
    version=APP_VERSION,
)


class NonilionWebhookPayload(BaseModel):
    """Normalized payload to map from the Nonilion custom webhook/Bot API."""
    event_type: str = "message"
    conversation_id: str | None = None
    sender_id: str | None = None
    message: str | None = None
    text: str | None = None
    attachments: list[dict[str, Any]] = Field(default_factory=list)


class ManualFeedbackPayload(BaseModel):
    """Text-first submission payload using the same classifier pipeline as files."""
    mode: str = "paste"
    feedback_text: str
    customer_id: str | None = None


class ResearchQuestionPayload(BaseModel):
    question: str = Field(min_length=1, max_length=1000)


class ComparePayload(BaseModel):
    baseline_job_id: str = Field(min_length=32, max_length=32)
    current_job_id: str = Field(min_length=32, max_length=32)


class IntegrationActionPayload(BaseModel):
    finding_id: str | None = None
    confirm: bool = False


def verify_api_token(
    request: Request, authorization: str | None = Header(default=None)
) -> None:
    """Require a bearer token except for explicitly allowed localhost development."""
    if not SIGNALDESK_API_TOKEN:
        host_header = request.headers.get("host", "")
        request_host = (urlsplit(f"//{host_header}").hostname or "").casefold()
        client_host = (request.client.host if request.client else "").casefold()
        local_hosts = {"localhost", "127.0.0.1", "::1", "testserver", "testclient"}
        if (
            ALLOW_UNAUTHENTICATED_LOCAL
            and not PUBLIC_BASE_URL
            and request_host in local_hosts
            and client_host in local_hosts
        ):
            return
        raise HTTPException(
            status_code=503,
            detail="SIGNALDESK_API_TOKEN must be configured before public access is enabled.",
        )
    expected = f"Bearer {SIGNALDESK_API_TOKEN}"
    if not authorization or not secrets.compare_digest(authorization, expected):
        raise HTTPException(status_code=401, detail="Invalid or missing SIGNALDESK API token.")


def _safe_filename(name: str) -> str:
    clean = Path(name).name
    clean = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in clean)
    return clean[:120] or "feedback.csv"


def _public_artifact_urls(job_id: str) -> list[dict[str, str]]:
    prefix = PUBLIC_BASE_URL
    return [
        {"type": "excel", "name": "SIGNALDESK research workbook", "url": f"{prefix}/api/jobs/{job_id}/report.xlsx"},
        {"type": "pdf", "name": "SIGNALDESK research brief", "url": f"{prefix}/api/jobs/{job_id}/report.pdf"},
        {"type": "chart", "name": "Theme frequency chart", "url": f"{prefix}/api/jobs/{job_id}/chart.png"},
        {"type": "product_decision_pack", "name": "Product decision pack (Markdown)", "url": f"{prefix}/api/jobs/{job_id}/decision-pack.md"},
    ]


def _classification_breakdown(result: dict) -> dict[str, Any]:
    """Summarise per-record classifier provenance without assuming model success."""
    records = result.get("classified_records")
    if records is None or "classification_method" not in records.columns:
        total_records = int(result.get("dataset", {}).get("total_valid_records", 0))
        return {
            "qwen3_records": 0,
            "fallback_records": 0,
            "unreported_records": total_records,
            "total_records": total_records,
            "total_classified": 0,
            "qwen3_percentage": 0.0,
            "fallback_percentage": 0.0,
        }

    methods = records["classification_method"].fillna("").astype(str)
    qwen3_count = int((methods == "qwen3").sum())
    fallback_count = int((methods == "keyword_fallback").sum())
    total_records = int(len(records))
    classified_count = qwen3_count + fallback_count
    unreported = max(0, total_records - classified_count)
    return {
        "qwen3_records": qwen3_count,
        "fallback_records": fallback_count,
        "unreported_records": unreported,
        "total_records": total_records,
        "total_classified": classified_count,
        "qwen3_percentage": round((qwen3_count / total_records) * 100, 1) if total_records else 0.0,
        "fallback_percentage": round((fallback_count / total_records) * 100, 1) if total_records else 0.0,
    }


def _public_result(result: dict) -> dict:
    return {
        "dataset": result["dataset"],
        "summary": result["summary"],
        "findings": result["findings"],
        "trend_analysis": result.get("trend_analysis", {"available": False, "reason": "Trend analysis was not generated."}),
        "warnings": result["warnings"],
        "ai_breakdown": result["ai_breakdown"],
        "ingestion": result.get("ingestion", {}),
        "problem_clusters": result.get("problem_clusters", {"available": False, "clusters": []}),
        "segment_analysis": result.get("segment_analysis", {"available": False, "dimensions": []}),
        "decision_pack": result.get("decision_pack", {"available": False, "documents": []}),
    }


def _complete_analysis(result: dict, job_id: str) -> dict:
    """Attach provenance, persist the processed dataset and generate reports."""
    output_folder = OUTPUT_DIR / job_id
    output_folder.mkdir(parents=True, exist_ok=True)
    result["ai_breakdown"] = _classification_breakdown(result)
    result["warnings"] = list(result.get("warnings", []))
    if result["ai_breakdown"]["fallback_records"] > 0:
        result["warnings"].append(
            f"Classification transparency: {result['ai_breakdown']['qwen3_records']} records "
            f"were classified by Qwen3 and {result['ai_breakdown']['fallback_records']} "
            "records used the keyword fallback."
        )
    if result["ai_breakdown"]["unreported_records"] > 0:
        result["warnings"].append(
            f"{result['ai_breakdown']['unreported_records']} records have no recognised "
            "classification-method label. Review the processed-feedback export."
        )

    result["classified_records"].to_csv(
        output_folder / "classified_feedback.csv", index=False, encoding="utf-8-sig"
    )
    reports = generate_reports(result, output_folder)
    public = _public_result(result)
    decision_pack = public.get("decision_pack", {})
    (output_folder / "decision_pack.json").write_text(
        json.dumps(decision_pack, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    markdown_parts = ["# SIGNALDESK Product Decision Pack", "", str(decision_pack.get("limitations", "")), ""]
    for document in decision_pack.get("documents", []):
        markdown_parts.extend([document.get("bug_report_markdown", ""), "\n---\n", document.get("prd_markdown", ""), "\n---\n", document.get("user_stories_markdown", ""), "\n---\n"])
    decision_path = output_folder / "product_decision_pack.md"
    decision_path.write_text("\n".join(markdown_parts), encoding="utf-8")
    public["artifacts_generated"] = ["excel", "pdf", "chart", "product_decision_pack"]
    (output_folder / "result.json").write_text(
        json.dumps(public, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {"public": public, "reports": reports}


def _run_analysis(file_path: Path, job_id: str, feedback_column: str | None = None,
                  source_id_column: str | None = None) -> dict:
    result = analyze_file(
        file_path,
        feedback_column=feedback_column or None,
        source_id_column=source_id_column or None,
    )
    return _complete_analysis(result, job_id)


def _split_manual_feedback(payload: ManualFeedbackPayload) -> list[str]:
    """Convert paste/single text input into individual feedback records."""
    text = (payload.feedback_text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        raise ValueError("Enter at least one customer feedback comment.")
    if len(text) > 500_000:
        raise ValueError("Manual feedback is too large. The maximum is 500,000 characters.")
    if payload.mode not in {"paste", "single"}:
        raise ValueError("mode must be either 'paste' or 'single'.")

    if payload.mode == "single":
        records = [text]
    else:
        # Blank lines or a line containing --- separate comments. Single newlines
        # remain within a comment so multi-line support messages are preserved.
        records = re.split(r"\n[ \t]*\n|^[ \t]*---+[ \t]*$", text, flags=re.MULTILINE)
        records = [item.strip() for item in records if item.strip()]

    if not records:
        raise ValueError("No non-empty customer feedback comments were found.")
    if len(records) > 500:
        raise ValueError("A manual submission can contain at most 500 feedback records.")
    if payload.customer_id and len(payload.customer_id.strip()) > 160:
        raise ValueError("Customer ID must be 160 characters or fewer.")
    return records


def _run_manual_analysis(payload: ManualFeedbackPayload, job_id: str) -> dict:
    records = _split_manual_feedback(payload)
    raw = pd.DataFrame({"Feedback": records, "source_type": "manual_text"})
    customer_id = (payload.customer_id or "").strip()
    source_id_column = None
    if customer_id:
        raw["Customer_ID"] = customer_id
        source_id_column = "Customer_ID"
    result = analyze_dataframe(
        raw,
        dataset_name=f"manual_{payload.mode}_submission.txt",
        feedback_column="Feedback",
        source_id_column=source_id_column,
        source_row_offset=1,
    )
    return _complete_analysis(result, job_id)


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def landing_page() -> str:
    """Public-facing product overview and marketing landing page."""
    html_path = Path(__file__).parent / "static" / "home.html"
    return html_path.read_text(encoding="utf-8")


@app.get("/app", response_class=HTMLResponse, include_in_schema=False)
def dashboard() -> str:
    """SIGNALDESK application workspace."""
    html_path = Path(__file__).parent / "static" / "index.html"
    return html_path.read_text(encoding="utf-8")


@app.get("/api/health")
def health() -> dict:
    model_available = False
    model_error = None
    try:
        response = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=2)
        response.raise_for_status()
        model_names = [item.get("name", "") for item in response.json().get("models", [])]
        model_available = any(name == OLLAMA_MODEL or name.startswith(OLLAMA_MODEL + ":") for name in model_names)
    except requests.RequestException as exc:
        model_error = str(exc)
    return {
        "status": "ok",
        "application": APP_NAME,
        "supported_submission_modes": ["multi_format_file_upload", "paste_feedback", "single_complaint"],
        "supported_uploads": [".csv", ".xlsx", ".pdf", ".html", ".htm", ".txt", ".docx", ".json"],
        "intelligence_features": ["emotion_and_urgency_signals", "evidence_breadth", "problem_investigation_cards", "date_aware_trend_comparison", "grounded_dataset_qa", "similarity_problem_clustering", "customer_segmentation", "before_after_comparison", "bug_prd_user_story_drafts", "product_tool_integrations"],
        "clustering_embedding_model_configured": bool(OLLAMA_EMBED_MODEL),
        "version": APP_VERSION,
        "ollama_reachable": model_error is None,
        "configured_model": OLLAMA_MODEL,
        "inference_settings": {
            "batch_size": OLLAMA_BATCH_SIZE,
            "context_window": OLLAMA_NUM_CTX,
            "prompt_batch_tokens": OLLAMA_NUM_BATCH,
            "max_output_tokens": OLLAMA_NUM_PREDICT,
            "keep_alive": OLLAMA_KEEP_ALIVE,
        },
        "model_available": model_available,
        "model_status": "available" if model_available else (
            "ollama_unreachable" if model_error else "model_not_installed"
        ),
        "api_token_configured": bool(SIGNALDESK_API_TOKEN),
        "public_base_url_configured": bool(PUBLIC_BASE_URL),
        "authentication_mode": ("bearer_token" if SIGNALDESK_API_TOKEN else ("local_only" if not PUBLIC_BASE_URL and ALLOW_UNAUTHENTICATED_LOCAL else "blocked_until_token_configured")),
        "public_exposure_warning": None if SIGNALDESK_API_TOKEN else "Set SIGNALDESK_API_TOKEN before exposing this service publicly.",
        "product_integrations": integration_status(),
    }


@app.post("/api/analyze", dependencies=[Depends(verify_api_token)])
async def analyze_upload(
    file: UploadFile = File(...),
    feedback_column: str = Form(default=""),
    source_id_column: str = Form(default=""),
) -> dict:
    filename = _safe_filename(file.filename or "feedback.csv")
    if Path(filename).suffix.lower() not in {".csv", ".xlsx", ".pdf", ".html", ".htm", ".txt", ".docx", ".json"}:
        raise HTTPException(status_code=400, detail="Supported formats: CSV, XLSX, PDF, HTML, TXT, DOCX and JSON.")
    job_id = uuid.uuid4().hex
    upload_folder = UPLOAD_DIR / job_id
    upload_folder.mkdir(parents=True, exist_ok=True)
    target = upload_folder / filename
    total = 0
    try:
        with target.open("wb") as destination:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_UPLOAD_MB * 1024 * 1024:
                    raise HTTPException(status_code=413, detail=f"File exceeds {MAX_UPLOAD_MB} MB.")
                destination.write(chunk)
        if total == 0:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")
        try:
            result = await run_in_threadpool(
                _run_analysis, target, job_id, feedback_column, source_id_column
            )
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            logger.exception("Analysis failed for job %s", job_id)
            raise HTTPException(status_code=500, detail=f"Analysis failed: {exc}") from exc
        return {
            "job_id": job_id,
            **result["public"],
            "artifacts": _public_artifact_urls(job_id),
        }
    finally:
        await file.close()
        # Source uploads are working files only; retain reports and processed records,
        # but remove the original uploaded file after analysis to reduce data retention.
        shutil.rmtree(upload_folder, ignore_errors=True)


@app.post("/api/analyze/text", dependencies=[Depends(verify_api_token)])
async def analyze_manual_feedback(payload: ManualFeedbackPayload) -> dict:
    """Analyse pasted feedback or a single complaint through the shared pipeline."""
    job_id = uuid.uuid4().hex
    try:
        result = await run_in_threadpool(_run_manual_analysis, payload, job_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Manual feedback analysis failed for job %s", job_id)
        raise HTTPException(status_code=500, detail="Manual feedback analysis failed.") from exc
    return {
        "job_id": job_id,
        **result["public"],
        "artifacts": _public_artifact_urls(job_id),
    }


@app.post("/api/jobs/{job_id}/ask", dependencies=[Depends(verify_api_token)])
async def ask_about_analysis(job_id: str, payload: ResearchQuestionPayload) -> dict:
    """Answer a question using only source records from a saved analysis."""
    _validate_job_id(job_id)
    job_folder = OUTPUT_DIR / job_id
    result_path = job_folder / "result.json"
    records_path = job_folder / "classified_feedback.csv"
    if not result_path.is_file() or not records_path.is_file():
        raise HTTPException(status_code=404, detail="Analysis job not found or source records are unavailable.")
    try:
        public = json.loads(result_path.read_text(encoding="utf-8"))
        records = pd.read_csv(records_path, dtype=object, keep_default_na=False)
        answer = await run_in_threadpool(
            answer_research_question,
            payload.question,
            records,
            public.get("findings", []),
        )
        return {"job_id": job_id, "question": payload.question, **answer}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Research question failed for job %s", job_id)
        raise HTTPException(status_code=500, detail="Could not answer this question from the saved analysis.") from exc


@app.post("/api/jobs/compare", dependencies=[Depends(verify_api_token)])
async def compare_saved_analyses(payload: ComparePayload) -> dict:
    """Compare two prior analyses by observed theme prevalence and segment patterns."""
    _validate_job_id(payload.baseline_job_id)
    _validate_job_id(payload.current_job_id)
    if payload.baseline_job_id == payload.current_job_id:
        raise HTTPException(status_code=400, detail="Choose two different analysis jobs.")
    loaded = []
    for job_id in (payload.baseline_job_id, payload.current_job_id):
        folder = OUTPUT_DIR / job_id
        result_path = folder / "result.json"
        records_path = folder / "classified_feedback.csv"
        if not result_path.is_file() or not records_path.is_file():
            raise HTTPException(status_code=404, detail=f"Analysis job {job_id} was not found.")
        try:
            saved = json.loads(result_path.read_text(encoding="utf-8"))
            records = pd.read_csv(records_path, dtype=object, keep_default_na=False)
        except Exception as exc:
            raise HTTPException(status_code=500, detail="Saved analysis could not be read.") from exc
        loaded.append({"dataset": saved.get("dataset", {}), "classified_records": records})
    return compare_analyses(loaded[0], loaded[1])


@app.get("/api/integrations/status", dependencies=[Depends(verify_api_token)])
def get_integration_status() -> dict:
    return {"integrations": integration_status(), "write_policy": "Preview is read-only. External writes require explicit confirm=true and configured credentials."}


def _load_decision_document(job_id: str, finding_id: str | None = None) -> dict:
    _validate_job_id(job_id)
    path = OUTPUT_DIR / job_id / "decision_pack.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Product decision pack not found for this analysis.")
    decision_pack = json.loads(path.read_text(encoding="utf-8"))
    documents = decision_pack.get("documents", [])
    if finding_id:
        document = next((item for item in documents if item.get("finding_id") == finding_id), None)
        if document is None:
            raise HTTPException(status_code=404, detail="Finding ID was not found in this analysis.")
        return document
    if not documents:
        raise HTTPException(status_code=404, detail="No product decision documents are available.")
    return documents[0]


@app.post("/api/jobs/{job_id}/integrations/{provider}/preview", dependencies=[Depends(verify_api_token)])
def preview_product_integration(job_id: str, provider: str, payload: IntegrationActionPayload) -> dict:
    try:
        document = _load_decision_document(job_id, payload.finding_id)
        return build_provider_preview(provider.casefold(), document)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/jobs/{job_id}/integrations/{provider}", dependencies=[Depends(verify_api_token)])
def create_product_integration_item(job_id: str, provider: str, payload: IntegrationActionPayload) -> dict:
    if not payload.confirm:
        raise HTTPException(status_code=400, detail="External write requires confirm=true after reviewing the preview.")
    try:
        document = _load_decision_document(job_id, payload.finding_id)
        return create_provider_item(provider.casefold(), document)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except IntegrationNotConfiguredError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except IntegrationProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except requests.RequestException as exc:
        logger.exception("External integration failed: %s", provider)
        raise HTTPException(status_code=502, detail=f"{provider.title()} request failed. Check credentials and provider status.") from exc


@app.get("/api/jobs/{job_id}/decision-pack.md")
def download_decision_pack(job_id: str):
    _validate_job_id(job_id)
    path = OUTPUT_DIR / job_id / "product_decision_pack.md"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Product decision pack not found.")
    return FileResponse(path, filename="SIGNALDESK_Product_Decision_Pack.md", media_type="text/markdown")


def _validate_job_id(job_id: str) -> None:
    if len(job_id) != 32 or any(ch not in "0123456789abcdef" for ch in job_id):
        raise HTTPException(status_code=404, detail="Analysis job not found.")


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    _validate_job_id(job_id)
    result_path = OUTPUT_DIR / job_id / "result.json"
    if not result_path.is_file():
        raise HTTPException(status_code=404, detail="Analysis job not found.")
    data = json.loads(result_path.read_text(encoding="utf-8"))
    return {"job_id": job_id, **data, "artifacts": _public_artifact_urls(job_id)}


@app.get("/api/jobs/{job_id}/report.xlsx")
def download_excel(job_id: str):
    _validate_job_id(job_id)
    path = OUTPUT_DIR / job_id / "signaldesk_research_report.xlsx"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Excel report not found.")
    return FileResponse(path, filename="SIGNALDESK_Research_Report.xlsx")


@app.get("/api/jobs/{job_id}/report.pdf")
def download_pdf(job_id: str):
    _validate_job_id(job_id)
    path = OUTPUT_DIR / job_id / "signaldesk_research_brief.pdf"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="PDF report not found.")
    return FileResponse(path, filename="SIGNALDESK_Research_Brief.pdf")


@app.get("/api/jobs/{job_id}/chart.png")
def download_chart(job_id: str):
    _validate_job_id(job_id)
    path = OUTPUT_DIR / job_id / "theme_frequencies.png"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Chart not found.")
    return FileResponse(path, filename="SIGNALDESK_Theme_Frequencies.png")


@app.get("/api/nonilion/manifest")
def nonilion_manifest() -> dict:
    """Integration metadata for mapping a Nonilion custom agent/webhook."""
    return {
        "name": "SIGNALDESK",
        "version": APP_VERSION,
        "protocol": "signaldesk.nonilion.reply.v1",
        "method": "POST",
        "endpoint": "/api/nonilion/webhook",
        "authentication": "Authorization: Bearer <SIGNALDESK_API_TOKEN>",
        "request_example": {
            "event_type": "message",
            "conversation_id": "conversation-123",
            "sender_id": "user-123",
            "message": "Analyse the attached customer feedback and identify the top five issues.",
            "attachments": [{
                "filename": "customer_feedback.csv",
                "content_base64": "<base64-encoded CSV or XLSX bytes>",
            }],
        },
        "response_fields": ["response", "job_id", "artifacts", "format", "ai_breakdown", "trend_analysis", "problem_clusters", "segment_analysis", "decision_summary", "warnings"],
        "supported_uploads": [".csv", ".xlsx", ".pdf", ".html", ".htm", ".txt", ".docx", ".json"],
        "supported_submission_modes": ["file_upload", "paste_feedback", "single_complaint"],
        "text_endpoint": "/api/analyze/text",
        "public_artifacts_configured": bool(PUBLIC_BASE_URL),
        "research_question_endpoint": "/api/jobs/{job_id}/ask",
        "note": "This is a normalized adapter contract, not a verified native Nonilion payload. Map Nonilion's actual import fields to this schema. Configure PUBLIC_BASE_URL for absolute artifact links and SIGNALDESK_API_TOKEN before public exposure.",
    }


@app.post("/api/nonilion/webhook", dependencies=[Depends(verify_api_token)])
def nonilion_webhook(payload: NonilionWebhookPayload) -> dict:
    """Receive normalized Nonilion agent events and return concise replies."""
    message = extract_message(payload.model_dump())
    if not payload.attachments:
        if message.casefold() in {"/help", "help", "what can you do?"}:
            return build_nonilion_reply(
                "I am SIGNALDESK. Upload CSV, XLSX, PDF, HTML, TXT, DOCX or JSON feedback, paste multiple customer comments, or send one complaint. "
                "I identify recurring problems, show emotion and urgency language signals, create evidence-backed investigation cards, "
                "compare date-stamped feedback periods, answer questions about the dataset and return research reports."
            )
        if not message:
            return build_nonilion_reply(
                "Please upload a customer-feedback file (CSV, XLSX, PDF, HTML, TXT, DOCX or JSON), paste multiple comments, or send one customer complaint."
            )
        try:
            manual_payload = ManualFeedbackPayload(mode="single", feedback_text=message)
            manual_job_id = uuid.uuid4().hex
            result = _run_manual_analysis(manual_payload, manual_job_id)
            public = result["public"]
            top_finding = public["summary"].get("top_findings", [])
            category = top_finding[0]["theme"] if top_finding else "Unclassified"
            evidence = public["findings"][0]["evidence"][0] if public["findings"] and public["findings"][0]["evidence"] else None
            response = (
                "Single-feedback analysis\n"
                f"Category: {category}\n"
                f"Records analysed: {public['dataset']['total_valid_records']}\n"
                "The complaint was processed through the same classification and evidence pipeline "
                "used for uploaded files."
            )
            if evidence:
                response += f"\nEvidence record: {evidence['record_id']} (source row {evidence['source_row']})"
            response += "\nFor frequency analysis, paste multiple comments or upload a supported feedback file."
            return build_nonilion_reply(
                response,
                job_id=manual_job_id,
                artifacts=_public_artifact_urls(manual_job_id),
                ai_breakdown=public["ai_breakdown"],
                trend_analysis=public.get("trend_analysis"),
                problem_clusters=public.get("problem_clusters"),
                segment_analysis=public.get("segment_analysis"),
                decision_summary={"cards": public.get("decision_pack", {}).get("prioritised_decision_cards", [])[:5], "limitations": public.get("decision_pack", {}).get("limitations")},
                warnings=public.get("warnings", []),
            )
        except (OllamaError, ValueError) as exc:
            return build_nonilion_reply(f"I could not analyse that message: {exc}")

    if len(payload.attachments) > 1:
        return build_nonilion_reply("Please send one feedback file per analysis request.")

    job_id = uuid.uuid4().hex
    file_path: Path | None = None
    try:
        file_path = save_base64_attachment(payload.attachments[0], job_id)
        result = _run_analysis(file_path, job_id)
    except (ValueError, OSError) as exc:
        return build_nonilion_reply(f"I could not process the attachment: {exc}")
    finally:
        if file_path is not None:
            shutil.rmtree(file_path.parent, ignore_errors=True)
    public = result["public"]
    top_lines = [
        f"{item['rank']}. {item['theme']} — {item['mentions']} mentions ({item['prevalence_pct']}%). "
        f"Suggested follow-up: {item['suggested_next_step']}"
        for item in public["summary"]["top_findings"]
    ]
    evidence_lines = []
    for finding in public["findings"][:3]:
        for evidence in finding["evidence"][:2]:
            source_label = f", customer {evidence['source_id']}" if evidence.get("source_id") else ""
            quote = evidence["quote"].replace("\n", " ").strip()
            evidence_lines.append(
                f"- {finding['finding_id']} / {finding['theme']}: \"{quote}\" "
                f"(record {evidence['record_id']}{source_label}, source row {evidence['source_row']})"
            )
    trend_analysis = public.get("trend_analysis", {})
    if trend_analysis.get("available"):
        trend_lines = [
            f"- {item['theme']}: {item['previous_mentions']} to {item['recent_mentions']} "
            f"({item['signal']})"
            for item in trend_analysis.get("trends", []) if item.get("signal") in {"Emerging", "Newly observed"}
        ]
        trend_text = "\n".join(trend_lines) if trend_lines else "No emerging theme met the configured signal threshold."
    else:
        trend_text = f"Unavailable: {trend_analysis.get('reason', 'No date comparison was possible.')}"
    response = (
        f"Analysis complete: {public['dataset']['total_valid_records']} valid feedback records, "
        f"{public['dataset']['exact_duplicate_mentions']} exact duplicate mentions retained.\n"
        f"Classification method: {public['ai_breakdown']['qwen3_records']} Qwen3, "
        f"{public['ai_breakdown']['fallback_records']} keyword fallback.\n\n"
        "Top themes by observed frequency:\n" + "\n".join(top_lines) +
        "\n\nEmerging problem signals:\n" + trend_text +
        "\n\nRepresentative source evidence:\n" + "\n".join(evidence_lines) +
        "\n\nCounts are computed from source records. Suggestions are analyst follow-ups to validate, "
        "not measured impacts. Ranking reflects frequency, not measured severity."
    )
    integration_warnings = []
    if not PUBLIC_BASE_URL:
        integration_warnings.append(
            "PUBLIC_BASE_URL is not configured. Artifact links are relative and will not be "
            "accessible from Nonilion until a public HTTPS base URL is configured."
        )
    return build_nonilion_reply(
        response,
        job_id=job_id,
        artifacts=_public_artifact_urls(job_id),
        ai_breakdown=public["ai_breakdown"],
        trend_analysis=public.get("trend_analysis"),
        warnings=integration_warnings,
        problem_clusters=public.get("problem_clusters"),
        segment_analysis=public.get("segment_analysis"),
        decision_summary={"cards": public.get("decision_pack", {}).get("prioritised_decision_cards", [])[:5], "limitations": public.get("decision_pack", {}).get("limitations")},
    )
