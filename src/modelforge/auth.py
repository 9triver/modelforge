"""认证与授权辅助。

支持两种 Token 来源：
1. HTTP Basic Auth（Git 默认行为）：username 任意，password 是 token
2. Authorization: Bearer <token>（API 调用）
"""
from __future__ import annotations

import base64
import secrets
from typing import Optional

from fastapi import Header, HTTPException, status

from . import db


def generate_token() -> str:
    """生成新 token，前缀 mf_ 便于人眼辨识。"""
    return "mf_" + secrets.token_urlsafe(32)


def _parse_basic(value: str) -> tuple[str, str] | None:
    """解析 'Basic base64(user:pass)'。"""
    if not value.lower().startswith("basic "):
        return None
    try:
        decoded = base64.b64decode(value.split(" ", 1)[1]).decode("utf-8")
        if ":" not in decoded:
            return None
        user, password = decoded.split(":", 1)
        return user, password
    except Exception:
        return None


def _parse_bearer(value: str) -> str | None:
    if not value.lower().startswith("bearer "):
        return None
    return value.split(" ", 1)[1].strip()


def authenticate(authorization: str | None) -> db.User:
    """从 Authorization 头解析并验证用户。失败抛 401。"""
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": 'Basic realm="modelforge"'},
        )

    token: str | None = _parse_bearer(authorization)
    if token is None:
        parsed = _parse_basic(authorization)
        if parsed:
            _, token = parsed

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unsupported Authorization scheme",
            headers={"WWW-Authenticate": 'Basic realm="modelforge"'},
        )

    tk = db.get_token(token)
    if not tk:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": 'Basic realm="modelforge"'},
        )

    user = db.get_user_by_id(tk.user_id)
    if not user:
        raise HTTPException(status_code=500, detail="Token references missing user")
    return user


def require_user(authorization: Optional[str] = Header(None)) -> db.User:
    """FastAPI 依赖项形式。"""
    return authenticate(authorization)
