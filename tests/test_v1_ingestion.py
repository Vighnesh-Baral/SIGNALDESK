import json
from pathlib import Path

import fitz
import pandas as pd
from docx import Document

from app.services.document_ingestor import load_document_dataframe


def test_txt_ingestion_splits_paragraphs_and_preserves_source_reference(tmp_path):
    path = tmp_path / "feedback.txt"
    path.write_text("The dashboard is slow.\n\nExport crashes every time.", encoding="utf-8")
    frame, meta = load_document_dataframe(path)
    assert len(frame) == 2
    assert frame.iloc[0]["source_reference"] == "txt:paragraph:1"
    assert meta["format"] == "txt"


def test_html_ingestion_prefers_review_blocks(tmp_path):
    path = tmp_path / "reviews.html"
    path.write_text("""<html><nav>Ignore menu</nav><main>
    <div class='review'>The dashboard is slow</div>
    <div class='review'>Export crashes</div>
    </main></html>""", encoding="utf-8")
    frame, _ = load_document_dataframe(path)
    assert len(frame) == 2
    assert set(frame["source_type"]) == {"html"}


def test_pdf_ingestion_preserves_page_reference(tmp_path):
    path = tmp_path / "feedback.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "The dashboard is slow to load.\n\nExporting reports crashes.")
    doc.save(path)
    doc.close()
    frame, _ = load_document_dataframe(path, ocr_scanned_pdf=False)
    assert len(frame) >= 1
    assert all(str(ref).startswith("page:1/") for ref in frame["source_reference"])
    assert set(frame["source_page"].astype(int)) == {1}


def test_docx_ingestion_reads_paragraphs_and_tables(tmp_path):
    path = tmp_path / "feedback.docx"
    doc = Document()
    doc.add_paragraph("The app crashes during export.")
    table = doc.add_table(rows=1, cols=1)
    table.cell(0, 0).text = "The dashboard is slow."
    doc.save(path)
    frame, _ = load_document_dataframe(path)
    assert len(frame) == 2
    assert any(value.startswith("docx:table") for value in frame["source_reference"])


def test_json_ingestion_preserves_customer_date_and_segments(tmp_path):
    path = tmp_path / "feedback.json"
    path.write_text(json.dumps({"reviews": [
        {"id": "C1", "customer_id": "C1", "feedback": "Dashboard is slow", "date": "2026-01-01", "plan": "Pro"},
        {"id": "C2", "customer_id": "C2", "feedback": "Export crashes", "date": "2026-01-02", "plan": "Free"},
    ]}), encoding="utf-8")
    frame, _ = load_document_dataframe(path)
    assert len(frame) == 2
    assert frame.iloc[0]["Customer_ID"] == "C1"
    assert frame.iloc[0]["Date"] == "2026-01-01"
    assert frame.iloc[0]["plan"] == "Pro"


def test_unsupported_extension_is_rejected(tmp_path):
    path = tmp_path / "feedback.exe"
    path.write_text("not a document")
    try:
        load_document_dataframe(path)
    except ValueError as exc:
        assert "Unsupported file format" in str(exc)
    else:
        raise AssertionError("Expected unsupported format error")
