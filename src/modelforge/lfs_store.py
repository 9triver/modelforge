"""LFS 对象本地存储。

物件按 SHA256 两级目录存放：
  data/lfs-objects/ab/cd/abcdef1234.../abcdef1234...

两级目录避免单目录文件数过多。
"""
from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from typing import AsyncIterator, Iterator

from .config import get_settings

CHUNK_SIZE = 256 * 1024  # 256 KB


def _object_path(oid: str) -> Path:
    """SHA256 OID → 物理路径。"""
    return get_settings().lfs_dir / oid[:2] / oid[2:4] / oid


def path_for_oid(oid: str) -> Path | None:
    """返回 OID 对应的物理路径；不存在返回 None。"""
    p = _object_path(oid)
    return p if p.is_file() else None


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


async def write_stream(oid: str, stream: AsyncIterator[bytes], max_size: int) -> tuple[Path, int]:
    """流式写入 LFS 物件，同时计算 SHA256。

    先写到临时文件，校验通过后原子 rename 到目标路径。
    返回 (path, total_bytes)。SHA256 不匹配时抛 ValueError。
    """
    target = _object_path(oid)
    target.parent.mkdir(parents=True, exist_ok=True)

    sha = hashlib.sha256()
    total = 0

    fd, tmp_path = tempfile.mkstemp(dir=target.parent, prefix=".lfs-")
    try:
        with os.fdopen(fd, "wb") as f:
            async for chunk in stream:
                total += len(chunk)
                if total > max_size:
                    raise ValueError(f"Object too large (max {max_size} bytes)")
                sha.update(chunk)
                f.write(chunk)

        actual_sha = sha.hexdigest()
        if actual_sha != oid:
            raise ValueError(f"SHA256 mismatch: expected {oid}, got {actual_sha}")

        os.replace(tmp_path, target)
        return target, total
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def read(oid: str) -> bytes | None:
    p = _object_path(oid)
    return p.read_bytes() if p.is_file() else None


def read_chunks(oid: str) -> Iterator[bytes] | None:
    """流式读取 LFS 物件，每次 yield CHUNK_SIZE 字节。"""
    p = _object_path(oid)
    if not p.is_file():
        return None

    def _gen():
        with open(p, "rb") as f:
            while True:
                chunk = f.read(CHUNK_SIZE)
                if not chunk:
                    break
                yield chunk
    return _gen()


def delete(oid: str) -> bool:
    p = _object_path(oid)
    if p.is_file():
        p.unlink()
        return True
    return False
