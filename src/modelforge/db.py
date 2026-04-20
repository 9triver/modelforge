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

CREATE INDEX IF NOT EXISTS idx_tokens_user_id ON tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_repos_owner_id ON repos(owner_id);
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
