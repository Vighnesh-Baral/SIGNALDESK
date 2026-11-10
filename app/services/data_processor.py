"""Read and prepare customer feedback while retaining source traceability."""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import IO

import pandas as pd

FEEDBACK_COLUMN_CANDIDATES = [
    "feedback", "customer_feedback", "comment", "review", "message",
    "text", "description", "issue", "content", "response",
]


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", str(text)).casefold().strip()
    text = re.sub(r"[^\w\s]", "", text)
    return re.sub(r"\s+", " ", text)


def load_feedback_file(file_path: str | Path) -> pd.DataFrame:
    path = Path(file_path)
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"File not found: {path}")
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path, dtype=object, keep_default_na=True)
    if suffix == ".xlsx":
        return pd.read_excel(path, engine="openpyxl", dtype=object)
    raise ValueError("Unsupported file format. Please upload a .csv or .xlsx file.")


def load_feedback_stream(file_obj: IO[bytes], filename: str) -> pd.DataFrame:
    suffix = Path(filename).suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(file_obj, dtype=object, keep_default_na=True)
    if suffix == ".xlsx":
        return pd.read_excel(file_obj, engine="openpyxl", dtype=object)
    raise ValueError("Unsupported file format. Please upload a .csv or .xlsx file.")


def _resolve_column(columns: list[str], requested: str | None) -> str | None:
    lookup = {str(column).strip().casefold(): column for column in columns}
    if requested:
        return lookup.get(requested.strip().casefold())
    for candidate in FEEDBACK_COLUMN_CANDIDATES:
        if candidate in lookup:
            return lookup[candidate]
    return None


def process_feedback_dataframe(
    df: pd.DataFrame,
    feedback_column: str | None = None,
    source_id_column: str | None = None,
    *,
    source_row_offset: int = 2,
) -> pd.DataFrame:
    """Clean empty rows and flag exact duplicates; never delete duplicate mentions."""
    if df is None or df.empty:
        raise ValueError("The uploaded dataset is empty.")

    working = df.copy()
    working.columns = [str(column).strip() for column in working.columns]
    selected_column = _resolve_column(list(working.columns), feedback_column)
    if selected_column is None:
        raise ValueError(
            "Feedback column not found. Available columns: "
            f"{list(working.columns)}. Pass feedback_column explicitly."
        )

    selected_source_column = None
    if source_id_column:
        selected_source_column = _resolve_column(list(working.columns), source_id_column)
        if selected_source_column is None:
            raise ValueError(f"Source ID column '{source_id_column}' does not exist.")

    feedback_values = working[selected_column].fillna("").astype(str).str.strip()
    valid_positions = [i for i, value in enumerate(feedback_values.tolist()) if value]
    if not valid_positions:
        raise ValueError("No non-empty customer feedback records were found.")

    cleaned = working.iloc[valid_positions].copy().reset_index(drop=True)
    cleaned_feedback = [feedback_values.iloc[i] for i in valid_positions]
    # Row 1 is assumed to contain the spreadsheet header; data begins on row 2.
    if source_row_offset < 1:
        raise ValueError("source_row_offset must be at least 1.")
    cleaned["source_row"] = [position + source_row_offset for position in valid_positions]
    cleaned["record_id"] = [f"FB-{i:06d}" for i in range(1, len(cleaned) + 1)]
    cleaned["source_id"] = (
        cleaned[selected_source_column].where(cleaned[selected_source_column].notna(), None)
        if selected_source_column else None
    )
    cleaned["original_feedback"] = cleaned_feedback
    cleaned["normalized_feedback"] = cleaned["original_feedback"].map(normalize_text)

    first_seen: dict[str, str] = {}
    duplicate_of: list[str | None] = []
    duplicate_flags: list[bool] = []
    for record_id, normalized in zip(cleaned["record_id"], cleaned["normalized_feedback"]):
        if normalized in first_seen:
            duplicate_flags.append(True)
            duplicate_of.append(first_seen[normalized])
        else:
            duplicate_flags.append(False)
            duplicate_of.append(None)
            first_seen[normalized] = record_id
    cleaned["is_duplicate"] = duplicate_flags
    cleaned["duplicate_of_record_id"] = duplicate_of
    return cleaned.reset_index(drop=True)


def process_feedback_file(
    file_path: str | Path,
    feedback_column: str | None = None,
    source_id_column: str | None = None,
) -> pd.DataFrame:
    raw = load_feedback_file(file_path)
    return process_feedback_dataframe(raw, feedback_column, source_id_column)
