"""仓库管理 REST API。

- POST /api/v1/repos    创建仓库
- GET  /api/v1/repos    列表
- GET  /api/v1/repos/{name}  详情
- DELETE /api/v1/repos/{name}  删除（仅 owner）
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from .. import db, storage
from ..auth import require_user

router = APIRouter(prefix="/api/v1/repos", tags=["repos"])


class CreateRepoRequest(BaseModel):
    name: str = Field(..., description="仓库名，符合 [A-Za-z0-9][A-Za-z0-9._-]{0,63}")
    is_private: bool = False


class RepoResponse(BaseModel):
    name: str
    owner: str
    is_private: bool
    created_at: str
    git_url: str


def _to_response(repo: db.Repo, base_url: str = "") -> RepoResponse:
    owner = db.get_user_by_id(repo.owner_id)
    return RepoResponse(
        name=repo.name,
        owner=owner.name if owner else "<unknown>",
        is_private=repo.is_private,
        created_at=repo.created_at,
        git_url=f"{base_url}/{repo.name}.git" if base_url else f"/{repo.name}.git",
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=RepoResponse)
def create_repo(req: CreateRepoRequest, user: db.User = Depends(require_user)):
    if db.get_repo(req.name):
        raise HTTPException(409, f"Repository '{req.name}' already exists")
    try:
        storage.validate_repo_name(req.name)
        storage.create_bare_repo(req.name)
    except storage.RepoStorageError as e:
        raise HTTPException(400, str(e))
    repo = db.create_repo(req.name, owner_id=user.id, is_private=req.is_private)
    return _to_response(repo)


@router.get("", response_model=list[RepoResponse])
def list_repos():
    return [_to_response(r) for r in db.list_repos()]


@router.get("/{name}", response_model=RepoResponse)
def get_repo(name: str):
    repo = db.get_repo(name)
    if not repo:
        raise HTTPException(404, f"Repository '{name}' not found")
    return _to_response(repo)


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
def delete_repo(name: str, user: db.User = Depends(require_user)):
    repo = db.get_repo(name)
    if not repo:
        raise HTTPException(404, f"Repository '{name}' not found")
    if repo.owner_id != user.id:
        raise HTTPException(403, "Only the owner can delete this repository")
    db.delete_repo(name)
    storage.delete_bare_repo(name)
