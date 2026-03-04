from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from modelforge import __version__
from modelforge.api.deployment import router as deployment_router
from modelforge.api.features import router as features_router
from modelforge.api.monitoring import router as monitoring_router
from modelforge.api.parameters import router as parameters_router
from modelforge.api.registry import router as registry_router
from modelforge.config import settings
from modelforge.services.inference import inference_manager
from modelforge.store import get_store

WEB_DIR = Path(__file__).parent / "web"


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_store()  # initialize store directories
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=__version__,
    description="AI Model Sharing Center for Power Industry - 电力行业人工智能模型全网共享中心",
    lifespan=lifespan,
)


app.include_router(registry_router, prefix=settings.API_V1_PREFIX)
app.include_router(features_router, prefix=settings.API_V1_PREFIX)
app.include_router(parameters_router, prefix=settings.API_V1_PREFIX)
app.include_router(deployment_router, prefix=settings.API_V1_PREFIX)
app.include_router(monitoring_router, prefix=settings.API_V1_PREFIX)

class NoCacheStaticMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        if request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-cache, must-revalidate"
        return response


app.add_middleware(NoCacheStaticMiddleware)
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


@app.get("/", include_in_schema=False)
def root():
    return FileResponse(WEB_DIR / "index.html")


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "version": __version__,
        "active_deployments": inference_manager.active_count,
    }
