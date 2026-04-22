"""SQLite 持久层：用户、Token、仓库元数据。

不引入 SQLAlchemy 等 ORM，用标准库 sqlite3 + 显式 SQL，
保持依赖最小、行为可预测。
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .config import get_settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT UNIQUE NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tokens (
    token       TEXT PRIMARY KEY,
    user_id     INTEGER NOT NULL,
    description TEXT,
    created_at  TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS repos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    namespace   TEXT NOT NULL,                -- 命名空间（如 amazon / jiangsu / chun）
    name        TEXT NOT NULL,                -- 仓库名（不含 .git 后缀）
    owner_id    INTEGER NOT NULL,
    is_private  INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL,
    UNIQUE(namespace, name),
    FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS repo_cards (
    repo_id       INTEGER PRIMARY KEY,              -- 1:1 with repos.id
    revision      TEXT NOT NULL,                    -- 最后一次校验通过的 commit SHA
    library_name  TEXT,
    pipeline_tag  TEXT,
    license       TEXT,
    tags_json     TEXT,                             -- JSON array of tags
    base_model    TEXT,
    best_metric_name   TEXT,                        -- 从 model-index 扁平化后取最优
    best_metric_value  REAL,                        -- 数值（越小越好约定：mape/rmse/mae；其他指标仅作展示）
    updated_at    TEXT NOT NULL,
    FOREIGN KEY (repo_id) REFERENCES repos(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_tokens_user_id ON tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_repos_owner_id ON repos(owner_id);
CREATE INDEX IF NOT EXISTS idx_cards_library ON repo_cards(library_name);
CREATE INDEX IF NOT EXISTS idx_cards_pipeline ON repo_cards(pipeline_tag);
CREATE INDEX IF NOT EXISTS idx_cards_license ON repo_cards(license);

-- 评估记录：只存 repo 级匿名聚合所需字段，不关联用户/不留输入数据
CREATE TABLE IF NOT EXISTS evaluations (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_id      INTEGER NOT NULL,
    revision     TEXT NOT NULL,              -- 评估的 commit SHA
    task         TEXT NOT NULL,              -- pipeline_tag
    status       TEXT NOT NULL,              -- 'queued' | 'running' | 'ok' | 'error'
    metrics_json TEXT,                        -- JSON: {mape: 0.08, ...}
    primary_metric TEXT,
    primary_value  REAL,
    duration_ms  INTEGER,
    error        TEXT,
    created_at   TEXT NOT NULL,
    FOREIGN KEY (repo_id) REFERENCES repos(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_eval_repo ON evaluations(repo_id);
CREATE INDEX IF NOT EXISTS idx_eval_status ON evaluations(status);

-- 校准记录
CREATE TABLE IF NOT EXISTS calibrations (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    source_repo_id      INTEGER NOT NULL,
    source_revision     TEXT NOT NULL,
    target_repo         TEXT,              -- fork 出的 namespace/name
    target_revision     TEXT,              -- fork 的 commit SHA
    method              TEXT NOT NULL,     -- 'linear_bias'
    params_json         TEXT,              -- {"a": 1.02, "b": -0.5}
    before_metrics_json TEXT,
    after_metrics_json  TEXT,
    primary_metric      TEXT,
    before_value        REAL,
    after_value         REAL,
    status              TEXT NOT NULL,     -- queued|running|ok|error
    duration_ms         INTEGER,
    error               TEXT,
    created_at          TEXT NOT NULL,
    FOREIGN KEY (source_repo_id) REFERENCES repos(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_cal_source ON calibrations(source_repo_id);

-- 迁移学习记录（Phase 4b）
CREATE TABLE IF NOT EXISTS transfers (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    source_repo_id      INTEGER NOT NULL,
    source_revision     TEXT NOT NULL,
    target_repo         TEXT,              -- fork 出的 namespace/name
    target_revision     TEXT,              -- fork 的 commit SHA
    method              TEXT NOT NULL,     -- 'linear_probe'
    classes_json        TEXT,              -- JSON list of class names
    n_classes           INTEGER,
    n_samples           INTEGER,
    weights_b64         TEXT,              -- base64 pickle 的 sklearn 模型
    after_metrics_json  TEXT,
    primary_metric      TEXT,
    after_value         REAL,
    status              TEXT NOT NULL,     -- queued|running|previewed|saving|ok|error
    duration_ms         INTEGER,
    error               TEXT,
    created_at          TEXT NOT NULL,
    FOREIGN KEY (source_repo_id) REFERENCES repos(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_transfer_source ON transfers(source_repo_id);
"""


