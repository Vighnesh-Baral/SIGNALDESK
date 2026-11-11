"""Safe filesystem storage helpers used by SIGNALDESK.

The application writes all durable files beneath configured upload/output/processed
roots. Deployments should mount Render Persistent Disk at SIGNALDESK_STORAGE_ROOT.
"""
from __future__ import annotations

import re
import shutil
import time
from pathlib import Path
from typing import Literal

_JOB_ID = re.compile(r"^[a-f0-9]{32}$")


class StorageError(RuntimeError):
    """Raised when a requested storage location is invalid or unavailable."""


class FileStorage:
    def __init__(self, *, uploads: Path, outputs: Path, processed: Path, temp: Path):
        self.roots = {
            "uploads": Path(uploads).resolve(),
            "outputs": Path(outputs).resolve(),
            "processed": Path(processed).resolve(),
            "temp": Path(temp).resolve(),
        }
        self.ensure_directories()

    def ensure_directories(self) -> None:
        for root in self.roots.values():
            root.mkdir(parents=True, exist_ok=True)

    def job_dir(self, area: Literal["uploads", "outputs", "processed", "temp"], job_id: str) -> Path:
        if area not in self.roots or not _JOB_ID.fullmatch(str(job_id)):
            raise StorageError("Invalid storage area or job identifier.")
        root = self.roots[area]
        candidate = (root / job_id).resolve()
        if candidate.parent != root:
            raise StorageError("Storage path escaped its configured root.")
        candidate.mkdir(parents=True, exist_ok=True)
        return candidate

    def file_path(self, area: Literal["uploads", "outputs", "processed", "temp"], job_id: str, filename: str) -> Path:
        clean = Path(str(filename)).name
        if not clean or clean in {".", ".."}:
            raise StorageError("Invalid file name.")
        folder = self.job_dir(area, job_id)
        target = (folder / clean).resolve()
        if target.parent != folder:
            raise StorageError("Storage path escaped its job directory.")
        return target

    def cleanup_expired(
        self, *, source_upload_days: int = 30, artifact_days: int = 90, temp_hours: int = 24,
        now: float | None = None,
    ) -> dict[str, list[str] | int]:
        """Remove expired job files and temporary items, returning affected job IDs.

        Retention is based on the job-folder modification time. Source uploads have a
        shorter independent retention window. Expired artifact job IDs are returned so
        their corresponding database history can be pruned in the same startup task.
        """
        current = time.time() if now is None else float(now)
        artifact_cutoff = current - max(1, int(artifact_days)) * 86400
        upload_cutoff = current - max(1, int(source_upload_days)) * 86400
        temp_cutoff = current - max(1, int(temp_hours)) * 3600
        expired_artifacts: set[str] = set()
        expired_uploads: set[str] = set()
        removed_temp = 0

        def expired(path: Path, cutoff: float) -> bool:
            try:
                return path.stat().st_mtime < cutoff
            except OSError:
                return False

        # Outputs determine whether an analysis is still available as a file-backed job.
        for folder in self.roots["outputs"].iterdir():
            if folder.is_dir() and _JOB_ID.fullmatch(folder.name) and expired(folder, artifact_cutoff):
                expired_artifacts.add(folder.name)
                shutil.rmtree(folder, ignore_errors=True)
        # Clean processed artefacts for expired jobs and stale orphaned processed folders.
        for folder in self.roots["processed"].iterdir():
            if folder.is_dir() and _JOB_ID.fullmatch(folder.name) and (
                folder.name in expired_artifacts or expired(folder, artifact_cutoff)
            ):
                expired_artifacts.add(folder.name)
                shutil.rmtree(folder, ignore_errors=True)
        for job_id in expired_artifacts:
            shutil.rmtree(self.roots["outputs"] / job_id, ignore_errors=True)
            shutil.rmtree(self.roots["uploads"] / job_id, ignore_errors=True)

        for folder in self.roots["uploads"].iterdir():
            if folder.is_dir() and _JOB_ID.fullmatch(folder.name) and expired(folder, upload_cutoff):
                expired_uploads.add(folder.name)
                shutil.rmtree(folder, ignore_errors=True)

        for item in self.roots["temp"].iterdir():
            if expired(item, temp_cutoff):
                if item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)
                else:
                    try:
                        item.unlink(missing_ok=True)
                    except OSError:
                        continue
                removed_temp += 1

        return {
            "expired_artifact_job_ids": sorted(expired_artifacts),
            "expired_upload_job_ids": sorted(expired_uploads),
            "removed_temp_items": removed_temp,
        }

    def check_writable(self) -> bool:
        probe = self.roots["temp"] / ".signaldesk-write-check"
        try:
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return True
        except OSError:
            return False


def safe_job_directory(root: Path, job_id: str) -> Path:
    """Resolve/create a job directory under an explicit root (test friendly)."""
    if not _JOB_ID.fullmatch(str(job_id)):
        raise StorageError("Invalid job identifier.")
    resolved_root = Path(root).resolve()
    candidate = (resolved_root / job_id).resolve()
    if candidate.parent != resolved_root:
        raise StorageError("Storage path escaped its configured root.")
    candidate.mkdir(parents=True, exist_ok=True)
    return candidate
