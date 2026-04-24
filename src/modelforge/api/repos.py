"""仓库管理 REST API。

- POST   /api/v1/repos                  创建仓库
- GET    /api/v1/repos                  列表
- GET    /api/v1/repos/search           按 Model Card 字段搜索
- GET    /api/v1/repos/{namespace}/{name}    详情
- DELETE /api/v1/repos/{namespace}/{name}    删除（仅 owner）

仓库名采用 `{namespace}/{name}` 两段格式（类似 Hugging Face）。
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from .. import db, storage
from ..auth import require_user

router = APIRouter(prefix="/api/v1/repos", tags=["repos"])


class CreateRepoRequest(BaseModel):
    namespace: str = Field(..., description="命名空间（如 amazon / jiangsu）")
    name: str = Field(..., description="仓库名，符合 [A-Za-z0-9][A-Za-z0-9._-]{0,63}")
    is_private: bool = False


class RepoResponse(BaseModel):
    namespace: str
    name: str
    full_name: str  # "{namespace}/{name}"
    owner: str
    is_private: bool
    created_at: str
    git_url: str


class RepoSearchResult(BaseModel):
    namespace: str
    name: str
    full_name: str
    owner: str
    library_name: str | None = None
    pipeline_tag: str | None = None
    license: str | None = None
    tags: list[str] = []
    base_model: str | None = None
    best_metric_name: str | None = None
    best_metric_value: float | None = None
    revision: str | None = None
    updated_at: str | None = None
    repo_type: str = "model"
    data_format: str | None = None


def _to_response(repo: db.Repo, base_url: str = "") -> RepoResponse:
    owner = db.get_user_by_id(repo.owner_id)
    full = repo.full_name
    return RepoResponse(
        namespace=repo.namespace,
        name=repo.name,
        full_name=full,
        owner=owner.name if owner else "<unknown>",
        is_private=repo.is_private,
        created_at=repo.created_at,
        git_url=f"{base_url}/{full}.git" if base_url else f"/{full}.git",
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=RepoResponse)
def create_repo(req: CreateRepoRequest, user: db.User = Depends(require_user)):
    if db.get_repo(req.namespace, req.name):
        raise HTTPException(409, f"Repository '{req.namespace}/{req.name}' already exists")
    try:
        storage.validate_repo_name(req.namespace, req.name)
        storage.create_bare_repo(req.namespace, req.name)
    except storage.RepoStorageError as e:
        raise HTTPException(400, str(e))
    repo = db.create_repo(req.namespace, req.name, owner_id=user.id, is_private=req.is_private)
    return _to_response(repo)


@router.get("", response_model=list[RepoResponse])
def list_repos():
    return [_to_response(r) for r in db.list_repos()]


@router.get("/search", response_model=list[RepoSearchResult])
def search_repos(
    library: str | None = Query(None, description="精确匹配 library_name，如 'lightgbm'"),
    pipeline_tag: str | None = Query(None, description="精确匹配 pipeline_tag"),
    license: str | None = Query(None, description="精确匹配 license"),
    tag: str | None = Query(None, description="tags 中包含该 tag"),
    metric: str | None = Query(None, description="限定指标名（如 'mape'）"),
    max_metric: float | None = Query(None, description="best_metric_value <= max_metric"),
    repo_type: str | None = Query(None, description="model | dataset"),
    data_format: str | None = Query(None, description="csv | image_folder | parquet | coco_json"),
    limit: int = Query(100, ge=1, le=500),
):
    """按 Model Card 字段组合搜索。

    例：/api/v1/repos/search?library=lightgbm&metric=mape&max_metric=4.0
    """
    pairs = db.search_repos(
        library_name=library,
        pipeline_tag=pipeline_tag,
        license_=license,
        tag=tag,
        max_metric=max_metric,
        metric_name=metric,
        repo_type=repo_type,
        data_format=data_format,
        limit=limit,
    )
    out: list[RepoSearchResult] = []
    for repo, card in pairs:
        owner = db.get_user_by_id(repo.owner_id)
        tags = []
        if card and card.tags_json:
            try:
                tags = json.loads(card.tags_json)
            except json.JSONDecodeError:
                tags = []
        out.append(RepoSearchResult(
            namespace=repo.namespace,
            name=repo.name,
            full_name=repo.full_name,
            owner=owner.name if owner else "<unknown>",
            library_name=card.library_name if card else None,
            pipeline_tag=card.pipeline_tag if card else None,
            license=card.license if card else None,
            tags=tags,
            base_model=card.base_model if card else None,
            best_metric_name=card.best_metric_name if card else None,
            best_metric_value=card.best_metric_value if card else None,
            revision=card.revision if card else None,
            updated_at=card.updated_at if card else None,
            repo_type=card.repo_type if card else "model",
            data_format=card.data_format if card else None,
        ))
    return out


@router.get("/{namespace}/{name}", response_model=RepoResponse)
def get_repo(namespace: str, name: str):
    repo = db.get_repo(namespace, name)
    if not repo:
        raise HTTPException(404, f"Repository '{namespace}/{name}' not found")
    return _to_response(repo)


@router.delete("/{namespace}/{name}", status_code=status.HTTP_204_NO_CONTENT)
def delete_repo(namespace: str, name: str, user: db.User = Depends(require_user)):
    repo = db.get_repo(namespace, name)
    if not repo:
        raise HTTPException(404, f"Repository '{namespace}/{name}' not found")
    if repo.owner_id != user.id:
        raise HTTPException(403, "Only the owner can delete this repository")
    db.delete_repo(namespace, name)
    storage.delete_bare_repo(namespace, name)


@router.delete("/{namespace}/{name}/force", status_code=status.HTTP_204_NO_CONTENT)
def force_delete_repo(namespace: str, name: str):
    """无认证删除（内网简化）。前端确认后直接调用。"""
    repo = db.get_repo(namespace, name)
    if not repo:
        raise HTTPException(404, f"Repository '{namespace}/{name}' not found")
    db.delete_repo(namespace, name)
    storage.delete_bare_repo(namespace, name)
