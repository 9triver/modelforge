"""ModelForge 只读 Web UI：模型列表 + 详情。

路由：
  GET  /                    首页（所有仓库列表，带元数据预览）
  GET  /{repo_name}         详情（Model Card 元数据表 + 渲染后的 README body + 文件清单）

Markdown 用 markdown-it-py 渲染；YAML frontmatter 复用 schema.parse_frontmatter。
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from markdown_it import MarkdownIt

from . import __version__, db, repo_reader
from .schema import ModelCardError, parse_frontmatter

router = APIRouter(tags=["web"])

_TEMPLATE_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATE_DIR))

_md = MarkdownIt("commonmark", {"html": False, "linkify": True}).enable("table")


def _human_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    for unit in ("KB", "MB", "GB", "TB"):
        n /= 1024
        if n < 1024:
            return f"{n:.1f} {unit}"
    return f"{n:.1f} PB"


def _get_repo_preview(repo_name: str) -> dict:
    """尝试读 README.md 并解析 frontmatter。出错返回 error 字段。"""
    if not repo_reader.has_any_commits(repo_name):
        return {"metadata": None, "error": None}
    readme = repo_reader.read_file(repo_name, "HEAD", "README.md")
    if readme is None:
        return {"metadata": None, "error": "README.md 缺失"}
    try:
        metadata, _ = parse_frontmatter(readme)
        return {"metadata": metadata, "error": None}
    except ModelCardError as e:
        return {"metadata": None, "error": str(e).split("\n")[0]}


def _flatten_model_index(model_index: list | None) -> list[dict]:
    """把 HF model-index 的嵌套结构铺平成表格行。"""
    rows = []
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


# ---------- / 首页 ----------

@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    repos_raw = db.list_repos()
    repos = []
    for r in repos_raw:
        owner = db.get_user_by_id(r.owner_id)
        preview = _get_repo_preview(r.name)
        repos.append({
            "name": r.name,
            "owner": owner.name if owner else "<unknown>",
            "is_private": r.is_private,
            "created_at": r.created_at,
            "metadata": preview["metadata"],
            "error": preview["error"],
        })

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"repos": repos, "version": __version__},
    )


# ---------- /{repo_name} 详情 ----------

@router.get("/{repo_name}", response_class=HTMLResponse)
def repo_detail(request: Request, repo_name: str, revision: str = "main"):
    # 排除已被其他路由处理的路径
    if repo_name in ("healthz", "version", "docs", "redoc", "openapi.json"):
        raise HTTPException(404)

    repo_row = db.get_repo(repo_name)
    if not repo_row:
        raise HTTPException(404, f"Repository '{repo_name}' not found")
    owner = db.get_user_by_id(repo_row.owner_id)

    # 读取 Model Card
    metadata = None
    body_html = None
    body_error = None
    model_index_rows: list[dict] = []
    if not repo_reader.has_any_commits(repo_name):
        body_error = "仓库为空，尚未推送任何内容"
    else:
        readme = repo_reader.read_file(repo_name, revision, "README.md")
        if readme is None:
            body_error = f"在 revision '{revision}' 下未找到 README.md"
        else:
            try:
                metadata, body = parse_frontmatter(readme)
                model_index_rows = _flatten_model_index(metadata.get("model-index"))
                body_html = _md.render(body)
            except ModelCardError as e:
                body_error = str(e)

    # 文件清单
    files = []
    if repo_reader.has_any_commits(repo_name):
        for f in repo_reader.list_files(repo_name, revision):
            files.append({
                "path": f.path,
                "is_lfs": f.is_lfs,
                "size_human": _human_size(f.size),
            })

    # Git URL（用户拷贝粘贴）
    host = request.headers.get("host", "localhost")
    scheme = request.url.scheme
    git_url = f"{scheme}://{host}/{repo_name}.git"

    return templates.TemplateResponse(
        request=request,
        name="repo.html",
        context={
            "version": __version__,
            "revision": revision,
            "git_url": git_url,
            "repo": {
                "name": repo_name,
                "owner": owner.name if owner else "<unknown>",
                "created_at": repo_row.created_at,
            },
            "metadata": metadata,
            "model_index": model_index_rows,
            "body_html": body_html,
            "body_error": body_error,
            "files": files,
        },
    )
