"""Git Smart HTTP 协议支持：把请求代理给 git-http-backend CGI。

实现的端点（Git 标准）：
- GET  /{repo}.git/info/refs?service=git-upload-pack      # clone/fetch 握手
- GET  /{repo}.git/info/refs?service=git-receive-pack     # push 握手
- POST /{repo}.git/git-upload-pack                        # fetch 数据流
- POST /{repo}.git/git-receive-pack                       # push 数据流

前两个走"读"权限；push 的两个端点要求认证通过的用户。
"""
from __future__ import annotations

import os
import shutil
import subprocess
from functools import lru_cache
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Response

from .. import db, storage
from ..auth import authenticate
from ..config import get_settings

router = APIRouter(tags=["git"])


@lru_cache
def _resolve_git_http_backend() -> str:
    """优先用配置；为空则向 `git --exec-path` 询问。"""
    configured = get_settings().git_http_backend_path
    if configured:
        return configured
    found = shutil.which("git-http-backend")
    if found:
        return found
    # macOS 通常装在 `git --exec-path` 目录里
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
    """写操作（receive-pack）必须认证。"""
    return authenticate(authorization)


def _ensure_repo(name: str) -> None:
    repo = db.get_repo(name)
    if not repo:
        raise HTTPException(404, f"Repository '{name}' not found")
    if not storage.repo_exists_on_disk(name):
        raise HTTPException(500, f"Repository '{name}' metadata exists but directory missing")


async def _run_git_http_backend(
    path_info: str,
    query_string: str,
    request_method: str,
    content_type: str,
    body: bytes,
) -> Response:
    """调用 git-http-backend CGI。

    git-http-backend 是 Git 自带的 CGI 程序，按 CGI 规范读写标准输入输出。
    我们的 FastAPI 应用把 HTTP 请求翻译成 CGI 环境变量 + stdin，
    然后把 CGI 输出解析回 HTTP 响应。
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
        "CONTENT_LENGTH": str(len(body)),
        # 允许 git push 通过 HTTP
        "REMOTE_USER": "modelforge",
    }

    proc = subprocess.Popen(
        [_resolve_git_http_backend()],
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout, stderr = proc.communicate(input=body)

    if proc.returncode != 0:
        raise HTTPException(
            500,
            f"git-http-backend exited {proc.returncode}: {stderr.decode('utf-8', errors='replace')}",
        )

    # 解析 CGI 输出：headers 与 body 以空行分隔
    sep = b"\r\n\r\n"
    if sep not in stdout:
        sep = b"\n\n"
    if sep not in stdout:
        raise HTTPException(500, "Malformed CGI response (no header/body separator)")

    header_block, body_bytes = stdout.split(sep, 1)

    status_code = 200
    headers: dict[str, str] = {}
    for line in header_block.decode("latin-1").split("\n"):
        line = line.rstrip("\r")
        if not line:
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if key.lower() == "status":
            # 形如 "404 Not Found"
            parts = value.split(" ", 1)
            status_code = int(parts[0])
        else:
            headers[key] = value

    return Response(content=body_bytes, status_code=status_code, headers=headers)


@router.get("/{repo_name}.git/info/refs")
async def git_info_refs(
    repo_name: str,
    request: Request,
    service: Optional[str] = None,
):
    """Git 握手：clone/fetch/push 首个请求。

    - service=git-upload-pack 是拉（读）
    - service=git-receive-pack 是推（写，需要认证）
    """
    _ensure_repo(repo_name)

    if service == "git-receive-pack":
        _require_write_auth(request.headers.get("authorization"))

    return await _run_git_http_backend(
        path_info=f"/{repo_name}.git/info/refs",
        query_string=f"service={service}" if service else "",
        request_method="GET",
        content_type=request.headers.get("content-type", ""),
        body=b"",
    )


@router.post("/{repo_name}.git/git-upload-pack")
async def git_upload_pack(repo_name: str, request: Request):
    """客户端拉取数据流（clone / fetch）。"""
    _ensure_repo(repo_name)
    body = await request.body()
    return await _run_git_http_backend(
        path_info=f"/{repo_name}.git/git-upload-pack",
        query_string="",
        request_method="POST",
        content_type=request.headers.get("content-type", "application/x-git-upload-pack-request"),
        body=body,
    )


@router.post("/{repo_name}.git/git-receive-pack")
async def git_receive_pack(repo_name: str, request: Request):
    """客户端推送数据流（push）——需要认证。"""
    _ensure_repo(repo_name)
    _require_write_auth(request.headers.get("authorization"))

    body = await request.body()
    return await _run_git_http_backend(
        path_info=f"/{repo_name}.git/git-receive-pack",
        query_string="",
        request_method="POST",
        content_type=request.headers.get("content-type", "application/x-git-receive-pack-request"),
        body=body,
    )
