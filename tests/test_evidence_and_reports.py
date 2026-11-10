import pandas as pd

from app.services.evidence_engine import build_findings
from app.services.prioritizer import prioritize_findings
from app.services.report_generator import generate_reports


def make_classified():
    return pd.DataFrame([
        {"record_id": "FB-000001", "source_id": "C1", "source_row": 2,
         "original_feedback": "The app crashes during export.", "normalized_feedback": "the app crashes during export",
         "is_duplicate": False, "theme": "Crashes & Stability", "sentiment": "negative",
         "classification_method": "keyword_fallback", "duplicate_of_record_id": None,
         "source_type": "manual_text"},
        {"record_id": "FB-000002", "source_id": "C2", "source_row": 3,
         "original_feedback": "The app crashes during export!", "normalized_feedback": "the app crashes during export",
         "is_duplicate": True, "theme": "Crashes & Stability", "sentiment": "negative",
         "classification_method": "keyword_fallback", "duplicate_of_record_id": "FB-000001",
         "source_type": "manual_text"},
        {"record_id": "FB-000003", "source_id": "C3", "source_row": 4,
         "original_feedback": "Dashboard is slow.", "normalized_feedback": "dashboard is slow",
         "is_duplicate": False, "theme": "Performance & Speed", "sentiment": "negative",
         "classification_method": "keyword_fallback", "duplicate_of_record_id": None,
         "source_type": "manual_text"},
    ])


def test_findings_count_source_records_and_keep_traceability():
    classified = make_classified()
    findings = prioritize_findings(build_findings(classified))
    assert findings[0]["theme"] == "Crashes & Stability"
    assert findings[0]["mention_count"] == 2
    assert findings[0]["duplicate_mention_count"] == 1
    assert {item["record_id"] for item in findings[0]["evidence"]} == {"FB-000001", "FB-000002"}
    assert findings[0]["priority_basis"].startswith("Relative frequency")
    assert findings[0]["suggested_next_step"]
    assert findings[0]["suggestion_note"].startswith("Analyst suggestion")


def test_report_generation_creates_excel_pdf_and_chart(tmp_path):
    classified = make_classified()
    findings = prioritize_findings(build_findings(classified))
    result = {
        "dataset": {"filename": "fixture.csv", "raw_rows": 3, "total_valid_records": 3,
                    "empty_rows_removed": 0, "exact_duplicate_mentions": 1,
                    "unique_normalized_feedback": 2},
        "summary": {"themes_identified": len(findings), "priority_method": "Frequency ranking."},
        "findings": findings,
        "warnings": [],
        "classified_records": classified,
        "ai_breakdown": {
            "qwen3_records": 1, "fallback_records": 2, "unreported_records": 0,
            "total_records": 3, "total_classified": 3,
            "qwen3_percentage": 33.3, "fallback_percentage": 66.7,
        },
    }
    paths = generate_reports(result, tmp_path)
    assert all(tmp_path.joinpath(path.split("/")[-1]).exists() for path in paths.values())
    assert tmp_path.joinpath("signaldesk_research_report.xlsx").stat().st_size > 1000
    assert tmp_path.joinpath("signaldesk_research_brief.pdf").stat().st_size > 1000
    from openpyxl import load_workbook
    workbook = load_workbook(tmp_path / "signaldesk_research_report.xlsx", read_only=True)
    overview = list(workbook["Overview"].values)
    assert ("Classified by Qwen3", 1) in overview
    assert ("Classified by keyword fallback", 2) in overview
    processed_headers = list(workbook["Processed Feedback"].values)[0]
    assert "source_type" in processed_headers
    evidence_headers = list(workbook["Evidence Register"].values)[0]
    assert "Source type" in evidence_headers
    workbook.close()


def test_investigation_cards_separate_evidence_from_unknowns():
    findings = prioritize_findings(build_findings(make_classified()))
    card = findings[0]["investigation"]
    assert card["status"] == "Needs investigation"
    assert card["evidence_breadth"] == "Limited"
    assert "root cause" in card["what_is_not_established"][0].lower()
    assert card["investigation_checks"]


def test_report_includes_investigation_and_trend_sheets(tmp_path):
    classified = make_classified()
    findings = prioritize_findings(build_findings(classified))
    result = {
        "dataset": {"filename": "fixture.csv", "raw_rows": 3, "total_valid_records": 3,
                    "empty_rows_removed": 0, "exact_duplicate_mentions": 1,
                    "unique_normalized_feedback": 2},
        "summary": {"themes_identified": len(findings), "priority_method": "Frequency ranking."},
        "findings": findings,
        "warnings": [],
        "classified_records": classified,
        "ai_breakdown": {"qwen3_records": 1, "fallback_records": 2, "unreported_records": 0,
                         "qwen3_percentage": 33.3, "fallback_percentage": 66.7},
        "trend_analysis": {"available": False, "reason": "No date column was found."},
    }
    generate_reports(result, tmp_path)
    from openpyxl import load_workbook
    workbook = load_workbook(tmp_path / "signaldesk_research_report.xlsx", read_only=True)
    assert "Investigation Cards" in workbook.sheetnames
    assert "Trend Analysis" in workbook.sheetnames
    headers = list(workbook["Investigation Cards"].values)[0]
    assert "What is not established" in headers
    workbook.close()
