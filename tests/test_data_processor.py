import pandas as pd
import pytest

from app.services.data_processor import normalize_text, process_feedback_dataframe


def test_removes_blank_rows_but_keeps_duplicate_mentions():
    source = pd.DataFrame({
        "Customer_ID": ["C001", "C002", "C003", "C004"],
        "Feedback": ["App crashes during export!", "", "app crashes during export", "Dashboard is slow"],
    })
    result = process_feedback_dataframe(source, "Feedback", "Customer_ID")
    assert len(result) == 3
    assert result["is_duplicate"].tolist() == [False, True, False]
    assert result["duplicate_of_record_id"].iloc[1] == "FB-000001"
    assert result["source_id"].tolist() == ["C001", "C003", "C004"]
    assert result["source_row"].tolist() == [2, 4, 5]


def test_auto_detects_feedback_column_case_insensitively():
    result = process_feedback_dataframe(pd.DataFrame({" CUSTOMER_FEEDBACK ": ["Slow search"]}))
    assert result.iloc[0]["original_feedback"] == "Slow search"


def test_rejects_missing_feedback_column():
    with pytest.raises(ValueError, match="Feedback column not found"):
        process_feedback_dataframe(pd.DataFrame({"Customer_ID": ["C1"]}))


def test_normalize_text():
    assert normalize_text("  APP crashes, DURING export!  ") == "app crashes during export"


def test_supports_one_based_source_rows_for_manual_text():
    result = process_feedback_dataframe(
        pd.DataFrame({"Feedback": ["First complaint", "Second complaint"]}),
        "Feedback",
        source_row_offset=1,
    )
    assert result["source_row"].tolist() == [1, 2]
