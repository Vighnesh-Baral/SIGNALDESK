"""Build aggregate findings with source-level evidence references."""
from __future__ import annotations

import pandas as pd


def build_findings(classified: pd.DataFrame) -> list[dict]:
    if classified.empty:
        return []
    total_records = int(len(classified))
    findings: list[dict] = []
    grouped = classified.groupby("theme", dropna=False)
    for index, (theme, group) in enumerate(
        sorted(grouped, key=lambda item: (-len(item[1]), str(item[0]).casefold())), start=1
    ):
        evidence = []
        for row in group.head(5).itertuples(index=False):
            evidence.append({
                "record_id": str(row.record_id),
                "source_id": None if pd.isna(row.source_id) else str(row.source_id),
                "source_row": int(row.source_row),
                "quote": str(row.original_feedback),
                "is_duplicate": bool(row.is_duplicate),
                "source_type": str(getattr(row, "source_type", "file_upload")),
                "source_reference": str(getattr(row, "source_reference", "") or ""),
                "source_page": int(getattr(row, "source_page")) if getattr(row, "source_page", None) is not None and not pd.isna(getattr(row, "source_page")) else None,
                "sentiment": str(getattr(row, "sentiment", "unknown")),
                "emotion": str(getattr(row, "emotion", "unknown")),
                "urgency": str(getattr(row, "urgency", "unknown")),
            })
        count = int(len(group))
        findings.append({
            "finding_id": f"F-{index:03d}",
            "theme": str(theme),
            "mention_count": count,
            "unique_normalized_feedback_count": int(group["normalized_feedback"].nunique()),
            "duplicate_mention_count": int(group["is_duplicate"].sum()),
            "prevalence_pct": round((count / total_records) * 100, 1),
            "record_ids": [str(value) for value in group["record_id"].tolist()],
            "sentiment_breakdown": {
                str(key): int(value)
                for key, value in group["sentiment"].value_counts(dropna=False).items()
            },
            "emotion_breakdown": {
                str(key): int(value)
                for key, value in group.get("emotion", pd.Series(["unknown"] * len(group), index=group.index)).value_counts(dropna=False).items()
            },
            "urgency_breakdown": {
                str(key): int(value)
                for key, value in group.get("urgency", pd.Series(["unknown"] * len(group), index=group.index)).value_counts(dropna=False).items()
            },
            "evidence": evidence,
            "evidence_note": "Counts are calculated from retained non-empty source records. Quotes are copied from original rows.",
        })
    return findings
