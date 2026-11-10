"""Date-aware comparison of recent and preceding customer-feedback periods."""
from __future__ import annotations

import re

import pandas as pd

DATE_COLUMN_CANDIDATES = (
    "date", "created_at", "created", "submitted_at", "submission_date",
    "feedback_date", "review_date", "timestamp", "time", "date_submitted",
    "created_on", "record_date", "reviewed_at",
)


def analyze_trends(classified: pd.DataFrame, *, window_days: int = 30) -> dict:
    """Compare two adjacent windows anchored to the latest date in the dataset.

    This avoids pretending that a historical export ends today. A trend is only
    reported when both windows contain a minimum number of dated records.
    """
    if classified.empty:
        return {"available": False, "reason": "No feedback records are available."}

    columns = {
        re.sub(r"[^a-z0-9]+", "_", str(column).strip().casefold()).strip("_"): column
        for column in classified.columns
    }
    selected = next((columns[name] for name in DATE_COLUMN_CANDIDATES if name in columns), None)
    if selected is None:
        return {
            "available": False,
            "reason": "No recognised date column was found. Add a Date, Created_At or Submitted_At column to enable trend analysis.",
        }
    raw_dates = classified[selected]
    if pd.api.types.is_numeric_dtype(raw_dates):
        return {"available": False, "date_column": str(selected), "reason": "The detected date column is numeric and could not be interpreted safely."}
    parsed = pd.to_datetime(raw_dates, errors="coerce", utc=True, format="mixed")
    valid = classified.loc[parsed.notna()].copy()
    valid["_signaldesk_date"] = parsed.loc[parsed.notna()]
    if valid.empty:
        return {"available": False, "date_column": str(selected), "reason": "The date column contains no parseable dates."}

    latest = valid["_signaldesk_date"].max()
    recent_start = latest - pd.Timedelta(days=window_days)
    previous_start = latest - pd.Timedelta(days=window_days * 2)
    recent = valid[(valid["_signaldesk_date"] > recent_start) & (valid["_signaldesk_date"] <= latest)]
    previous = valid[(valid["_signaldesk_date"] > previous_start) & (valid["_signaldesk_date"] <= recent_start)]
    minimum = 3
    if len(recent) < minimum or len(previous) < minimum:
        return {
            "available": False,
            "date_column": str(selected),
            "latest_date": latest.date().isoformat(),
            "reason": (
                f"Not enough dated records in both adjacent {window_days}-day windows "
                f"(need at least {minimum} in each; found {len(previous)} earlier and {len(recent)} recent)."
            ),
        }

    previous_counts = previous["theme"].value_counts().to_dict()
    recent_counts = recent["theme"].value_counts().to_dict()
    rows = []
    for theme in sorted(set(previous_counts) | set(recent_counts)):
        earlier = int(previous_counts.get(theme, 0))
        current = int(recent_counts.get(theme, 0))
        delta = current - earlier
        pct_change = None if earlier == 0 else round((delta / earlier) * 100, 1)
        if earlier == 0 and current >= 3:
            signal = "Newly observed"
        elif current >= 3 and delta > 0 and (pct_change is None or pct_change >= 50):
            signal = "Emerging"
        elif delta < 0:
            signal = "Declining"
        else:
            signal = "No strong change"
        rows.append({
            "theme": str(theme),
            "previous_mentions": earlier,
            "recent_mentions": current,
            "change": delta,
            "change_pct": pct_change,
            "signal": signal,
        })
    rows.sort(key=lambda item: (0 if item["signal"] in {"Newly observed", "Emerging"} else 1, -item["change"], item["theme"].casefold()))
    return {
        "available": True,
        "date_column": str(selected),
        "window_days": window_days,
        "previous_period": {"start": previous_start.date().isoformat(), "end": recent_start.date().isoformat(), "records": int(len(previous))},
        "recent_period": {"start": recent_start.date().isoformat(), "end": latest.date().isoformat(), "records": int(len(recent))},
        "latest_date": latest.date().isoformat(),
        "minimum_records_per_period": minimum,
        "trends": rows,
        "method_note": "Adjacent fixed-length windows anchored to the latest parseable date in the uploaded data; not to the current date. Emerging labels require at least three recent mentions and either no earlier mentions or at least 50% growth.",
    }
