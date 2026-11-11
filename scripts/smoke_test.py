"""Run an offline end-to-end smoke test for SIGNALDESK."""
from __future__ import annotations

import json
import tempfile
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services import theme_classifier
from app.services.agent import analyze_file
from app.services.llm_service import OllamaError
from app.services.report_generator import generate_reports
from app.main import _classification_breakdown


def _offline_model(_prompt: str) -> dict:
    raise OllamaError("Offline smoke test: using deterministic keyword fallback.")


def main() -> None:
    project_root = PROJECT_ROOT
    sample = project_root / "data" / "sample" / "customer_feedback_demo.csv"
    truth_path = project_root / "data" / "sample" / "ground_truth.json"
    truth = json.loads(truth_path.read_text(encoding="utf-8"))

    original = theme_classifier.generate_json
    theme_classifier.generate_json = _offline_model
    try:
        result = analyze_file(sample, feedback_column="Feedback", source_id_column="Customer_ID")
        result["ai_breakdown"] = _classification_breakdown(result)
    finally:
        theme_classifier.generate_json = original

    if result["dataset"]["total_valid_records"] != truth["expected_non_empty_records"]:
        raise SystemExit("Smoke test failed: valid-record count does not match ground truth.")

    correct = 0
    for row in result["classified_records"].itertuples(index=False):
        expected = truth["records"][str(row.source_id)]["expected_theme"]
        correct += int(row.theme == expected)
    accuracy = correct / len(result["classified_records"])

    with tempfile.TemporaryDirectory(prefix="signaldesk-smoke-") as temp_dir:
        artifacts = generate_reports(result, temp_dir)
        missing = [name for name, path in artifacts.items() if not Path(path).is_file()]
        if missing:
            raise SystemExit(f"Smoke test failed: missing report artifacts: {missing}")

    print("SIGNALDESK offline end-to-end smoke test: PASS")
    print(f"Valid records: {result['dataset']['total_valid_records']}")
    print(f"Blank rows removed: {result['dataset']['empty_rows_removed']}")
    print(f"Exact duplicates retained: {result['dataset']['exact_duplicate_mentions']}")
    print(f"Themes found: {result['summary']['themes_identified']}")
    trend = result.get("trend_analysis", {})
    if not trend.get("available"):
        raise SystemExit(f"Smoke test failed: the supplied synthetic date column should produce a trend comparison: {trend.get('reason')}")
    print(f"Date trend analysis available: {bool(trend.get('available'))}")
    if trend.get("available"):
        emerging = [item["theme"] for item in trend.get("trends", []) if item.get("signal") in {"Emerging", "Newly observed"}]
        print(f"Emerging/newly observed themes: {', '.join(emerging) if emerging else 'None met the configured threshold'}")
    else:
        print(f"Trend limitation: {trend.get('reason', 'Not generated')}")
    print(f"Local Qwen3-classified records: {result['ai_breakdown']['qwen3_records']}")
    print(f"Keyword-fallback records: {result['ai_breakdown']['fallback_records']}")
    print(f"Fallback agreement with synthetic labels: {accuracy:.1%} ({correct}/{len(result['classified_records'])})")
    print("Reports: Excel, PDF and chart generated successfully.")
    print("Note: the fallback agreement is a synthetic QA check, not real-world model accuracy.")


if __name__ == "__main__":
    main()
