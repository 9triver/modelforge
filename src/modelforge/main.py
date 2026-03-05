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
from modelforge.api.deployment import predict_router, router as deployment_router
from modelforge.api.evaluation import router as evaluation_router
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
    store = get_store()
    # Mark any stale runs (pending/running from previous server) as failed
    _cleanup_stale_runs(store)
    yield


def _cleanup_stale_runs(store):
    """Handle runs stuck in pending/running after server restart.

    - If the training subprocess completed (metrics.json exists),
      recover by creating the version record automatically.
    - If the subprocess is still alive, leave the run alone.
    - Otherwise mark as failed and clean up incomplete artifacts.
    """
    import json as _json
    import os
    import shutil
    from datetime import datetime, timezone

    from modelforge.store import YAMLFile

    if not store.models_dir.exists():
        return
    for model_dir in store.models_dir.iterdir():
        if not model_dir.is_dir():
            continue
        runs_dir = model_dir / "runs"
        if not runs_dir.exists():
            continue
        slug = model_dir.name
        for run_file in runs_dir.iterdir():
            if run_file.suffix != ".yaml":
                continue
            data = YAMLFile.read(run_file)
            status = data.get("status")
            tv = data.get("target_version")

            # Recover runs previously wrongly marked failed
            if (
                status == "failed"
                and data.get("error")
                    == "Server restarted during execution"
                and tv
            ):
                vdir = model_dir / "versions" / tv
                has_metrics = (vdir / "metrics.json").exists()
                no_version = not (vdir / "version.yaml").exists()
                if has_metrics and no_version:
                    _recover_run(
                        store, data, slug, vdir, run_file,
                        _json, datetime, timezone,
                    )
                continue

            if status not in ("pending", "running"):
                continue

            # If subprocess is still alive, skip
            pid = data.get("pid")
            if pid:
                try:
                    os.kill(pid, 0)
                    continue  # still running
                except (OSError, ProcessLookupError):
                    pass

            # Check if training actually completed
            if tv and status == "running":
                vdir = model_dir / "versions" / tv
                if (vdir / "metrics.json").exists():
                    _recover_run(
                        store, data, slug, vdir, run_file,
                        _json, datetime, timezone,
                    )
                    continue

            # Truly failed — mark and clean up
            data["status"] = "failed"
            data["error"] = "Server restarted during execution"
            data["finished_at"] = datetime.now(
                timezone.utc,
            ).isoformat()
            YAMLFile.write(run_file, data)
            if tv:
                vdir = model_dir / "versions" / tv
                if vdir.exists():
                    if not (vdir / "version.yaml").exists():
                        shutil.rmtree(vdir, ignore_errors=True)


def _recover_run(store, data, slug, vdir, run_file,
                 _json, datetime, timezone):
    """Recover a run whose training completed but thread died."""
    from modelforge.store import YAMLFile

    model_id = data["model_id"]
    tv = data["target_version"]
    tv_display = tv.lstrip("v") if tv else tv
    bv = data.get("base_version", "")
    pipeline = data.get("pipeline_snapshot", {})

    metrics = None
    mf = vdir / "metrics.json"
    if mf.exists():
        with open(mf) as f:
            metrics = _json.load(f)

    weights_path = None
    wd = vdir / "weights"
    if wd.exists():
        for fp in wd.iterdir():
            if fp.is_file() and not fp.name.startswith("."):
                weights_path = fp
                break

    file_size = weights_path.stat().st_size if weights_path else 0
    parent_id = store.get_version_id_by_str(slug, bv)

    vdata = store.create_version_from_run(
        model_id, slug, tv, vdir,
        metrics=metrics,
        file_format=pipeline.get(
            "output", {},
        ).get("format", "joblib"),
        file_size=file_size,
        weights_rel=(
            str(weights_path.relative_to(vdir))
            if weights_path else None
        ),
        parent_version_id=parent_id,
    )

    log = data.get("log", "")
    log += (
        "\n[恢复] 训练已完成但服务器重启导致记录中断，已自动恢复"
        f"\n[完成] 已创建新版本 {tv} (id={vdata['id']})"
    )

    now = datetime.now(timezone.utc).isoformat()
    data.update({
        "status": "success",
        "finished_at": now,
        "result_version_id": vdata["id"],
        "result_version": tv_display,
        "metrics": metrics,
        "log": log,
    })
    YAMLFile.write(run_file, data)


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
app.include_router(predict_router, prefix=settings.API_V1_PREFIX)
app.include_router(monitoring_router, prefix=settings.API_V1_PREFIX)
app.include_router(evaluation_router, prefix=settings.API_V1_PREFIX)

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
