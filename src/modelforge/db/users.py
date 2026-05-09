from __future__ import annotations

from .connection import _now, connect
from .models import User


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
