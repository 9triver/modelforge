from __future__ import annotations

from .connection import _now, connect
from .models import Calibration


def _row_to_calibration(row) -> Calibration:
    return Calibration(
        id=row["id"], source_repo_id=row["source_repo_id"],
        source_revision=row["source_revision"],
        target_repo=row["target_repo"], target_revision=row["target_revision"],
        method=row["method"], params_json=row["params_json"],
        before_metrics_json=row["before_metrics_json"],
        after_metrics_json=row["after_metrics_json"],
        primary_metric=row["primary_metric"],
        before_value=row["before_value"], after_value=row["after_value"],
        status=row["status"], duration_ms=row["duration_ms"],
        error=row["error"], created_at=row["created_at"],
    )


def create_calibration(source_repo_id: int, source_revision: str, method: str) -> Calibration:
    with connect() as c:
        c.execute(
            """INSERT INTO calibrations
               (source_repo_id, source_revision, method, status, created_at)
               VALUES (?, ?, ?, 'queued', ?)""",
            (source_repo_id, source_revision, method, _now()),
        )
        row = c.execute(
            "SELECT * FROM calibrations WHERE id = last_insert_rowid()"
        ).fetchone()
        return _row_to_calibration(row)


def update_calibration(
    cal_id: int,
    *,
    status: str,
    target_repo: str | None = None,
    target_revision: str | None = None,
    params_json: str | None = None,
    before_metrics_json: str | None = None,
    after_metrics_json: str | None = None,
    primary_metric: str | None = None,
    before_value: float | None = None,
    after_value: float | None = None,
    duration_ms: int | None = None,
    error: str | None = None,
) -> None:
    with connect() as c:
        c.execute(
            """UPDATE calibrations SET
               status = ?, target_repo = ?, target_revision = ?,
               params_json = ?, before_metrics_json = ?, after_metrics_json = ?,
               primary_metric = ?, before_value = ?, after_value = ?,
               duration_ms = ?, error = ?
               WHERE id = ?""",
            (status, target_repo, target_revision, params_json,
             before_metrics_json, after_metrics_json, primary_metric,
             before_value, after_value, duration_ms, error, cal_id),
        )


def get_calibration(cal_id: int) -> Calibration | None:
    with connect() as c:
        row = c.execute(
            "SELECT * FROM calibrations WHERE id = ?", (cal_id,)
        ).fetchone()
        return _row_to_calibration(row) if row else None
