"""Workspace API：创建、查状态、停止、重启 + 反向代理到 code-server。

POST /api/v1/workspaces              创建
GET  /api/v1/workspaces              列出
GET  /api/v1/workspaces/{id}         查状态
POST /api/v1/workspaces/{id}/stop    停止
POST /api/v1/workspaces/{id}/restart 重启
/workspaces/{id}/{path}              反向代理到 code-server
"""
from __future__ import annotations

import asyncio

import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request, WebSocket
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .. import db
from ..services import workspace as ws_svc
from ..storage import RepoStorageError

router = APIRouter(tags=["workspaces"])


# ---------- request / response models ----------

class WorkspaceCreateRequest(BaseModel):
    namespace: str
    name: str
    models: list[str] = []
    datasets: list[str] = []


class WorkspaceCreated(BaseModel):
    workspace_id: int
    status: str


class WorkspaceStatus(BaseModel):
    id: int
    repo: str
    models: list[str]
    datasets: list[str]
    status: str
    url: str | None = None
    error: str | None = None
    created_at: str


def _ws_to_status(ws: db.Workspace) -> WorkspaceStatus:
    repo_name = db.get_repo_name(ws.repo_id) or ""
    models: list[str] = []
    datasets: list[str] = []
    try:
        from .. import repo_reader
        ns, nm = repo_name.split("/", 1) if "/" in repo_name else ("", "")
        if ns:
            content = repo_reader.read_file(ns, nm, "main", ".gitmodules")
            if content:
                models, datasets = ws_svc.parse_gitmodules(content)
    except Exception:
        pass

    return WorkspaceStatus(
        id=ws.id,
        repo=repo_name,
        models=models,
        datasets=datasets,
        status=ws.status,
        url=f"/workspaces/{ws.id}/" if ws.status == "running" else None,
        error=ws.error,
        created_at=ws.created_at,
    )


# ---------- CRUD endpoints ----------

@router.post("/api/v1/workspaces", status_code=202, response_model=WorkspaceCreated)
def create_workspace(req: WorkspaceCreateRequest, bg: BackgroundTasks):
    for m in req.models:
        if "/" not in m:
            raise HTTPException(400, f"Invalid model repo: {m}")
        ns, nm = m.split("/", 1)
        if not db.get_repo(ns, nm):
            raise HTTPException(404, f"Model repo not found: {m}")
    for d in req.datasets:
        if "/" not in d:
            raise HTTPException(400, f"Invalid dataset repo: {d}")
        ns, nm = d.split("/", 1)
        if not db.get_repo(ns, nm):
            raise HTTPException(404, f"Dataset repo not found: {d}")

    try:
        ws_id = ws_svc.create_workspace(
            namespace=req.namespace,
            name=req.name,
            models=req.models,
            datasets=req.datasets,
        )
    except RepoStorageError as e:
        raise HTTPException(409, str(e))

    bg.add_task(ws_svc.launch_workspace, ws_id)
    return WorkspaceCreated(workspace_id=ws_id, status="creating")


@router.get("/api/v1/workspaces", response_model=list[WorkspaceStatus])
def list_workspaces(status: str | None = Query(None), repo: str | None = Query(None)):
    if repo and "/" in repo:
        ns, nm = repo.split("/", 1)
        r = db.get_repo(ns, nm)
        if not r:
            return []
        ws = db.get_workspace_by_repo(r.id)
        if not ws:
            return []
        if status and ws.status != status:
            return []
        return [_ws_to_status(ws)]
    wss = db.list_workspaces(status=status)
    return [_ws_to_status(ws) for ws in wss]


@router.get("/api/v1/workspaces/{workspace_id}", response_model=WorkspaceStatus)
def get_workspace(workspace_id: int):
    ws = db.get_workspace(workspace_id)
    if not ws:
        raise HTTPException(404, "Workspace not found")
    return _ws_to_status(ws)


@router.post("/api/v1/workspaces/{workspace_id}/stop")
def stop_workspace(workspace_id: int, bg: BackgroundTasks):
    ws = db.get_workspace(workspace_id)
    if not ws:
        raise HTTPException(404, "Workspace not found")
    if ws.status != "running":
        raise HTTPException(400, f"Workspace is not running (status={ws.status})")
    bg.add_task(ws_svc.stop_workspace, workspace_id)
    return {"status": "stopping"}


@router.post("/api/v1/workspaces/{workspace_id}/restart")
def restart_workspace(workspace_id: int, bg: BackgroundTasks):
    ws = db.get_workspace(workspace_id)
    if not ws:
        raise HTTPException(404, "Workspace not found")
    if ws.status != "stopped":
        raise HTTPException(400, f"Workspace is not stopped (status={ws.status})")
    bg.add_task(ws_svc.restart_workspace, workspace_id)
    return {"status": "creating"}


# ---------- reverse proxy to code-server ----------

def _get_ws_port(workspace_id: int) -> int:
    ws = db.get_workspace(workspace_id)
    if not ws or ws.status != "running" or not ws.port:
        raise HTTPException(502, "Workspace is not running")
    return ws.port


@router.api_route(
    "/workspaces/{workspace_id}/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
)
async def proxy_http(workspace_id: int, path: str, request: Request):
    port = _get_ws_port(workspace_id)
    target = f"http://127.0.0.1:{port}/{path}"
    qs = str(request.url.query)
    if qs:
        target += "?" + qs

    async with httpx.AsyncClient(timeout=60.0) as client:
        body = await request.body()
        fwd = {
            k: v for k, v in request.headers.items()
            if k.lower() not in ("host", "accept-encoding")
        }
        upstream = await client.request(
            method=request.method,
            url=target,
            headers=fwd,
            content=body,
        )
        excluded = {"content-encoding", "content-length", "transfer-encoding", "vary"}
        resp_headers = {
            k: v for k, v in upstream.headers.items()
            if k.lower() not in excluded
        }
        return StreamingResponse(
            content=iter([upstream.content]),
            status_code=upstream.status_code,
            headers=resp_headers,
        )


@router.websocket("/workspaces/{workspace_id}/{path:path}")
async def proxy_ws(workspace_id: int, path: str, websocket: WebSocket):
    port = _get_ws_port(workspace_id)
    target = f"ws://127.0.0.1:{port}/{path}"
    qs = str(websocket.url.query)
    if qs:
        target += "?" + qs

    await websocket.accept()

    try:
        import websockets
        async with websockets.connect(target) as upstream:
            async def client_to_upstream():
                try:
                    while True:
                        data = await websocket.receive_bytes()
                        await upstream.send(data)
                except Exception:
                    pass

            async def upstream_to_client():
                try:
                    async for msg in upstream:
                        if isinstance(msg, bytes):
                            await websocket.send_bytes(msg)
                        else:
                            await websocket.send_text(msg)
                except Exception:
                    pass

            await asyncio.gather(client_to_upstream(), upstream_to_client())
    except Exception:
        pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
