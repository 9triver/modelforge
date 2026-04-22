"""单文件下载 API。

GET /api/v1/repos/{ns}/{name}/raw/{path:path}?revision=main

普通文件走 git show；LFS 文件从 lfs_store 流式返回。
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response, StreamingResponse

from .. import lfs_store, repo_reader, storage

router = APIRouter(prefix="/api/v1/repos", tags=["raw"])

LFS_POINTER_PREFIX = b"version https://git-lfs.github.com/spec/"


def _parse_lfs_oid(data: bytes) -> tuple[str, int] | None:
    if not data.startswith(LFS_POINTER_PREFIX):
        return None
    oid = None
    size = 0
    for line in data.splitlines():
        if line.startswith(b"oid sha256:"):
            oid = line[len(b"oid sha256:"):].decode().strip()
        elif line.startswith(b"size "):
            try:
                size = int(line[5:])
            except ValueError:
                pass
    return (oid, size) if oid else None


@router.get("/{namespace}/{name}/raw/{path:path}")
async def download_file(
    namespace: str,
    name: str,
    path: str,
    revision: str = Query("main"),
):
    bare = storage.repo_path(namespace, name)
    if not bare.is_dir():
        raise HTTPException(404, f"Repository '{namespace}/{name}' not found")

    result = subprocess.run(
        ["git", f"--git-dir={bare}", "show", f"{revision}:{path}"],
        capture_output=True,
    )
    if result.returncode != 0:
        raise HTTPException(404, f"File not found: {path}@{revision}")

    raw = result.stdout

    lfs = _parse_lfs_oid(raw) if len(raw) < 1024 else None
    if lfs:
        oid, size = lfs
        chunks = lfs_store.read_chunks(oid)
        if chunks is None:
            raise HTTPException(404, f"LFS object missing: {oid}")
        filename = Path(path).name
        return StreamingResponse(
            chunks,
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Length": str(size),
            },
        )

    filename = Path(path).name
    return Response(
        content=raw,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
