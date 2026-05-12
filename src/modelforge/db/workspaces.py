"""Workspace CRUD。"""
from __future__ import annotations

from .connection import _now, connect
from .models import Workspace


def _row_to_workspace(row) -> Workspace:
    return Workspace(
        id=row["id"],
        repo_id=row["repo_id"],
        container_id=row["container_id"],
        container_name=row["container_name"],
        port=row["port"],
        status=row["status"],
        error=row["error"],
        created_at=row["created_at"],
    )


def create_workspace(repo_id: int, container_name: str) -> Workspace:
    with connect() as c:
        c.execute(
            """INSERT INTO workspaces
               (repo_id, container_name, status, created_at)
               VALUES (?, ?, 'creating', ?)""",
            (repo_id, container_name, _now()),
        )
        row = c.execute(
            "SELECT * FROM workspaces WHERE id = last_insert_rowid()"
        ).fetchone()
        return _row_to_workspace(row)


def update_workspace(
    ws_id: int,
    *,
    status: str,
    container_id: str | None = None,
    port: int | None = None,
    error: str | None = None,
) -> None:
    with connect() as c:
        c.execute(
            """UPDATE workspaces SET
               status = ?, container_id = ?, port = ?, error = ?
               WHERE id = ?""",
            (status, container_id, port, error, ws_id),
        )


def get_workspace(ws_id: int) -> Workspace | None:
    with connect() as c:
        row = c.execute(
            "SELECT * FROM workspaces WHERE id = ?", (ws_id,)
        ).fetchone()
        return _row_to_workspace(row) if row else None


def get_workspace_by_repo(repo_id: int) -> Workspace | None:
    with connect() as c:
        row = c.execute(
            "SELECT * FROM workspaces WHERE repo_id = ? ORDER BY id DESC LIMIT 1",
            (repo_id,),
        ).fetchone()
        return _row_to_workspace(row) if row else None


def list_workspaces(status: str | None = None) -> list[Workspace]:
    with connect() as c:
        if status:
            rows = c.execute(
                "SELECT * FROM workspaces WHERE status = ? ORDER BY created_at DESC",
                (status,),
            ).fetchall()
        else:
            rows = c.execute(
                "SELECT * FROM workspaces ORDER BY created_at DESC"
            ).fetchall()
        return [_row_to_workspace(r) for r in rows]
