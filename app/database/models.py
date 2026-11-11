"""SQLAlchemy models for persistent SIGNALDESK analysis history."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class Dataset(Base):
    __tablename__ = "datasets"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(32), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False, default="file_upload")
    upload_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    processed_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    valid_records: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class Analysis(Base):
    __tablename__ = "analyses"
    job_id: Mapped[str] = mapped_column(String(32), ForeignKey("datasets.id", ondelete="CASCADE"), primary_key=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="completed")
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    total_valid_records: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    themes_identified: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fallback_records: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    llm_records: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    summary_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    ai_breakdown_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    warnings_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    result_path: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class Theme(Base):
    __tablename__ = "themes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(32), ForeignKey("analyses.job_id", ondelete="CASCADE"), nullable=False, index=True)
    finding_id: Mapped[str] = mapped_column(String(80), nullable=False)
    theme: Mapped[str] = mapped_column(String(160), nullable=False)
    mention_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    prevalence_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    priority_rank: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    finding_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    __table_args__ = (UniqueConstraint("job_id", "finding_id", name="uq_theme_job_finding"),)


class Evidence(Base):
    __tablename__ = "evidence"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(32), ForeignKey("analyses.job_id", ondelete="CASCADE"), nullable=False, index=True)
    finding_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    record_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    source_row: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    source_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quote: Mapped[str] = mapped_column(Text, nullable=False, default="")
    evidence_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class Report(Base):
    __tablename__ = "reports"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(32), ForeignKey("analyses.job_id", ondelete="CASCADE"), nullable=False, index=True)
    report_type: Mapped[str] = mapped_column(String(40), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    media_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    __table_args__ = (UniqueConstraint("job_id", "report_type", name="uq_report_job_type"),)
