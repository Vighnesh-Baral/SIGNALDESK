import pandas as pd

from app.services.trend_engine import analyze_trends


def test_detects_emerging_theme_in_adjacent_source_date_windows():
    frame = pd.DataFrame([
        {"Date": "2026-01-30", "theme": "Performance & Speed"},
        {"Date": "2026-01-31", "theme": "Performance & Speed"},
        {"Date": "2026-02-01", "theme": "Performance & Speed"},
        {"Date": "2026-02-02", "theme": "Performance & Speed"},
        {"Date": "2026-02-03", "theme": "Crashes & Stability"},
        {"Date": "2026-02-04", "theme": "Performance & Speed"},
        {"Date": "2026-03-01", "theme": "Authentication & Account Access"},
        {"Date": "2026-03-02", "theme": "Authentication & Account Access"},
        {"Date": "2026-03-03", "theme": "Authentication & Account Access"},
        {"Date": "2026-03-04", "theme": "Performance & Speed"},
    ])
    result = analyze_trends(frame)
    assert result["available"] is True
    assert result["date_column"] == "Date"
    emerging = next(item for item in result["trends"] if item["theme"] == "Authentication & Account Access")
    assert emerging["signal"] == "Newly observed"
    assert emerging["previous_mentions"] == 0
    assert emerging["recent_mentions"] == 3


def test_trend_analysis_is_transparent_when_date_column_missing():
    frame = pd.DataFrame({"theme": ["Performance & Speed"] * 10})
    result = analyze_trends(frame)
    assert result["available"] is False
    assert "No recognised date column" in result["reason"]


def test_trend_analysis_requires_enough_records_in_both_windows():
    frame = pd.DataFrame({
        "created_at": ["2026-01-02", "2026-03-02", "2026-03-03", "2026-03-04"],
        "theme": ["Performance & Speed"] * 4,
    })
    result = analyze_trends(frame)
    assert result["available"] is False
    assert "Not enough dated records" in result["reason"]



def test_recognises_spaced_date_column_names():
    frame = pd.DataFrame({
        "Created At": ["2026-01-30", "2026-01-31", "2026-02-01", "2026-03-01", "2026-03-02", "2026-03-03"],
        "theme": ["Performance & Speed"] * 6,
    })
    result = analyze_trends(frame)
    assert result["date_column"] == "Created At"
    assert result["available"] is True
