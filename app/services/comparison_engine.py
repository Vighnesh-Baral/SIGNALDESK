"""Compare two saved analyses without implying causation from observational data."""
from __future__ import annotations

from typing import Any

import pandas as pd


def compare_analyses(baseline: dict, current: dict) -> dict[str, Any]:
    base_records = baseline.get("classified_records")
    curr_records = current.get("classified_records")
    if not isinstance(base_records, pd.DataFrame) or not isinstance(curr_records, pd.DataFrame):
        raise ValueError("Both analyses must include classified source records.")
    if base_records.empty or curr_records.empty:
        raise ValueError("Both comparison datasets must contain at least one valid record.")

    base_total, curr_total = len(base_records), len(curr_records)
    base_counts = base_records["theme"].value_counts().to_dict()
    curr_counts = curr_records["theme"].value_counts().to_dict()
    rows = []
    for theme in sorted(set(base_counts) | set(curr_counts)):
        before = int(base_counts.get(theme, 0))
        after = int(curr_counts.get(theme, 0))
        before_rate = before / base_total * 100
        after_rate = after / curr_total * 100
        delta = after_rate - before_rate
        if before == 0 and after > 0:
            status = "Newly observed"
        elif before > 0 and after == 0:
            status = "Not observed in current dataset"
        elif delta >= 2:
            status = "Higher share"
        elif delta <= -2:
            status = "Lower share"
        else:
            status = "Broadly stable"
        rows.append({
            "theme": str(theme),
            "baseline_mentions": before,
            "current_mentions": after,
            "baseline_prevalence_pct": round(before_rate, 1),
            "current_prevalence_pct": round(after_rate, 1),
            "prevalence_change_percentage_points": round(delta, 1),
            "status": status,
        })
    rows.sort(key=lambda item: (-abs(item["prevalence_change_percentage_points"]), item["theme"].casefold()))

    # Compare segment themes when a segment dimension appears in both datasets.
    segment_comparisons = []
    candidate_columns = {"customer_segment", "segment", "plan", "subscription_plan", "region", "country", "device", "platform", "customer_type", "customer_tier"}
    for column in sorted(set(base_records.columns) & set(curr_records.columns)):
        if str(column).strip().casefold().replace(" ", "_") not in candidate_columns:
            continue
        bvals = {value for value in base_records[column].dropna().astype(str).str.strip() if value}
        cvals = {value for value in curr_records[column].dropna().astype(str).str.strip() if value}
        for label in sorted(bvals & cvals):
            b = base_records[base_records[column].fillna("").astype(str).str.strip() == label]
            c = curr_records[curr_records[column].fillna("").astype(str).str.strip() == label]
            btop = b["theme"].value_counts().head(3)
            ctop = c["theme"].value_counts().head(3)
            segment_comparisons.append({
                "dimension": str(column), "segment": label,
                "baseline_records": int(len(b)), "current_records": int(len(c)),
                "baseline_top_themes": [{"theme": str(k), "mentions": int(v)} for k, v in btop.items()],
                "current_top_themes": [{"theme": str(k), "mentions": int(v)} for k, v in ctop.items()],
            })

    return {
        "comparison_type": "observational_dataset_comparison",
        "baseline": {"name": baseline.get("dataset", {}).get("filename", "Baseline"), "records": base_total},
        "current": {"name": current.get("dataset", {}).get("filename", "Current"), "records": curr_total},
        "theme_comparisons": rows,
        "segment_comparisons": segment_comparisons,
        "interpretation": "Differences are changes in observed feedback counts and prevalence, not proof that a product release caused the change. Compare collection windows, customer mix and exposure before attributing effects to a release.",
    }
