"""FastAPI 应用工厂。"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import __version__
from .api import calibrations, download, evaluations, git_routes, lfs_routes, preview, repos, transfers
from .config import get_settings

STATIC_DIR = Path(__file__).parent / "static"


class SPAStaticFiles(StaticFiles):
    """StaticFiles 变体：文件不存在时回退到 index.html，支持 react-router 动态路径。

    Git/LFS/API 路由已提前注册，这里只处理前端页面的 404。
    """

    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as e:
            if e.status_code == 404:
                index = Path(self.directory) / "index.html"
                if index.is_file():
                    return FileResponse(index)
            raise


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

    # API 与 Git/LFS 必须先注册（SPAStaticFiles 挂在 / 上会兜底所有路径）
    app.include_router(repos.router)
    app.include_router(preview.router)
    app.include_router(evaluations.router)
    app.include_router(calibrations.router)
    app.include_router(transfers.router)
    app.include_router(download.router)
    app.include_router(lfs_routes.router)
    app.include_router(git_routes.router)

    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    if not (STATIC_DIR / "index.html").exists():
        # 占位：未构建前端时给个提示页
        (STATIC_DIR / "index.html").write_text(
            "<!doctype html><meta charset=utf-8><title>ModelForge</title>"
            "<h1>ModelForge</h1>"
            "<p>前端尚未构建。运行 <code>cd web && pnpm install && pnpm build</code>。</p>"
            "<p><a href='/api/v1/repos'>API: /api/v1/repos</a> · "
            "<a href='/docs'>Swagger: /docs</a></p>",
            encoding="utf-8",
        )
    app.mount("/", SPAStaticFiles(directory=STATIC_DIR, html=True), name="ui")

    return app


# 模块级 app，便于 `uvicorn modelforge.server:app`
app = create_app()

