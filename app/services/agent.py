"""End-to-end SIGNALDESK analysis workflow for files and normalized records."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.services.data_processor import load_feedback_file, process_feedback_dataframe
from app.services.evidence_engine import build_findings
from app.services.prioritizer import prioritize_findings
from app.services.theme_classifier import classify_records
from app.services.trend_engine import analyze_trends
from app.services.clustering_engine import analyze_segments, build_problem_clusters
from app.services.decision_engine import build_decision_pack
from app.core.config import CLUSTERING_MAX_RECORDS, SIMILARITY_THRESHOLD
from app.services.document_ingestor import load_document_dataframe


def analyze_dataframe(
    raw: pd.DataFrame,
    *,
    dataset_name: str = "customer_feedback.csv",
    feedback_column: str | None = None,
    source_id_column: str | None = None,
    source_row_offset: int = 2,
    source_type: str = "file_upload",
    batch_size: int | None = None,
) -> dict:
    """Analyse a normalized dataframe regardless of its original input method."""
    raw = raw.copy()
    if "source_type" not in raw.columns:
        raw["source_type"] = source_type
    else:
        raw["source_type"] = raw["source_type"].fillna(source_type).astype(str)
    if source_id_column is None:
        id_candidates = {"customer_id", "customerid", "user_id", "userid", "account_id", "author_id"}
        source_id_column = next(
            (str(column) for column in raw.columns if str(column).strip().casefold().replace(" ", "_") in id_candidates),
            None,
        )
    processed = process_feedback_dataframe(
        raw,
        feedback_column=feedback_column,
        source_id_column=source_id_column,
        source_row_offset=source_row_offset,
    )
    classified, warnings = classify_records(processed, batch_size=batch_size)
    findings = prioritize_findings(build_findings(classified))
    total = len(classified)
    duplicate_count = int(classified["is_duplicate"].sum())
    emotion_counts = {str(k): int(v) for k, v in classified.get("emotion", pd.Series(dtype=str)).value_counts().items()}
    urgency_counts = {str(k): int(v) for k, v in classified.get("urgency", pd.Series(dtype=str)).value_counts().items()}
    trend_analysis = analyze_trends(classified)
    problem_clusters = build_problem_clusters(
        classified, threshold=SIMILARITY_THRESHOLD, max_records=CLUSTERING_MAX_RECORDS
    )
    segment_analysis = analyze_segments(classified)
    decision_pack = build_decision_pack(findings, classified, {"total_valid_records": total})

    return {
        "dataset": {
            "filename": dataset_name,
            "raw_rows": int(len(raw)),
            "total_valid_records": total,
            "empty_rows_removed": int(len(raw) - total),
            "exact_duplicate_mentions": duplicate_count,
            "unique_normalized_feedback": int(classified["normalized_feedback"].nunique()),
        },
        "summary": {
            "themes_identified": len(findings),
            "top_findings": [
                {
                    "rank": item["priority_rank"],
                    "theme": item["theme"],
                    "mentions": item["mention_count"],
                    "prevalence_pct": item["prevalence_pct"],
                    "suggested_next_step": item["suggested_next_step"],
                }
                for item in findings[:5]
            ],
            "priority_method": "Frequency ranking for findings; the decision pack separately provides a transparent heuristic triage score, not a severity or business-value score.",
            "emotion_breakdown": emotion_counts,
            "urgency_breakdown": urgency_counts,
            "high_urgency_records": int((classified.get("urgency", pd.Series(index=classified.index, dtype=str)) == "high").sum()),
        },
        "findings": findings,
        "trend_analysis": trend_analysis,
        "problem_clusters": problem_clusters,
        "segment_analysis": segment_analysis,
        "decision_pack": decision_pack,
        "warnings": warnings,
        "classified_records": classified,
    }


def analyze_file(
    file_path: str | Path,
    *,
    feedback_column: str | None = None,
    source_id_column: str | None = None,
    batch_size: int | None = None,
) -> dict:
    from app.core.config import PDF_OCR_ENABLED
    raw, ingestion = load_document_dataframe(file_path, ocr_scanned_pdf=PDF_OCR_ENABLED)
    result = analyze_dataframe(
        raw,
        dataset_name=Path(file_path).name,
        feedback_column=feedback_column,
        source_id_column=source_id_column,
        source_row_offset=2,
        batch_size=batch_size,
    )
    result["ingestion"] = ingestion
    if ingestion.get("warnings"):
        result["warnings"].extend(ingestion["warnings"])
    return result
