"""Git-LFS Batch API 实现。

规范参考：https://github.com/git-lfs/git-lfs/blob/main/docs/api/batch.md

核心流程：
1. 客户端 POST /{repo}.git/info/lfs/objects/batch
   → 报告要上传/下载哪些 OID
2. 服务端返回每个 OID 的上传/下载 URL
3. 客户端对每个 OID 执行 PUT（上传）或 GET（下载）

本实现把上传/下载 URL 指向自身（不外包给 S3），
物件直接落盘到 data/lfs-objects/。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Header, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .. import db, lfs_store, storage
from ..auth import authenticate
from ..config import get_settings

router = APIRouter(tags=["lfs"])

LFS_CONTENT_TYPE = "application/vnd.git-lfs+json"


# ---------- Batch API 请求/响应模型 ----------

class LfsBatchObject(BaseModel):
    oid: str
    size: int


class LfsBatchRequest(BaseModel):
    operation: str  # "upload" | "download"
    transfers: list[str] | None = None
    objects: list[LfsBatchObject]


class LfsAction(BaseModel):
    href: str
    header: dict[str, str] | None = None


class LfsBatchObjectResponse(BaseModel):
    oid: str
    size: int
    authenticated: bool = True
    actions: dict[str, LfsAction] | None = None
    error: dict[str, Any] | None = None


class LfsBatchResponse(BaseModel):
    transfer: str = "basic"
    objects: list[LfsBatchObjectResponse]


# ---------- Batch 端点 ----------

@router.post(
    "/{repo_name}.git/info/lfs/objects/batch",
    response_model=LfsBatchResponse,
)
async def lfs_batch(
    repo_name: str,
    req: LfsBatchRequest,
    request: Request,
    authorization: str | None = Header(None),
):
    """LFS Batch API：客户端报告要传/取哪些 OID，服务端返回 URL。"""
    repo = db.get_repo(repo_name)
    if not repo:
        raise HTTPException(404, f"Repository '{repo_name}' not found")

    if req.operation == "upload":
        authenticate(authorization)

    # 构造 base URL（从请求推断）
    base = str(request.base_url).rstrip("/")

    objects: list[LfsBatchObjectResponse] = []
    for obj in req.objects:
        if req.operation == "upload":
            if lfs_store.exists(obj.oid) and lfs_store.size(obj.oid) == obj.size:
                # 已存在且大小一致，不需要重传
                objects.append(LfsBatchObjectResponse(oid=obj.oid, size=obj.size))
            else:
                objects.append(LfsBatchObjectResponse(
                    oid=obj.oid,
                    size=obj.size,
                    actions={
                        "upload": LfsAction(
                            href=f"{base}/{repo_name}.git/lfs/objects/{obj.oid}",
                            header={"Authorization": authorization or ""},
                        ),
                        "verify": LfsAction(
                            href=f"{base}/{repo_name}.git/lfs/verify",
                            header={"Authorization": authorization or ""},
                        ),
                    },
                ))
        elif req.operation == "download":
            if lfs_store.exists(obj.oid):
                objects.append(LfsBatchObjectResponse(
                    oid=obj.oid,
                    size=obj.size,
                    actions={
                        "download": LfsAction(
                            href=f"{base}/{repo_name}.git/lfs/objects/{obj.oid}",
                        ),
                    },
                ))
            else:
                objects.append(LfsBatchObjectResponse(
                    oid=obj.oid,
                    size=obj.size,
                    error={"code": 404, "message": "Object not found"},
                ))

    return LfsBatchResponse(objects=objects)


# ---------- 上传端点 ----------

@router.put("/{repo_name}.git/lfs/objects/{oid}")
async def lfs_upload(
    repo_name: str,
    oid: str,
    request: Request,
    authorization: str | None = Header(None),
):
    """流式接收 LFS 物件，边写边算 SHA256。"""
    authenticate(authorization)

    settings = get_settings()

    try:
        _path, total = await lfs_store.write_stream(
            oid, request.stream(), max_size=settings.lfs_max_object_size,
        )
    except ValueError as e:
        msg = str(e)
        if "mismatch" in msg:
            raise HTTPException(422, msg)
        if "too large" in msg:
            raise HTTPException(413, msg)
        raise HTTPException(400, msg)

    return Response(status_code=200)


# ---------- 下载端点 ----------

@router.get("/{repo_name}.git/lfs/objects/{oid}")
async def lfs_download(repo_name: str, oid: str):
    """流式返回 LFS 物件内容。"""
    chunks = lfs_store.read_chunks(oid)
    if chunks is None:
        raise HTTPException(404, f"LFS object {oid} not found")

    obj_size = lfs_store.size(oid)
    return StreamingResponse(
        chunks,
        media_type="application/octet-stream",
        headers={"Content-Length": str(obj_size)},
    )


# ---------- Verify 端点 ----------

@router.post("/{repo_name}.git/lfs/verify")
async def lfs_verify(
    repo_name: str,
    request: Request,
    authorization: str | None = Header(None),
):
    """上传后校验：客户端确认服务端已收到。"""
    authenticate(authorization)
    body = await request.json()
    oid = body.get("oid", "")
    expected_size = body.get("size", 0)

    if not lfs_store.exists(oid):
        raise HTTPException(404, f"LFS object {oid} not found")

    actual_size = lfs_store.size(oid)
    if actual_size != expected_size:
        raise HTTPException(
            422,
            f"Size mismatch: expected {expected_size}, got {actual_size}",
        )

    return Response(status_code=200)
