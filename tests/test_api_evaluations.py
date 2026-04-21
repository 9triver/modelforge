"""End-to-end HTTP tests for the evaluate API."""
from __future__ import annotations

import subprocess
import time
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("pandas")
from fastapi.testclient import TestClient  # noqa: E402

from modelforge import config, db, storage  # noqa: E402
from modelforge.server import create_app  # noqa: E402


FORECASTING_README = """\
---
license: mit
library_name: dummy
pipeline_tag: time-series-forecasting
forecasting:
  target: load
  features:
    required: []
---

# Dummy forecast
"""

PERFECT_HANDLER = """\
import pandas as pd
from modelforge.runtime.tasks import ForecastingHandler

class Handler(ForecastingHandler):
    def predict(self, df):
        return pd.DataFrame({"timestamp": df["timestamp"], "prediction": df["load"]})
"""


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


def _push_repo(namespace: str, name: str, files: dict[str, str]) -> None:
    """建裸仓库 + work-tree 构造 commit + push 进去。"""
    # 去掉 pre-receive hook（测试环境不需要 modelforge CLI）
    storage.create_bare_repo(namespace, name)
    hook = storage.repo_path(namespace, name) / "hooks" / "pre-receive"
    if hook.exists():
        hook.unlink()

    workdir = Path(subprocess.check_output(["mktemp", "-d"], text=True).strip())
    try:
        _git(workdir, "init", "-q", "-b", "main")
        _git(workdir, "config", "user.email", "test@test")
        _git(workdir, "config", "user.name", "test")
        for rel, content in files.items():
            p = workdir / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
            _git(workdir, "add", rel)
        _git(workdir, "commit", "-q", "-m", "init")
        _git(workdir, "push", "-q", str(storage.repo_path(namespace, name)), "main")
    finally:
        subprocess.run(["rm", "-rf", str(workdir)], check=False)


@pytest.fixture
def client(tmp_path):
    config.reset_settings(data_dir=tmp_path)
    # create user + repo entry (pre-receive hook disabled above)
    user = db.create_user("tester")
    db.create_repo("ns", "m", owner_id=user.id)
    _push_repo("ns", "m", {
        "README.md": FORECASTING_README,
        "handler.py": PERFECT_HANDLER,
    })
    app = create_app()
    with TestClient(app) as c:
        yield c
    config.reset_settings()


CSV = (
    "timestamp,load\n"
    "2024-01-01 00:00,10\n"
    "2024-01-01 01:00,20\n"
    "2024-01-01 02:00,30\n"
)


class TestEvaluateEndpoint:
    def test_full_flow(self, client: "TestClient"):
        # POST: 上传数据
        r = client.post(
            "/api/v1/repos/ns/m/evaluate",
            files={"dataset": ("data.csv", CSV, "text/csv")},
        )
        assert r.status_code == 202, r.text
        eval_id = r.json()["evaluation_id"]
        assert r.json()["status"] == "queued"

        # 轮询状态直到完成
        for _ in range(50):
            s = client.get(f"/api/v1/evaluations/{eval_id}").json()
            if s["status"] in {"ok", "error"}:
                break
            time.sleep(0.05)

        assert s["status"] == "ok", s
        assert s["primary_metric"] == "mape"
        assert s["primary_value"] == 0.0
        assert s["task"] == "time-series-forecasting"
        assert s["metrics"]["mae"] == 0.0
        assert s["repo"] == "ns/m"

        # 聚合接口能看到这条
        agg = client.get("/api/v1/repos/ns/m/metrics").json()
        assert agg["count"] == 1
        assert agg["metric"] == "mape"
        assert agg["median"] == 0.0

    def test_unknown_repo(self, client: "TestClient"):
        r = client.post(
            "/api/v1/repos/nope/nope/evaluate",
            files={"dataset": ("x.csv", "a,b\n1,2\n", "text/csv")},
        )
        assert r.status_code == 404

    def test_evaluation_not_found(self, client: "TestClient"):
        r = client.get("/api/v1/evaluations/99999")
        assert r.status_code == 404

    def test_aggregate_empty(self, client: "TestClient"):
        r = client.get("/api/v1/repos/ns/m/metrics")
        assert r.status_code == 200
        assert r.json()["count"] == 0
