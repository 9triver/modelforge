"""Web UI 用的预览 API：聚合 README、文件树、refs、facets。

前端 SPA 调用这些端点渲染列表页和详情页。Git/LFS 不变；这里只服务"读"。
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException
from markdown_it import MarkdownIt
from pydantic import BaseModel

from .. import db, repo_reader
from ..schema import ModelCardError, parse_frontmatter

router = APIRouter(prefix="/api/v1", tags=["preview"])

_md = MarkdownIt("commonmark", {"html": False, "linkify": True}).enable("table")


def _human_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    size = float(n)
    for unit in ("KB", "MB", "GB", "TB"):
        size /= 1024
        if size < 1024:
            return f"{size:.1f} {unit}"
    return f"{size:.1f} PB"


def _flatten_model_index(model_index: list | None) -> list[dict]:
    rows: list[dict] = []
    if not model_index:
        return rows
    for entry in model_index:
        for result in entry.get("results", []):
            task = (result.get("task") or {}).get("name") or (result.get("task") or {}).get("type", "")
            dataset = (result.get("dataset") or {}).get("name", "")
            for m in result.get("metrics") or []:
                rows.append({
                    "task": task,
                    "dataset": dataset,
                    "metric": m.get("name") or m.get("type", ""),
                    "value": m.get("value", ""),
                })
    return rows


class FileItem(BaseModel):
    path: str
    size: int
    size_human: str
    is_lfs: bool


class PreviewResponse(BaseModel):
    namespace: str
    name: str
    full_name: str
    owner: str
    revision: str
    has_commits: bool
    metadata: dict[str, Any] | None = None
    body_html: str | None = None
    body_error: str | None = None
    model_index: list[dict] = []
    files: list[FileItem] = []
    refs: dict[str, list[str]] = {"branches": [], "tags": []}


@router.get("/repos/{namespace}/{name}/preview", response_model=PreviewResponse)
def repo_preview(namespace: str, name: str, revision: str = "main"):
    repo_row = db.get_repo(namespace, name)
    if not repo_row:
        raise HTTPException(404, f"Repository '{namespace}/{name}' not found")
    owner = db.get_user_by_id(repo_row.owner_id)

    has_commits = repo_reader.has_any_commits(namespace, name)
    metadata: dict | None = None
    body_html: str | None = None
    body_error: str | None = None
    model_index: list[dict] = []
    files: list[FileItem] = []
    refs = {"branches": [], "tags": []}

    if not has_commits:
        body_error = "仓库为空，尚未推送任何内容"
    else:
        readme = repo_reader.read_file(namespace, name, revision, "README.md")
        if readme is None:
            body_error = f"在 revision '{revision}' 下未找到 README.md"
        else:
            try:
                metadata, body = parse_frontmatter(readme)
                model_index = _flatten_model_index(metadata.get("model-index"))
                body_html = _md.render(body)
            except ModelCardError as e:
                body_error = str(e)

        for f in repo_reader.list_files(namespace, name, revision):
            files.append(FileItem(
                path=f.path,
                size=f.size,
                size_human=_human_size(f.size),
                is_lfs=f.is_lfs,
            ))
        refs = repo_reader.list_refs(namespace, name)

    return PreviewResponse(
        namespace=namespace,
        name=name,
        full_name=repo_row.full_name,
        owner=owner.name if owner else "<unknown>",
        revision=revision,
        has_commits=has_commits,
        metadata=metadata,
        body_html=body_html,
        body_error=body_error,
        model_index=model_index,
        files=files,
        refs=refs,
    )


class FacetsResponse(BaseModel):
    libraries: list[str]
    tasks: list[str]
    licenses: list[str]
    tags: list[str]


@router.get("/facets", response_model=FacetsResponse)
def facets():
    pairs = db.search_repos(limit=500)
    libraries: set[str] = set()
    tasks: set[str] = set()
    licenses: set[str] = set()
    tags: set[str] = set()
    for _repo, card in pairs:
        if not card:
            continue
        if card.library_name:
            libraries.add(card.library_name)
        if card.pipeline_tag:
            tasks.add(card.pipeline_tag)
        if card.license:
            licenses.add(card.license)
        if card.tags_json:
            try:
                for t in json.loads(card.tags_json):
                    tags.add(t)
            except json.JSONDecodeError:
                pass
    return FacetsResponse(
        libraries=sorted(libraries),
        tasks=sorted(tasks),
        licenses=sorted(licenses),
        tags=sorted(tags),
    )
