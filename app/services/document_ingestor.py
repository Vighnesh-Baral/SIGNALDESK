"""Multi-format customer-feedback ingestion with source traceability.

PDF OCR is optional and requires the external Tesseract executable. HTML extraction
removes page chrome and prefers repeated review/comment containers. JSON extraction
is intentionally schema-tolerant but never silently invents customer metadata.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pandas as pd

SUPPORTED_EXTENSIONS = {".csv", ".xlsx", ".pdf", ".html", ".htm", ".txt", ".docx", ".json"}
TEXT_KEYS = {"feedback", "comment", "review", "message", "text", "content", "description", "body", "issue", "complaint"}
ID_KEYS = {"customer_id", "customerid", "user_id", "userid", "author_id", "account_id"}
DATE_KEYS = {"date", "created_at", "created", "submitted_at", "timestamp", "review_date"}


def _records_from_blocks(blocks: list[tuple[str, str]], *, source_type: str, extra: list[dict] | None = None) -> pd.DataFrame:
    rows = []
    for index, (text, reference) in enumerate(blocks, start=1):
        cleaned = re.sub(r"\s+", " ", str(text)).strip()
        if len(cleaned) < 3:
            continue
        row = {
            "Feedback": cleaned,
            "source_type": source_type,
            "source_reference": reference,
            "source_sequence": index,
        }
        if extra and index - 1 < len(extra):
            row.update(extra[index - 1])
        rows.append(row)
    if not rows:
        raise ValueError("No usable customer feedback text could be extracted from this document.")
    return pd.DataFrame(rows)


def _split_paragraphs(text: str) -> list[str]:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    chunks = re.split(r"\n\s*\n+|^\s*(?:[-*•]|\d+[.)])\s+", text, flags=re.MULTILINE)
    cleaned = [re.sub(r"\s+", " ", chunk).strip(" \t-•") for chunk in chunks]
    return [item for item in cleaned if len(item) >= 3]


def _extract_pdf(path: Path, ocr_scanned: bool = True) -> tuple[pd.DataFrame, list[str]]:
    try:
        import fitz
    except ImportError as exc:
        raise ValueError("PDF support requires PyMuPDF. Install dependencies from requirements.txt.") from exc
    try:
        doc = fitz.open(path)
    except Exception as exc:
        raise ValueError(f"Could not open PDF: {exc}") from exc
    blocks: list[tuple[str, str]] = []
    warnings: list[str] = []
    for page_index, page in enumerate(doc, start=1):
        text = page.get_text("text") or ""
        if len(text.strip()) < 20 and ocr_scanned:
            try:
                import pytesseract
                from PIL import Image
                import io
                pix = page.get_pixmap(matrix=fitz.Matrix(1.7, 1.7), alpha=False)
                image = Image.open(io.BytesIO(pix.tobytes("png")))
                text = pytesseract.image_to_string(image)
            except Exception as exc:
                warnings.append(
                    f"Page {page_index} appears scanned, but OCR could not run ({type(exc).__name__}). "
                    "Install Tesseract OCR and ensure it is on PATH to extract scanned pages."
                )
        paragraphs = _split_paragraphs(text)
        if not paragraphs and text.strip():
            paragraphs = [re.sub(r"\s+", " ", text).strip()]
        for paragraph_index, paragraph in enumerate(paragraphs, start=1):
            blocks.append((paragraph, f"page:{page_index}/paragraph:{paragraph_index}"))
    doc.close()
    if not blocks and warnings:
        raise ValueError("This PDF appears to contain scanned pages, but OCR was unavailable. " + " ".join(warnings[:2]))
    frame = _records_from_blocks(blocks, source_type="pdf", extra=None)
    frame["source_page"] = frame["source_reference"].str.extract(r"page:(\d+)")[0].astype("Int64")
    return frame, warnings


def _extract_html(path: Path) -> pd.DataFrame:
    try:
        from bs4 import BeautifulSoup
    except ImportError as exc:
        raise ValueError("HTML support requires beautifulsoup4. Install dependencies from requirements.txt.") from exc
    soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="replace"), "html.parser")
    for node in soup.select("script,style,noscript,svg,nav,header,footer,aside,form,button,template"):
        node.decompose()
    selectors = [
        "[data-review]", "[data-feedback]", "[class*=review]", "[class*=feedback]",
        "[class*=comment]", "[class*=ticket]", "[class*=message]", "blockquote",
    ]
    candidates = []
    for selector in selectors:
        found = soup.select(selector)
        if len(found) >= 2:
            candidates = found
            break
    if not candidates:
        main = soup.find("main") or soup.find("article") or soup.body or soup
        candidates = main.find_all(["p", "blockquote", "li"])
    blocks, extras = [], []
    seen = set()
    for index, node in enumerate(candidates, start=1):
        # Avoid nested duplicates when a selected parent already contains selected children.
        if any(parent in candidates for parent in node.parents if getattr(parent, "name", None)):
            continue
        text = node.get_text(" ", strip=True)
        normal = re.sub(r"\s+", " ", text).strip()
        if len(normal) < 3 or normal.casefold() in seen:
            continue
        seen.add(normal.casefold())
        blocks.append((normal, f"html:element:{index}"))
        meta = {}
        for key in ("data-customer-id", "data-user-id", "data-author-id"):
            if node.get(key):
                meta["Customer_ID"] = node.get(key)
                break
        for key in ("data-date", "datetime", "data-created-at"):
            if node.get(key):
                meta["Date"] = node.get(key)
                break
        extras.append(meta)
    if not blocks:
        raise ValueError("No review, comment or meaningful text blocks were detected in the HTML file.")
    return _records_from_blocks(blocks, source_type="html", extra=extras)


def _extract_docx(path: Path) -> pd.DataFrame:
    try:
        from docx import Document
    except ImportError as exc:
        raise ValueError("DOCX support requires python-docx. Install dependencies from requirements.txt.") from exc
    document = Document(path)
    blocks: list[tuple[str, str]] = []
    for index, paragraph in enumerate(document.paragraphs, start=1):
        if paragraph.text.strip():
            blocks.append((paragraph.text, f"docx:paragraph:{index}"))
    for table_index, table in enumerate(document.tables, start=1):
        for row_index, row in enumerate(table.rows, start=1):
            values = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if values:
                blocks.append((" | ".join(values), f"docx:table:{table_index}/row:{row_index}"))
    return _records_from_blocks(blocks, source_type="docx")


def _flatten_json(value: Any, path: str = "json", inherited: dict | None = None) -> list[dict]:
    inherited = dict(inherited or {})
    rows: list[dict] = []
    if isinstance(value, list):
        for index, item in enumerate(value, start=1):
            rows.extend(_flatten_json(item, f"{path}[{index}]", inherited))
        return rows
    if isinstance(value, dict):
        normalized = {re.sub(r"[^a-z0-9]+", "_", str(key).casefold()).strip("_"): val for key, val in value.items()}
        text_key = next((key for key in normalized if key in TEXT_KEYS and isinstance(normalized[key], (str, int, float))), None)
        if text_key:
            row = {"Feedback": str(normalized[text_key]), "source_type": "json", "source_reference": path}
            id_key = next((key for key in normalized if key in ID_KEYS), None)
            date_key = next((key for key in normalized if key in DATE_KEYS), None)
            if id_key and normalized[id_key] is not None:
                row["Customer_ID"] = str(normalized[id_key])
            if date_key and normalized[date_key] is not None:
                row["Date"] = normalized[date_key]
            for key in ("plan", "region", "country", "device", "platform", "customer_segment", "customer_type"):
                if key in normalized and normalized[key] is not None:
                    row[key] = normalized[key]
            rows.append(row)
        else:
            for key, item in value.items():
                if isinstance(item, (dict, list)):
                    rows.extend(_flatten_json(item, f"{path}.{key}", inherited))
        return rows
    if isinstance(value, str) and value.strip():
        rows.append({"Feedback": value.strip(), "source_type": "json", "source_reference": path})
    return rows


def load_document_dataframe(file_path: str | Path, *, ocr_scanned_pdf: bool = True) -> tuple[pd.DataFrame, dict]:
    """Load supported file types into a common feedback dataframe and extraction metadata."""
    path = Path(file_path)
    suffix = path.suffix.casefold()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported file format. Supported formats: {', '.join(sorted(SUPPORTED_EXTENSIONS))}.")
    warnings: list[str] = []
    if suffix in {".csv", ".xlsx"}:
        from app.services.data_processor import load_feedback_file
        frame = load_feedback_file(path)
        metadata = {"format": suffix[1:], "extraction_method": "tabular_parser", "warnings": warnings}
        return frame, metadata
    if suffix == ".pdf":
        frame, warnings = _extract_pdf(path, ocr_scanned=ocr_scanned_pdf)
    elif suffix in {".html", ".htm"}:
        frame = _extract_html(path)
    elif suffix == ".txt":
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        blocks = [(item, f"txt:paragraph:{index}") for index, item in enumerate(_split_paragraphs(text), start=1)]
        frame = _records_from_blocks(blocks, source_type="txt")
    elif suffix == ".docx":
        frame = _extract_docx(path)
    elif suffix == ".json":
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON document: {exc}") from exc
        records = _flatten_json(payload)
        if not records:
            raise ValueError("No feedback-like fields were found in the JSON document.")
        frame = pd.DataFrame(records)
    metadata = {
        "format": suffix.lstrip("."),
        "extraction_method": "ocr_and_text_parser" if suffix == ".pdf" else "document_parser",
        "extracted_records": int(len(frame)),
        "warnings": warnings,
    }
    return frame, metadata
