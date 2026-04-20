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
    name        TEXT UNIQUE NOT NULL,         -- 仓库名（不含 .git 后缀）
    owner_id    INTEGER NOT NULL,
    is_private  INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL,
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
    name: str
    owner_id: int
    is_private: bool
    created_at: str


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

def create_repo(name: str, owner_id: int, is_private: bool = False) -> Repo:
    with connect() as c:
        c.execute(
            "INSERT INTO repos (name, owner_id, is_private, created_at) VALUES (?, ?, ?, ?)",
            (name, owner_id, int(is_private), _now()),
        )
        row = c.execute("SELECT * FROM repos WHERE name = ?", (name,)).fetchone()
        return Repo(
            id=row["id"], name=row["name"], owner_id=row["owner_id"],
            is_private=bool(row["is_private"]), created_at=row["created_at"],
        )


def get_repo(name: str) -> Repo | None:
    with connect() as c:
        row = c.execute("SELECT * FROM repos WHERE name = ?", (name,)).fetchone()
        if not row:
            return None
        return Repo(
            id=row["id"], name=row["name"], owner_id=row["owner_id"],
            is_private=bool(row["is_private"]), created_at=row["created_at"],
        )


def list_repos() -> list[Repo]:
    with connect() as c:
        rows = c.execute("SELECT * FROM repos ORDER BY name").fetchall()
        return [
            Repo(
                id=r["id"], name=r["name"], owner_id=r["owner_id"],
                is_private=bool(r["is_private"]), created_at=r["created_at"],
            )
            for r in rows
        ]


def delete_repo(name: str) -> bool:
    with connect() as c:
        cur = c.execute("DELETE FROM repos WHERE name = ?", (name,))
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
    sql += " ORDER BY r.name LIMIT ?"
    args.append(limit)

    with connect() as c:
        rows = c.execute(sql, tuple(args)).fetchall()

    out: list[tuple[Repo, RepoCard | None]] = []
    for r in rows:
        repo = Repo(
            id=r["id"], name=r["name"], owner_id=r["owner_id"],
            is_private=bool(r["is_private"]), created_at=r["created_at"],
        )
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