@dataclass
class User:
    id: int
    name: str
    created_at: str


@dataclass
class Token:
    token: str
    user_id: int
    description: str | None
    created_at: str


@dataclass
class Repo:
    id: int
    namespace: str
    name: str
    owner_id: int
    is_private: bool
    created_at: str

    @property
    def full_name(self) -> str:
        return f"{self.namespace}/{self.name}"


@dataclass
class RepoCard:
    repo_id: int
    revision: str
    library_name: str | None
    pipeline_tag: str | None
    license: str | None
    tags_json: str | None       # JSON array
    base_model: str | None
    best_metric_name: str | None
    best_metric_value: float | None
    updated_at: str


@dataclass
class Evaluation:
    id: int
    repo_id: int
    revision: str
    task: str
    status: str
    metrics_json: str | None
    primary_metric: str | None
    primary_value: float | None
    duration_ms: int | None
    error: str | None
    created_at: str


@dataclass
class Calibration:
    id: int
    source_repo_id: int
    source_revision: str
    target_repo: str | None
    target_revision: str | None
    method: str
    params_json: str | None
    before_metrics_json: str | None
    after_metrics_json: str | None
    primary_metric: str | None
    before_value: float | None
    after_value: float | None
    status: str
    duration_ms: int | None
    error: str | None
    created_at: str


@dataclass
class Transfer:
    id: int
    source_repo_id: int
    source_revision: str
    target_repo: str | None
    target_revision: str | None
    method: str
    classes_json: str | None
    n_classes: int | None
    n_samples: int | None
    weights_b64: str | None
    after_metrics_json: str | None
    primary_metric: str | None
    after_value: float | None
    status: str
    duration_ms: int | None
    error: str | None
    created_at: str


def _now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


@contextmanager
def connect(db_path: Path | None = None):
    """打开数据库连接（自动建表）。"""
    path = db_path or get_settings().db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.executescript(SCHEMA)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# ---------- 用户 ----------

def create_user(name: str) -> User:
    with connect() as c:
        c.execute(
            "INSERT INTO users (name, created_at) VALUES (?, ?)",
            (name, _now()),
        )
        row = c.execute("SELECT * FROM users WHERE name = ?", (name,)).fetchone()
        return User(**dict(row))


def get_user_by_name(name: str) -> User | None:
    with connect() as c:
        row = c.execute("SELECT * FROM users WHERE name = ?", (name,)).fetchone()
        return User(**dict(row)) if row else None


def get_user_by_id(user_id: int) -> User | None:
    with connect() as c:
        row = c.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return User(**dict(row)) if row else None


def list_users() -> list[User]:
    with connect() as c:
        rows = c.execute("SELECT * FROM users ORDER BY id").fetchall()
        return [User(**dict(r)) for r in rows]


# ---------- Token ----------

def create_token(user_id: int, token: str, description: str | None = None) -> Token:
    with connect() as c:
        c.execute(
            "INSERT INTO tokens (token, user_id, description, created_at) VALUES (?, ?, ?, ?)",
            (token, user_id, description, _now()),
        )
        row = c.execute("SELECT * FROM tokens WHERE token = ?", (token,)).fetchone()
        return Token(**dict(row))


def get_token(token: str) -> Token | None:
    with connect() as c:
        row = c.execute("SELECT * FROM tokens WHERE token = ?", (token,)).fetchone()
        return Token(**dict(row)) if row else None


def revoke_token(token: str) -> bool:
    with connect() as c:
        cur = c.execute("DELETE FROM tokens WHERE token = ?", (token,))
        return cur.rowcount > 0


# ---------- 仓库 ----------

def _row_to_repo(row) -> Repo:
    return Repo(
        id=row["id"], namespace=row["namespace"], name=row["name"],
        owner_id=row["owner_id"], is_private=bool(row["is_private"]),
        created_at=row["created_at"],
    )


def create_repo(namespace: str, name: str, owner_id: int, is_private: bool = False) -> Repo:
    with connect() as c:
        c.execute(
            "INSERT INTO repos (namespace, name, owner_id, is_private, created_at) VALUES (?, ?, ?, ?, ?)",
            (namespace, name, owner_id, int(is_private), _now()),
        )
        row = c.execute(
            "SELECT * FROM repos WHERE namespace = ? AND name = ?",
            (namespace, name),
        ).fetchone()
        return _row_to_repo(row)


def get_repo(namespace: str, name: str) -> Repo | None:
    with connect() as c:
        row = c.execute(
            "SELECT * FROM repos WHERE namespace = ? AND name = ?",
            (namespace, name),
        ).fetchone()
        return _row_to_repo(row) if row else None


