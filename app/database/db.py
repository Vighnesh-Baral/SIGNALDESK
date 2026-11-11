"""SQLAlchemy engine and persistence operations for analysis history."""
from __future__ import annotations

import logging
import uuid
from threading import Lock
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from sqlalchemy import create_engine, delete, func, select, text, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import DATABASE_MAX_OVERFLOW, DATABASE_POOL_SIZE, DATABASE_URL
from app.database.models import Analysis, Base, Dataset, Evidence, Project, Report, Theme

logger = logging.getLogger("signaldesk.database")
DEFAULT_PROJECT_ID = "00000000000000000000000000000000"


def _engine_options() -> dict[str, Any]:
    options: dict[str, Any] = {"pool_pre_ping": True, "future": True}
    if DATABASE_URL.startswith("sqlite:"):
        options["connect_args"] = {"check_same_thread": False, "timeout": 30}
    else:
        options.update(pool_size=DATABASE_POOL_SIZE, max_overflow=DATABASE_MAX_OVERFLOW, pool_recycle=1800)
    return options


engine = create_engine(DATABASE_URL, **_engine_options())
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)
_database_initialized = False
_database_init_lock = Lock()


def initialize_database() -> None:
    """Create any missing tables once per process; production evolution uses Alembic."""
    global _database_initialized
    if _database_initialized:
        return
    with _database_init_lock:
        if _database_initialized:
            return
        Base.metadata.create_all(bind=engine)
        with SessionLocal.begin() as session:
            if session.get(Project, DEFAULT_PROJECT_ID) is None:
                session.add(Project(id=DEFAULT_PROJECT_ID, name="Default Workspace", description="Default SIGNALDESK research workspace."))
        _database_initialized = True


@contextmanager
def session_scope() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def check_database() -> tuple[bool, str | None]:
    try:
        with engine.connect() as connection:
            connection.execute(select(1))
        return True, None
    except SQLAlchemyError as exc:
        logger.warning("Database health check failed: %s", exc)
        return False, str(exc)[:300]


