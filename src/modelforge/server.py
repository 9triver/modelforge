"""FastAPI 应用工厂。"""
from __future__ import annotations

from fastapi import FastAPI

from . import __version__, web
from .api import git_routes, lfs_routes, repos
from .config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="ModelForge",
        version=__version__,
        description="通用模型仓库服务（Git + LFS）",
    )

    @app.get("/healthz")
    def health():
        return {"status": "ok", "data_dir": str(settings.data_dir)}

    @app.get("/version")
    def version():
        return {"version": __version__}

    app.include_router(repos.router)
    app.include_router(lfs_routes.router)
    # Git 路由：路径模板 /{repo}.git/... （.git 后缀区分于 Web 路由）
    app.include_router(git_routes.router)
    # Web UI 路由放最后：/{repo_name} 单段路径，避开 /api、/healthz
    app.include_router(web.router)

    return app


# 模块级 app，便于 `uvicorn modelforge.server:app`
app = create_app()
