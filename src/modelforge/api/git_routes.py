"""Git Smart HTTP 协议支持：把请求代理给 git-http-backend CGI。

实现的端点（Git 标准）：
- GET  /{repo}.git/info/refs?service=git-upload-pack      # clone/fetch 握手
- GET  /{repo}.git/info/refs?service=git-receive-pack     # push 握手
- POST /{repo}.git/git-upload-pack                        # fetch 数据流
- POST /{repo}.git/git-receive-pack                       # push 数据流

前两个走"读"权限；push 的两个端点要求认证通过的用户。

流式传输：HTTP body 通过 asyncio 流式写入 subprocess stdin，
subprocess stdout 流式读出作为 StreamingResponse 返回，
避免大仓库 push/clone 时整个 pack 文件驻留内存。
"""
from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from functools import lru_cache
from typing import AsyncIterator, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response, StreamingResponse

from .. import db, storage
from ..auth import authenticate
from ..config import get_settings

router = APIRouter(tags=["git"])

PIPE_CHUNK = 64 * 1024  # 64 KB


@lru_cache
def _resolve_git_http_backend() -> str:
    """优先用配置；为空则向 `git --exec-path` 询问。"""
    configured = get_settings().git_http_backend_path
    if configured:
        return configured
    found = shutil.which("git-http-backend")
    if found:
        return found
    try:
        exec_path = subprocess.check_output(
            [get_settings().git_path, "--exec-path"], text=True,
        ).strip()
        candidate = os.path.join(exec_path, "git-http-backend")
        if os.path.exists(candidate):
            return candidate
    except Exception:
        pass
    raise RuntimeError(
        "Cannot locate git-http-backend. "
        "Set MODELFORGE_GIT_HTTP_BACKEND_PATH to the absolute path."
    )


def _require_write_auth(authorization: str | None) -> db.User:
    return authenticate(authorization)


def _ensure_repo(name: str) -> None:
    repo = db.get_repo(name)
    if not repo:
        raise HTTPException(404, f"Repository '{name}' not found")
    if not storage.repo_exists_on_disk(name):
        raise HTTPException(500, f"Repository '{name}' metadata exists but directory missing")


def _parse_cgi_headers(raw: bytes) -> tuple[int, dict[str, str], bytes]:
    """解析 CGI 输出的 header 部分，返回 (status_code, headers, 剩余 body 字节)。"""
    sep = b"\r\n\r\n"
    if sep not in raw:
        sep = b"\n\n"
    if sep not in raw:
        return 200, {}, raw

    header_block, rest = raw.split(sep, 1)
    status_code = 200
    headers: dict[str, str] = {}
    for line in header_block.decode("latin-1").split("\n"):
        line = line.rstrip("\r")
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key, value = key.strip(), value.strip()
        if key.lower() == "status":
            parts = value.split(" ", 1)
            status_code = int(parts[0])
        else:
            headers[key] = value
    return status_code, headers, rest


async def _run_git_http_backend_streaming(
    path_info: str,
    query_string: str,
    request_method: str,
    content_type: str,
    request_stream: AsyncIterator[bytes] | None,
    content_length: str = "",
) -> Response:
    """流式调用 git-http-backend CGI。

    stdin：从 request_stream 异步读取 chunk 写入 subprocess。
    stdout：先读 CGI header，然后流式返回 body。
    """
    settings = get_settings()

    env = {
        **os.environ,
        "GIT_PROJECT_ROOT": str(settings.repos_dir),
        "GIT_HTTP_EXPORT_ALL": "1",
        "PATH_INFO": path_info,
        "QUERY_STRING": query_string,
        "REQUEST_METHOD": request_method,
        "CONTENT_TYPE": content_type or "",
        "CONTENT_LENGTH": content_length,
        "REMOTE_USER": "modelforge",
    }

    proc = await asyncio.create_subprocess_exec(
        _resolve_git_http_backend(),
        env=env,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    # 流式写入 stdin
    if request_stream and proc.stdin:
        try:
            async for chunk in request_stream:
                proc.stdin.write(chunk)
                await proc.stdin.drain()
        finally:
            proc.stdin.close()
            await proc.stdin.wait_closed()
    elif proc.stdin:
        proc.stdin.close()
        await proc.stdin.wait_closed()

    # 读 CGI header（header 很小，先读到分隔符）
    header_buf = b""
    while proc.stdout:
        chunk = await proc.stdout.read(PIPE_CHUNK)
        if not chunk:
            break
        header_buf += chunk
        if b"\r\n\r\n" in header_buf or b"\n\n" in header_buf:
            break

    status_code, headers, first_body = _parse_cgi_headers(header_buf)

    if status_code >= 400:
        rest = await proc.stdout.read() if proc.stdout else b""
        await proc.wait()
        body = first_body + rest
        return Response(content=body, status_code=status_code, headers=headers)

    # 流式返回 body
    async def _stream_body():
        if first_body:
            yield first_body
        while proc.stdout:
            chunk = await proc.stdout.read(PIPE_CHUNK)
            if not chunk:
                break
            yield chunk
        await proc.wait()

    return StreamingResponse(
        _stream_body(),
        status_code=status_code,
        headers=headers,
    )


@router.get("/{repo_name}.git/info/refs")
async def git_info_refs(
    repo_name: str,
    request: Request,
    service: Optional[str] = None,
):
    _ensure_repo(repo_name)
    if service == "git-receive-pack":
        _require_write_auth(request.headers.get("authorization"))

    return await _run_git_http_backend_streaming(
        path_info=f"/{repo_name}.git/info/refs",
        query_string=f"service={service}" if service else "",
        request_method="GET",
        content_type=request.headers.get("content-type", ""),
        request_stream=None,
    )


@router.post("/{repo_name}.git/git-upload-pack")
async def git_upload_pack(repo_name: str, request: Request):
    _ensure_repo(repo_name)
    return await _run_git_http_backend_streaming(
        path_info=f"/{repo_name}.git/git-upload-pack",
        query_string="",
        request_method="POST",
        content_type=request.headers.get("content-type", "application/x-git-upload-pack-request"),
        request_stream=request.stream(),
        content_length=request.headers.get("content-length", ""),
    )


@router.post("/{repo_name}.git/git-receive-pack")
async def git_receive_pack(repo_name: str, request: Request):
    _ensure_repo(repo_name)
    _require_write_auth(request.headers.get("authorization"))

    return await _run_git_http_backend_streaming(
        path_info=f"/{repo_name}.git/git-receive-pack",
        query_string="",
        request_method="POST",
        content_type=request.headers.get("content-type", "application/x-git-receive-pack-request"),
        request_stream=request.stream(),
        content_length=request.headers.get("content-length", ""),
    )
