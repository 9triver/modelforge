from __future__ import annotations

from .connection import _now, connect
from .models import Evaluation


def _row_to_evaluation(row) -> Evaluation:
    return Evaluation(
        id=row["id"], repo_id=row["repo_id"], revision=row["revision"],
        task=row["task"], status=row["status"],
        metrics_json=row["metrics_json"],
        primary_metric=row["primary_metric"],
        primary_value=row["primary_value"],
        duration_ms=row["duration_ms"],
        error=row["error"],
        created_at=row["created_at"],
    )


def create_evaluation(repo_id: int, revision: str, task: str) -> Evaluation:
    """建一条 queued 状态的评估记录，返回 id 供 worker 更新。"""
    with connect() as c:
        c.execute(
            """INSERT INTO evaluations
               (repo_id, revision, task, status, created_at)
               VALUES (?, ?, ?, 'queued', ?)""",
            (repo_id, revision, task, _now()),
        )
        row = c.execute(
            "SELECT * FROM evaluations WHERE id = last_insert_rowid()"
        ).fetchone()
        return _row_to_evaluation(row)


def update_evaluation(
    eval_id: int,
    *,
    status: str,
    metrics_json: str | None = None,
    primary_metric: str | None = None,
    primary_value: float | None = None,
    duration_ms: int | None = None,
    error: str | None = None,
) -> None:
    with connect() as c:
        c.execute(
            """UPDATE evaluations SET
               status = ?, metrics_json = ?, primary_metric = ?,
               primary_value = ?, duration_ms = ?, error = ?
               WHERE id = ?""",
            (status, metrics_json, primary_metric, primary_value,
             duration_ms, error, eval_id),
        )


def get_evaluation(eval_id: int) -> Evaluation | None:
    with connect() as c:
        row = c.execute(
            "SELECT * FROM evaluations WHERE id = ?", (eval_id,)
        ).fetchone()
        return _row_to_evaluation(row) if row else None


def aggregate_repo_metrics(repo_id: int) -> dict:
    """聚合某 repo 所有成功评估的 primary_value，返回 {count, metric, median, p25, p75}。"""
    with connect() as c:
        rows = c.execute(
            """SELECT primary_metric, primary_value FROM evaluations
               WHERE repo_id = ? AND status = 'ok' AND primary_value IS NOT NULL""",
            (repo_id,),
        ).fetchall()
    if not rows:
        return {"count": 0, "metric": None, "median": None, "p25": None, "p75": None}

    metric = rows[0]["primary_metric"]
    vals = sorted(r["primary_value"] for r in rows if r["primary_metric"] == metric)
    n = len(vals)

    def pct(p: float) -> float:
        if n == 1:
            return vals[0]
        k = (n - 1) * p
        lo, hi = int(k), min(int(k) + 1, n - 1)
        return vals[lo] + (vals[hi] - vals[lo]) * (k - lo)

    return {
        "count": n,
        "metric": metric,
        "median": pct(0.5),
        "p25": pct(0.25),
        "p75": pct(0.75),
    }
