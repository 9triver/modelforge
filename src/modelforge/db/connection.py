"""数据库连接、Schema 定义、迁移。"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from ..config import get_settings

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
    namespace   TEXT NOT NULL,
    name        TEXT NOT NULL,
    owner_id    INTEGER NOT NULL,
    is_private  INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL,
    UNIQUE(namespace, name),
    FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS repo_cards (
    repo_id       INTEGER PRIMARY KEY,
    revision      TEXT NOT NULL,
    library_name  TEXT,
    pipeline_tag  TEXT,
    license       TEXT,
    tags_json     TEXT,
    base_model    TEXT,
    best_metric_name   TEXT,
    best_metric_value  REAL,
    updated_at    TEXT NOT NULL,
    FOREIGN KEY (repo_id) REFERENCES repos(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_tokens_user_id ON tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_repos_owner_id ON repos(owner_id);
CREATE INDEX IF NOT EXISTS idx_cards_library ON repo_cards(library_name);
CREATE INDEX IF NOT EXISTS idx_cards_pipeline ON repo_cards(pipeline_tag);
CREATE INDEX IF NOT EXISTS idx_cards_license ON repo_cards(license);

CREATE TABLE IF NOT EXISTS evaluations (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_id      INTEGER NOT NULL,
    revision     TEXT NOT NULL,
    task         TEXT NOT NULL,
    status       TEXT NOT NULL,
    metrics_json TEXT,
    primary_metric TEXT,
    primary_value  REAL,
    duration_ms  INTEGER,
    error        TEXT,
    created_at   TEXT NOT NULL,
    FOREIGN KEY (repo_id) REFERENCES repos(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_eval_repo ON evaluations(repo_id);
CREATE INDEX IF NOT EXISTS idx_eval_status ON evaluations(status);

CREATE TABLE IF NOT EXISTS calibrations (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    source_repo_id      INTEGER NOT NULL,
    source_revision     TEXT NOT NULL,
    target_repo         TEXT,
    target_revision     TEXT,
    method              TEXT NOT NULL,
    params_json         TEXT,
    before_metrics_json TEXT,
    after_metrics_json  TEXT,
    primary_metric      TEXT,
    before_value        REAL,
    after_value         REAL,
    status              TEXT NOT NULL,
    duration_ms         INTEGER,
    error               TEXT,
    created_at          TEXT NOT NULL,
    FOREIGN KEY (source_repo_id) REFERENCES repos(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_cal_source ON calibrations(source_repo_id);

CREATE TABLE IF NOT EXISTS transfers (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    source_repo_id      INTEGER NOT NULL,
    source_revision     TEXT NOT NULL,
    target_repo         TEXT,
    target_revision     TEXT,
    method              TEXT NOT NULL,
    classes_json        TEXT,
    n_classes           INTEGER,
    n_samples           INTEGER,
    weights_b64         TEXT,
    after_metrics_json  TEXT,
    primary_metric      TEXT,
    after_value         REAL,
    hparams_json        TEXT,
    current_epoch       INTEGER,
    total_epochs        INTEGER,
    status              TEXT NOT NULL,
    duration_ms         INTEGER,
    error               TEXT,
    created_at          TEXT NOT NULL,
    FOREIGN KEY (source_repo_id) REFERENCES repos(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_transfer_source ON transfers(source_repo_id);

CREATE TABLE IF NOT EXISTS workspaces (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_id         INTEGER NOT NULL,
    container_id    TEXT,
    container_name  TEXT NOT NULL,
    port            INTEGER,
    status          TEXT NOT NULL,
    error           TEXT,
    created_at      TEXT NOT NULL,
    FOREIGN KEY (repo_id) REFERENCES repos(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_ws_status ON workspaces(status);
CREATE INDEX IF NOT EXISTS idx_ws_repo ON workspaces(repo_id);
"""


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@contextmanager
def connect(db_path: Path | None = None):
    """打开数据库连接（自动建表）。"""
    path = db_path or get_settings().db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.executescript(SCHEMA)
    _migrate(conn)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _migrate(conn: sqlite3.Connection) -> None:
    """对老数据库加新列（SQLite 不支持 ADD COLUMN IF NOT EXISTS）。"""
    def _ensure_column(table: str, col: str, ddl: str) -> None:
        cur = conn.execute(f"PRAGMA table_info({table})")
        cols = {row[1] for row in cur.fetchall()}
        if col not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")

    _ensure_column("transfers", "hparams_json", "hparams_json TEXT")
    _ensure_column("transfers", "current_epoch", "current_epoch INTEGER")
    _ensure_column("transfers", "total_epochs", "total_epochs INTEGER")
    _ensure_column("repo_cards", "repo_type", "repo_type TEXT DEFAULT 'model'")
    _ensure_column("repo_cards", "data_format", "data_format TEXT")
