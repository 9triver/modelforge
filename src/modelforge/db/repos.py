from __future__ import annotations

from .connection import _now, connect
from .models import Repo


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


def get_repo_by_id(repo_id: int) -> Repo | None:
    with connect() as c:
        row = c.execute(
            "SELECT * FROM repos WHERE id = ?", (repo_id,)
        ).fetchone()
        return _row_to_repo(row) if row else None


def list_repos() -> list[Repo]:
    with connect() as c:
        rows = c.execute("SELECT * FROM repos ORDER BY namespace, name").fetchall()
        return [_row_to_repo(r) for r in rows]


def get_repo_name(repo_id: int) -> str | None:
    """返回 'namespace/name'，repo 不存在则返回 None。"""
    with connect() as c:
        row = c.execute(
            "SELECT namespace, name FROM repos WHERE id = ?", (repo_id,)
        ).fetchone()
        return f"{row['namespace']}/{row['name']}" if row else None


def delete_repo(namespace: str, name: str) -> bool:
    with connect() as c:
        cur = c.execute(
            "DELETE FROM repos WHERE namespace = ? AND name = ?",
            (namespace, name),
        )
        return cur.rowcount > 0
