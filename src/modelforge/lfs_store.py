"""LFS 对象本地存储。

物件按 SHA256 两级目录存放：
  data/lfs-objects/ab/cdef1234.../abcdef1234...

两级目录避免单目录文件数过多。
"""
from __future__ import annotations

from pathlib import Path

from .config import get_settings


def _object_path(oid: str) -> Path:
    """SHA256 OID → 物理路径。"""
    return get_settings().lfs_dir / oid[:2] / oid[2:4] / oid


def exists(oid: str) -> bool:
    return _object_path(oid).is_file()


def size(oid: str) -> int:
    p = _object_path(oid)
    return p.stat().st_size if p.is_file() else -1


def write(oid: str, data: bytes) -> Path:
    p = _object_path(oid)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return p


def read(oid: str) -> bytes | None:
    p = _object_path(oid)
    return p.read_bytes() if p.is_file() else None


def delete(oid: str) -> bool:
    p = _object_path(oid)
    if p.is_file():
        p.unlink()
        return True
    return False
