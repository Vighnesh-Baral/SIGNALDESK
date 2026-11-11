from pathlib import Path

import pytest

from app.storage.manager import FileStorage, StorageError, safe_job_directory


def test_safe_job_directory_rejects_path_traversal(tmp_path):
    with pytest.raises(StorageError):
        safe_job_directory(tmp_path, "../outside")


def test_file_storage_creates_separate_persistent_areas(tmp_path):
    storage = FileStorage(
        uploads=tmp_path / "uploads",
        outputs=tmp_path / "outputs",
        processed=tmp_path / "processed",
        temp=tmp_path / "temp",
    )
    job_id = "a" * 32
    upload = storage.file_path("uploads", job_id, "feedback.csv")
    output = storage.file_path("outputs", job_id, "report.pdf")
    assert upload.parent == tmp_path / "uploads" / job_id
    assert output.parent == tmp_path / "outputs" / job_id
    assert storage.check_writable() is True


def test_database_persists_analysis_metadata_and_history(tmp_path):
    from app.database.db import initialize_database, persist_analysis, list_analyses, get_analysis
    from app.database.models import Base

    job_id = "e" * 32
    output = tmp_path / "outputs" / job_id
    output.mkdir(parents=True)
    processed = tmp_path / "processed" / job_id / "classified_feedback.csv"
    processed.parent.mkdir(parents=True)
    processed.write_text("record_id,theme\nFB-1,Crashes & Stability\n", encoding="utf-8")
    (output / "result.json").write_text("{}", encoding="utf-8")
    (output / "signaldesk_research_report.xlsx").write_bytes(b"xlsx")

    # The project's SQLite dev database is initialised idempotently. A unique job id
    # keeps this integration assertion isolated from other test requests.
    initialize_database()
    result = {
        "dataset": {"filename": "test.csv", "raw_rows": 1, "total_valid_records": 1,
                    "empty_rows_removed": 0, "exact_duplicate_mentions": 0,
                    "unique_normalized_feedback": 1},
        "summary": {"themes_identified": 1},
        "ai_breakdown": {"llm_records": 1, "fallback_records": 0},
        "warnings": [],
        "findings": [{"finding_id": "F-1", "theme": "Crashes & Stability",
                      "mention_count": 1, "prevalence_pct": 100.0, "priority_rank": 1,
                      "evidence": [{"record_id": "FB-1", "quote": "The app crashes.", "source_row": 2}]}],
    }
    persist_analysis(job_id=job_id, public_result=result, output_dir=output, processed_path=processed,
                     source_type="test")
    saved = get_analysis(job_id)
    assert saved is not None
    assert saved["status"] == "completed"
    assert saved["total_valid_records"] == 1
    assert saved["dataset"]["source_type"] == "test"
    assert get_analysis(job_id)["job_id"] == job_id


def test_storage_cleanup_expires_uploads_artifacts_and_temp_files(tmp_path):
    import os
    import time

    storage = FileStorage(
        uploads=tmp_path / "uploads",
        outputs=tmp_path / "outputs",
        processed=tmp_path / "processed",
        temp=tmp_path / "temp",
    )
    old_job = "f" * 32
    old_upload = storage.job_dir("uploads", old_job)
    old_output = storage.job_dir("outputs", old_job)
    old_processed = storage.job_dir("processed", old_job)
    old_temp = storage.roots["temp"] / "stale.tmp"
    old_temp.write_text("temporary", encoding="utf-8")
    old_timestamp = time.time() - (3 * 86400)
    for path in (old_upload, old_output, old_processed, old_temp):
        os.utime(path, (old_timestamp, old_timestamp))

    result = storage.cleanup_expired(source_upload_days=1, artifact_days=1, temp_hours=1)

    assert result["expired_artifact_job_ids"] == [old_job]
    assert old_upload.exists() is False
    assert old_output.exists() is False
    assert old_processed.exists() is False
    assert old_temp.exists() is False
    assert result["removed_temp_items"] == 1


def _persist_minimal_analysis(job_id, tmp_path, upload_path=None):
    from app.database.db import persist_analysis

    output = tmp_path / "outputs" / job_id
    output.mkdir(parents=True)
    processed = tmp_path / "processed" / job_id / "classified_feedback.csv"
    processed.parent.mkdir(parents=True)
    result = {
        "dataset": {"filename": "retention.csv", "raw_rows": 1, "total_valid_records": 1},
        "summary": {"themes_identified": 0},
        "ai_breakdown": {"llm_records": 0, "fallback_records": 1},
        "warnings": [],
        "findings": [],
    }
    persist_analysis(
        job_id=job_id, public_result=result, output_dir=output,
        processed_path=processed, upload_path=upload_path,
    )


def test_database_retention_prunes_expired_analysis_history(tmp_path):
    from app.database.db import apply_storage_retention, get_analysis

    job_id = "a" * 32
    _persist_minimal_analysis(job_id, tmp_path)
    assert get_analysis(job_id) is not None
    apply_storage_retention({"expired_artifact_job_ids": [job_id], "expired_upload_job_ids": [], "removed_temp_items": 0})
    assert get_analysis(job_id) is None


def test_database_retention_clears_expired_upload_reference_only(tmp_path):
    from app.database.db import apply_storage_retention, get_analysis

    job_id = "b" * 32
    upload = tmp_path / "uploads" / job_id / "source.csv"
    upload.parent.mkdir(parents=True)
    upload.write_text("Feedback\nA sample\n", encoding="utf-8")
    _persist_minimal_analysis(job_id, tmp_path, upload_path=upload)
    assert get_analysis(job_id)["dataset"]["upload_path"] is not None
    apply_storage_retention({"expired_artifact_job_ids": [], "expired_upload_job_ids": [job_id], "removed_temp_items": 0})
    saved = get_analysis(job_id)
    assert saved is not None
    assert saved["dataset"]["upload_path"] is None