def list_repos() -> list[Repo]:
    with connect() as c:
        rows = c.execute("SELECT * FROM repos ORDER BY namespace, name").fetchall()
        return [_row_to_repo(r) for r in rows]


def delete_repo(namespace: str, name: str) -> bool:
    with connect() as c:
        cur = c.execute(
            "DELETE FROM repos WHERE namespace = ? AND name = ?",
            (namespace, name),
        )
        return cur.rowcount > 0


# ---------- Repo Cards ----------

def upsert_repo_card(card: RepoCard) -> None:
    with connect() as c:
        c.execute(
            """
            INSERT INTO repo_cards
                (repo_id, revision, library_name, pipeline_tag, license,
                 tags_json, base_model, best_metric_name, best_metric_value, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(repo_id) DO UPDATE SET
                revision = excluded.revision,
                library_name = excluded.library_name,
                pipeline_tag = excluded.pipeline_tag,
                license = excluded.license,
                tags_json = excluded.tags_json,
                base_model = excluded.base_model,
                best_metric_name = excluded.best_metric_name,
                best_metric_value = excluded.best_metric_value,
                updated_at = excluded.updated_at
            """,
            (
                card.repo_id, card.revision, card.library_name, card.pipeline_tag,
                card.license, card.tags_json, card.base_model,
                card.best_metric_name, card.best_metric_value, card.updated_at,
            ),
        )


def get_repo_card(repo_id: int) -> RepoCard | None:
    with connect() as c:
        row = c.execute("SELECT * FROM repo_cards WHERE repo_id = ?", (repo_id,)).fetchone()
        return RepoCard(**dict(row)) if row else None


def search_repos(
    library_name: str | None = None,
    pipeline_tag: str | None = None,
    license_: str | None = None,
    tag: str | None = None,             # 单个 tag 子串匹配 tags_json
    max_metric: float | None = None,    # best_metric_value <= max_metric
    metric_name: str | None = None,     # 限定指标名（如 'mape'）
    limit: int = 100,
) -> list[tuple[Repo, RepoCard | None]]:
    """组合条件搜索仓库。返回 (repo, card) 列表。"""
    sql = """
        SELECT r.*, c.repo_id AS c_repo_id, c.revision, c.library_name, c.pipeline_tag,
               c.license, c.tags_json, c.base_model,
               c.best_metric_name, c.best_metric_value, c.updated_at
        FROM repos r
        LEFT JOIN repo_cards c ON r.id = c.repo_id
        WHERE 1=1
    """
    args: list = []
    if library_name:
        sql += " AND c.library_name = ?"
        args.append(library_name)
    if pipeline_tag:
        sql += " AND c.pipeline_tag = ?"
        args.append(pipeline_tag)
    if license_:
        sql += " AND c.license = ?"
        args.append(license_)
    if tag:
        sql += " AND c.tags_json LIKE ?"
        args.append(f'%"{tag}"%')
    if max_metric is not None:
        sql += " AND c.best_metric_value IS NOT NULL AND c.best_metric_value <= ?"
        args.append(max_metric)
    if metric_name:
        sql += " AND c.best_metric_name = ?"
        args.append(metric_name)
    sql += " ORDER BY r.namespace, r.name LIMIT ?"
    args.append(limit)

    with connect() as c:
        rows = c.execute(sql, tuple(args)).fetchall()

    out: list[tuple[Repo, RepoCard | None]] = []
    for r in rows:
        repo = _row_to_repo(r)
        card = None
        if r["c_repo_id"] is not None:
            card = RepoCard(
                repo_id=r["c_repo_id"], revision=r["revision"],
                library_name=r["library_name"], pipeline_tag=r["pipeline_tag"],
                license=r["license"], tags_json=r["tags_json"],
                base_model=r["base_model"],
                best_metric_name=r["best_metric_name"],
                best_metric_value=r["best_metric_value"],
                updated_at=r["updated_at"],
            )
        out.append((repo, card))
    return out


# ---------- Evaluations ----------

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


# ---------- Calibrations ----------

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


# ---------- Transfers (Phase 4b) ----------

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
               duration_ms = ?, error = ?
               WHERE id = ?""",
            (status, target_repo, target_revision,
             classes_json, n_classes, n_samples, weights_b64,
             after_metrics_json, primary_metric, after_value,
             duration_ms, error, transfer_id),
        )


def get_transfer(transfer_id: int) -> Transfer | None:
    with connect() as c:
        row = c.execute(
            "SELECT * FROM transfers WHERE id = ?", (transfer_id,)
        ).fetchone()
        return _row_to_transfer(row) if row else None
