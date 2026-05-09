from __future__ import annotations

from .connection import _now, connect
from .models import Token


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