def persist_analysis(
    *,
    job_id: str,
    public_result: dict[str, Any],
    output_dir: Path,
    processed_path: Path,
    upload_path: Path | None = None,
    source_type: str = "file_upload",
    project_id: str = DEFAULT_PROJECT_ID,
) -> None:
    """Persist dataset, analysis summary, themes, evidence and downloadable reports."""
    initialize_database()
    dataset = public_result.get("dataset", {})
    summary = public_result.get("summary", {})
    ai = public_result.get("ai_breakdown", {})
    findings = public_result.get("findings", [])
    upload_exists = upload_path is not None and upload_path.is_file()
    upload_size = upload_path.stat().st_size if upload_exists and upload_path else None

    if not isinstance(project_id, str) or len(project_id) != 32 or any(ch not in "0123456789abcdef" for ch in project_id):
        raise ValueError("Project ID must be a 32-character lowercase hexadecimal identifier.")
    with session_scope() as session:
        if session.get(Project, project_id) is None:
            raise ValueError("The selected project/workspace does not exist.")
        session.merge(Dataset(
            id=job_id,
            project_id=project_id,
            filename=str(dataset.get("filename", "customer_feedback"))[:255],
            source_type=source_type,
            upload_path=str(upload_path.resolve()) if upload_exists and upload_path else None,
            processed_path=str(processed_path.resolve()),
            file_size_bytes=upload_size,
            raw_rows=int(dataset.get("raw_rows", 0) or 0),
            valid_records=int(dataset.get("total_valid_records", 0) or 0),
            metadata_json={
                "empty_rows_removed": int(dataset.get("empty_rows_removed", 0) or 0),
                "exact_duplicate_mentions": int(dataset.get("exact_duplicate_mentions", 0) or 0),
                "unique_normalized_feedback": int(dataset.get("unique_normalized_feedback", 0) or 0),
            },
        ))
        # Dataset.id is the parent key referenced by analyses.job_id. With no ORM
        # relationship configured, explicitly flush the parent row before inserting
        # the dependent Analysis row (PostgreSQL enforces this foreign key immediately).
        session.flush()
        session.merge(Analysis(
            job_id=job_id,
            status="completed",
            filename=str(dataset.get("filename", "customer_feedback"))[:255],
            total_valid_records=int(dataset.get("total_valid_records", 0) or 0),
            themes_identified=int(summary.get("themes_identified", 0) or 0),
            fallback_records=int(ai.get("fallback_records", 0) or 0),
            llm_records=int(ai.get("llm_records", ai.get("qwen3_records", 0)) or 0),
            summary_json=summary,
            ai_breakdown_json=ai,
            warnings_json=list(public_result.get("warnings", [])),
            result_path=str((output_dir / "result.json").resolve()),
        ))
        # Make persistence idempotent if a job is retried after partial completion.
        session.execute(delete(Theme).where(Theme.job_id == job_id))
        session.execute(delete(Evidence).where(Evidence.job_id == job_id))
        session.execute(delete(Report).where(Report.job_id == job_id))

        for finding in findings:
            finding_id = str(finding.get("finding_id", ""))[:80]
            session.add(Theme(
                job_id=job_id,
                finding_id=finding_id,
                theme=str(finding.get("theme", "Unclassified"))[:160],
                mention_count=int(finding.get("mention_count", 0) or 0),
                prevalence_pct=float(finding.get("prevalence_pct", 0) or 0),
                priority_rank=int(finding.get("priority_rank", 0) or 0),
                finding_json=finding,
            ))
            for item in finding.get("evidence", []) or []:
                session.add(Evidence(
                    job_id=job_id,
                    finding_id=finding_id,
                    record_id=str(item.get("record_id", ""))[:100],
                    source_row=int(item["source_row"]) if str(item.get("source_row", "")).isdigit() else None,
                    source_reference=str(item.get("source_reference", "")) or None,
                    source_id=str(item.get("source_id", "")) or None,
                    source_page=int(item["source_page"]) if str(item.get("source_page", "")).isdigit() else None,
                    quote=str(item.get("quote", "")),
                    evidence_json=item,
                ))

        report_specs = {
            "excel": ("signaldesk_research_report.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            "pdf": ("signaldesk_research_brief.pdf", "application/pdf"),
            "chart": ("theme_frequencies.png", "image/png"),
            "decision_pack": ("product_decision_pack.md", "text/markdown"),
            "processed_feedback": ("classified_feedback.csv", "text/csv"),
            "result": ("result.json", "application/json"),
            "decision_pack_json": ("decision_pack.json", "application/json"),
        }
        for report_type, (filename, media_type) in report_specs.items():
            path = output_dir / filename
            if path.is_file():
                session.add(Report(
                    job_id=job_id,
                    report_type=report_type,
                    filename=filename,
                    storage_path=str(path.resolve()),
                    media_type=media_type,
                    size_bytes=path.stat().st_size,
                ))


def get_analysis(job_id: str) -> dict[str, Any] | None:
    with session_scope() as session:
        row = session.get(Analysis, job_id)
        dataset = session.get(Dataset, job_id)
        if row is None or dataset is None:
            return None
        return {
            "job_id": row.job_id,
            "status": row.status,
            "filename": row.filename,
            "total_valid_records": row.total_valid_records,
            "themes_identified": row.themes_identified,
            "llm_records": row.llm_records,
            "fallback_records": row.fallback_records,
            "summary": row.summary_json,
            "ai_breakdown": row.ai_breakdown_json,
            "warnings": row.warnings_json,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "completed_at": row.completed_at.isoformat() if row.completed_at else None,
            "dataset": {
                "filename": dataset.filename,
                "project_id": dataset.project_id,
                "source_type": dataset.source_type,
                "upload_path": dataset.upload_path,
                "processed_path": dataset.processed_path,
                "file_size_bytes": dataset.file_size_bytes,
                "raw_rows": dataset.raw_rows,
                "valid_records": dataset.valid_records,
                **dataset.metadata_json,
            },
        }


def list_analyses(limit: int = 20, project_id: str | None = None) -> list[dict[str, Any]]:
    initialize_database()
    safe_limit = max(1, min(int(limit), 100))
    statement = select(Analysis, Dataset.project_id).join(Dataset, Dataset.id == Analysis.job_id)
    if project_id:
        statement = statement.where(Dataset.project_id == project_id)
    statement = statement.order_by(Analysis.created_at.desc()).limit(safe_limit)
    with session_scope() as session:
        rows = session.execute(statement).all()
        return [{
            "job_id": row.job_id,
            "project_id": project_id_value,
            "status": row.status,
            "filename": row.filename,
            "total_valid_records": row.total_valid_records,
            "themes_identified": row.themes_identified,
            "llm_records": row.llm_records,
            "fallback_records": row.fallback_records,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        } for row, project_id_value in rows]


def database_table_count() -> int:
    with engine.connect() as connection:
        return int(connection.execute(text("SELECT COUNT(*) FROM analyses")).scalar_one())


def apply_storage_retention(cleanup_result: dict[str, Any]) -> None:
    """Keep database metadata aligned with filesystem retention cleanup."""
    expired_jobs = [str(item) for item in cleanup_result.get("expired_artifact_job_ids", [])]
    expired_uploads = [str(item) for item in cleanup_result.get("expired_upload_job_ids", [])]
    if not expired_jobs and not expired_uploads:
        return
    initialize_database()
    with session_scope() as session:
        if expired_jobs:
            session.execute(delete(Evidence).where(Evidence.job_id.in_(expired_jobs)))
            session.execute(delete(Theme).where(Theme.job_id.in_(expired_jobs)))
            session.execute(delete(Report).where(Report.job_id.in_(expired_jobs)))
            session.execute(delete(Analysis).where(Analysis.job_id.in_(expired_jobs)))
            session.execute(delete(Dataset).where(Dataset.id.in_(expired_jobs)))
        if expired_uploads:
            session.execute(
                update(Dataset).where(Dataset.id.in_(expired_uploads)).values(upload_path=None)
            )


def list_projects() -> list[dict[str, Any]]:
    initialize_database()
    with session_scope() as session:
        rows = session.scalars(select(Project).order_by(Project.created_at.asc())).all()
        output = []
        for row in rows:
            dataset_count = session.scalar(
                select(func.count()).select_from(Dataset).where(Dataset.project_id == row.id)
            ) or 0
            output.append({
                "project_id": row.id,
                "name": row.name,
                "description": row.description,
                "dataset_count": int(dataset_count),
                "created_at": row.created_at.isoformat() if row.created_at else None,
            })
        return output


def project_exists(project_id: str) -> bool:
    """Return whether a workspace identifier exists."""
    if not isinstance(project_id, str) or len(project_id) != 32 or any(ch not in "0123456789abcdef" for ch in project_id):
        return False
    initialize_database()
    with session_scope() as session:
        return session.get(Project, project_id) is not None


def create_project(name: str, description: str | None = None) -> dict[str, Any]:
    initialize_database()
    clean_name = " ".join(str(name).split())
    clean_description = str(description or "").strip() or None
    if not clean_name or len(clean_name) > 120:
        raise ValueError("Project name must contain 1 to 120 characters.")
    if clean_description and len(clean_description) > 500:
        raise ValueError("Project description must be 500 characters or fewer.")
    project = Project(id=uuid.uuid4().hex, name=clean_name, description=clean_description)
    try:
        with session_scope() as session:
            session.add(project)
            session.flush()
            return {
                "project_id": project.id,
                "name": project.name,
                "description": project.description,
                "dataset_count": 0,
                "created_at": project.created_at.isoformat() if project.created_at else None,
            }
    except IntegrityError as exc:
        raise ValueError("A project with that name already exists.") from exc
