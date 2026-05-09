from __future__ import annotations

from .connection import _now, connect
from .models import Transfer


def _row_to_transfer(row) -> Transfer:
    return Transfer(
        id=row["id"], source_repo_id=row["source_repo_id"],
        source_revision=row["source_revision"],
        target_repo=row["target_repo"], target_revision=row["target_revision"],
        method=row["method"],
        classes_json=row["classes_json"],
        n_classes=row["n_classes"], n_samples=row["n_samples"],
        weights_b64=row["weights_b64"],
        after_metrics_json=row["after_metrics_json"],
        primary_metric=row["primary_metric"], after_value=row["after_value"],
        hparams_json=row["hparams_json"],
        current_epoch=row["current_epoch"], total_epochs=row["total_epochs"],
        status=row["status"], duration_ms=row["duration_ms"],
        error=row["error"], created_at=row["created_at"],
    )


def create_transfer(source_repo_id: int, source_revision: str, method: str) -> Transfer:
    with connect() as c:
        c.execute(
            """INSERT INTO transfers
               (source_repo_id, source_revision, method, status, created_at)
               VALUES (?, ?, ?, 'queued', ?)""",
            (source_repo_id, source_revision, method, _now()),
        )
        row = c.execute(
            "SELECT * FROM transfers WHERE id = last_insert_rowid()"
        ).fetchone()
        return _row_to_transfer(row)


def update_transfer(
    transfer_id: int,
    *,
    status: str,
    target_repo: str | None = None,
    target_revision: str | None = None,
    classes_json: str | None = None,
    n_classes: int | None = None,
    n_samples: int | None = None,
    weights_b64: str | None = None,
    after_metrics_json: str | None = None,
    primary_metric: str | None = None,
    after_value: float | None = None,
    hparams_json: str | None = None,
    current_epoch: int | None = None,
    total_epochs: int | None = None,
    duration_ms: int | None = None,
    error: str | None = None,
) -> None:
    with connect() as c:
        c.execute(
            """UPDATE transfers SET
               status = ?, target_repo = ?, target_revision = ?,
               classes_json = ?, n_classes = ?, n_samples = ?,
               weights_b64 = ?, after_metrics_json = ?,
               primary_metric = ?, after_value = ?,
               hparams_json = ?, current_epoch = ?, total_epochs = ?,
               duration_ms = ?, error = ?
               WHERE id = ?""",
            (status, target_repo, target_revision,
             classes_json, n_classes, n_samples, weights_b64,
             after_metrics_json, primary_metric, after_value,
             hparams_json, current_epoch, total_epochs,
             duration_ms, error, transfer_id),
        )


def get_transfer(transfer_id: int) -> Transfer | None:
    with connect() as c:
        row = c.execute(
            "SELECT * FROM transfers WHERE id = ?", (transfer_id,)
        ).fetchone()
        return _row_to_transfer(row) if row else None
