import io
import json
import time


def _create_model(client, **overrides):
    data = {
        "name": "华东短期负荷预测模型",
        "description": "基于梯度提升回归的短期电力负荷预测模型",
        "task_type": "load_forecast",
        "algorithm_type": "GradientBoosting",
        "framework": "sklearn",
        "owner_org": "华东省公司",
        "tags": ["load_forecast", "short_term"],
        "applicable_scenarios": {"region": ["华东"], "season": ["all"]},
    }
    data.update(overrides)
    return client.post("/api/v1/models", json=data)


def test_create_model(client):
    resp = _create_model(client)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "华东短期负荷预测模型"
    assert data["status"] == "draft"
    assert data["task_type"] == "load_forecast"
    assert data["version_count"] == 0


def test_create_duplicate_model(client):
    _create_model(client)
    resp = _create_model(client)
    assert resp.status_code == 409


def test_list_models(client):
    _create_model(client, name="模型A")
    _create_model(client, name="模型B", task_type="anomaly_detection")

    resp = client.get("/api/v1/models")
    assert resp.status_code == 200
    assert len(resp.json()) == 2

    resp = client.get("/api/v1/models", params={"task_type": "load_forecast"})
    assert len(resp.json()) == 1
    assert resp.json()[0]["name"] == "模型A"


def test_search_models(client):
    _create_model(client, name="负荷预测A", description="华东地区负荷预测")
    _create_model(client, name="故障诊断B", description="设备故障诊断")

    resp = client.get("/api/v1/models", params={"q": "负荷"})
    assert len(resp.json()) == 1
    assert resp.json()[0]["name"] == "负荷预测A"


def test_get_model(client):
    create_resp = _create_model(client)
    model_id = create_resp.json()["id"]

    resp = client.get(f"/api/v1/models/{model_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == model_id


def test_get_model_not_found(client):
    resp = client.get("/api/v1/models/nonexistent")
    assert resp.status_code == 404


def test_update_model(client):
    model_id = _create_model(client).json()["id"]

    resp = client.put(
        f"/api/v1/models/{model_id}",
        json={"description": "更新后的描述"},
    )
    assert resp.status_code == 200
    assert resp.json()["description"] == "更新后的描述"


def test_status_transitions(client):
    model_id = _create_model(client).json()["id"]

    # draft -> registered (valid)
    resp = client.patch(
        f"/api/v1/models/{model_id}/status",
        json={"target_status": "registered"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "registered"

    # registered -> shared (valid)
    resp = client.patch(
        f"/api/v1/models/{model_id}/status",
        json={"target_status": "shared"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "shared"

    # shared -> draft (invalid)
    resp = client.patch(
        f"/api/v1/models/{model_id}/status",
        json={"target_status": "draft"},
    )
    assert resp.status_code == 422


def test_delete_model(client):
    model_id = _create_model(client).json()["id"]
    resp = client.delete(f"/api/v1/models/{model_id}")
    assert resp.status_code == 204

    resp = client.get(f"/api/v1/models/{model_id}")
    assert resp.status_code == 404


# ── Version Tests ──


def _upload_version(client, model_id, version="1.0.0"):
    model_bytes = b"fake model content"
    return client.post(
        f"/api/v1/models/{model_id}/versions",
        data={
            "version": version,
            "file_format": "joblib",
            "metrics": json.dumps({"mae": 12.5, "mape": 2.8}),
            "description": "Initial version",
        },
        files={"file": ("model.joblib", io.BytesIO(model_bytes), "application/octet-stream")},
    )


def test_upload_version(client):
    model_id = _create_model(client).json()["id"]
    resp = _upload_version(client, model_id)
    assert resp.status_code == 201
    data = resp.json()
    assert data["version"] == "1.0.0"
    assert data["file_format"] == "joblib"
    assert data["stage"] == "development"
    assert data["metrics"]["mape"] == 2.8
    assert data["file_size_bytes"] > 0


def test_upload_duplicate_version(client):
    model_id = _create_model(client).json()["id"]
    _upload_version(client, model_id, version="1.0.0")
    resp = _upload_version(client, model_id, version="1.0.0")
    assert resp.status_code == 409


def test_list_versions(client):
    model_id = _create_model(client).json()["id"]
    _upload_version(client, model_id, version="1.0.0")
    _upload_version(client, model_id, version="2.0.0")

    resp = client.get(f"/api/v1/models/{model_id}/versions")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_version_stage_transition(client):
    model_id = _create_model(client).json()["id"]
    version_id = _upload_version(client, model_id).json()["id"]

    # development -> staging (valid)
    resp = client.patch(
        f"/api/v1/models/{model_id}/versions/{version_id}/stage",
        json={"target_stage": "staging"},
    )
    assert resp.status_code == 200
    assert resp.json()["stage"] == "staging"

    # staging -> production (valid)
    resp = client.patch(
        f"/api/v1/models/{model_id}/versions/{version_id}/stage",
        json={"target_stage": "production"},
    )
    assert resp.status_code == 200
    assert resp.json()["stage"] == "production"

    # production -> development (invalid)
    resp = client.patch(
        f"/api/v1/models/{model_id}/versions/{version_id}/stage",
        json={"target_stage": "development"},
    )
    assert resp.status_code == 422


def test_download_version(client):
    model_id = _create_model(client).json()["id"]
    _upload_version(client, model_id)

    versions = client.get(f"/api/v1/models/{model_id}/versions").json()
    version_id = versions[0]["id"]

    resp = client.get(f"/api/v1/models/{model_id}/versions/{version_id}/download")
    assert resp.status_code == 200
    assert resp.content == b"fake model content"


def test_model_version_count(client):
    model_id = _create_model(client).json()["id"]
    assert client.get(f"/api/v1/models/{model_id}").json()["version_count"] == 0

    _upload_version(client, model_id, version="1.0.0")
    assert client.get(f"/api/v1/models/{model_id}").json()["version_count"] == 1

    _upload_version(client, model_id, version="2.0.0")
    assert client.get(f"/api/v1/models/{model_id}").json()["version_count"] == 2


# ── Pipeline Definition ──

SAMPLE_PIPELINE = """\
data_prep:
  dataset: data.csv
  feature_config: features.yaml

training:
  script: train.py
  params: hyperparams.yaml

output:
  format: joblib
  metrics: [rmse, mae]
"""


def test_get_pipeline_not_exists(client):
    model_id = _create_model(client).json()["id"]
    resp = client.get(f"/api/v1/models/{model_id}/pipeline")
    assert resp.status_code == 200
    data = resp.json()
    assert data["exists"] is False
    assert data["data"] is None


def test_create_pipeline(client):
    model_id = _create_model(client).json()["id"]
    resp = client.put(
        f"/api/v1/models/{model_id}/pipeline",
        json={"content": SAMPLE_PIPELINE},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["exists"] is True
    assert data["data"]["data_prep"]["dataset"] == "data.csv"
    assert data["data"]["training"]["script"] == "train.py"
    assert data["data"]["output"]["format"] == "joblib"

    # Verify via GET
    resp2 = client.get(f"/api/v1/models/{model_id}/pipeline")
    assert resp2.json()["exists"] is True
    assert resp2.json()["data"]["data_prep"]["dataset"] == "data.csv"


def test_update_pipeline(client):
    model_id = _create_model(client).json()["id"]
    client.put(
        f"/api/v1/models/{model_id}/pipeline",
        json={"content": SAMPLE_PIPELINE},
    )

    updated = "data_prep:\n  dataset: new_data.csv\n"
    resp = client.put(
        f"/api/v1/models/{model_id}/pipeline",
        json={"content": updated},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["data_prep"]["dataset"] == "new_data.csv"


def test_delete_pipeline(client):
    model_id = _create_model(client).json()["id"]
    client.put(
        f"/api/v1/models/{model_id}/pipeline",
        json={"content": SAMPLE_PIPELINE},
    )
    resp = client.delete(f"/api/v1/models/{model_id}/pipeline")
    assert resp.status_code == 204

    resp2 = client.get(f"/api/v1/models/{model_id}/pipeline")
    assert resp2.json()["exists"] is False


def test_save_invalid_yaml(client):
    model_id = _create_model(client).json()["id"]
    resp = client.put(
        f"/api/v1/models/{model_id}/pipeline",
        json={"content": "- just\n- a\n- list\n"},
    )
    assert resp.status_code == 422


# ── Pipeline Run Tests ──

# Minimal training script that produces metrics.json and a model file
_TEST_TRAIN_SCRIPT = '''\
import json, sys, os

# Write metrics
json.dump({"mae": 1.5, "rmse": 2.0, "mape": 3.0}, open("metrics.json", "w"))

# Overwrite weights with new content
os.makedirs("weights", exist_ok=True)
with open("weights/model.joblib", "wb") as f:
    f.write(b"trained model bytes")

print("[test] training done")
'''

_RUN_PIPELINE = """\
data_prep:
  dataset: train.csv
  feature_config: features.yaml

training:
  script: train.py
  params: training_params.yaml

output:
  format: joblib
  metrics: [mae, rmse, mape]
"""


def _setup_runnable_version(client, store, model_id):
    """Upload a version and populate code/ with a test training script."""
    _upload_version(client, model_id, version="1.0.0")
    # Find the version dir via store internals
    slug = store._find_slug_by_id(model_id)
    vdir = store._version_dir(slug, "v1.0.0")
    # Write test training script
    code_dir = vdir / "code"
    code_dir.mkdir(exist_ok=True)
    (code_dir / "train.py").write_text(_TEST_TRAIN_SCRIPT)
    # Write minimal feature config
    feat_dir = vdir / "features"
    feat_dir.mkdir(exist_ok=True)
    (feat_dir / "features.yaml").write_text("features:\n  - name: x1\n")
    # Write minimal params
    params_dir = vdir / "params"
    params_dir.mkdir(exist_ok=True)
    (params_dir / "training_params.yaml").write_text("parameters: {}\n")
    # Write minimal dataset
    ds_dir = vdir / "datasets"
    ds_dir.mkdir(exist_ok=True)
    (ds_dir / "train.csv").write_text("x1,y\n1,2\n3,4\n")
    return slug


def test_run_pipeline_no_pipeline(client):
    """Starting a run without pipeline definition returns 400."""
    model_id = _create_model(client).json()["id"]
    _upload_version(client, model_id)
    resp = client.post(
        f"/api/v1/models/{model_id}/pipeline/run",
        json={"base_version": "v1.0.0"},
    )
    assert resp.status_code == 400


def test_run_pipeline_bad_version(client):
    """Starting a run with non-existent version returns 404."""
    model_id = _create_model(client).json()["id"]
    client.put(
        f"/api/v1/models/{model_id}/pipeline",
        json={"content": _RUN_PIPELINE},
    )
    resp = client.post(
        f"/api/v1/models/{model_id}/pipeline/run",
        json={"base_version": "v99.0.0"},
    )
    assert resp.status_code == 404


def test_list_runs_empty(client):
    model_id = _create_model(client).json()["id"]
    resp = client.get(f"/api/v1/models/{model_id}/pipeline/runs")
    assert resp.status_code == 200
    assert resp.json() == []


def test_run_pipeline_success(client, store):
    """Full pipeline run: start, poll until done, verify new version created."""
    from modelforge.runner import _runner, _runner_lock
    import modelforge.runner as runner_mod

    # Reset runner singleton so it picks up the test store
    with _runner_lock:
        runner_mod._runner = None

    model_id = _create_model(client).json()["id"]
    _setup_runnable_version(client, store, model_id)

    # Create pipeline definition
    client.put(
        f"/api/v1/models/{model_id}/pipeline",
        json={"content": _RUN_PIPELINE},
    )

    # Start run
    resp = client.post(
        f"/api/v1/models/{model_id}/pipeline/run",
        json={"base_version": "v1.0.0"},
    )
    assert resp.status_code == 201
    run = resp.json()
    run_id = run["id"]
    assert run["status"] in ("pending", "running")
    assert run["base_version"] == "v1.0.0"

    # Poll until completion (max 30 seconds)
    for _ in range(30):
        time.sleep(1)
        resp = client.get(f"/api/v1/models/{model_id}/pipeline/runs/{run_id}")
        assert resp.status_code == 200
        run = resp.json()
        if run["status"] in ("success", "failed"):
            break

    assert run["status"] == "success", f"Run failed: {run.get('error')} | log: {run.get('log', '')}"
    assert run["result_version"] is not None
    assert run["metrics"]["mae"] == 1.5

    # Verify new version appears in listing
    versions = client.get(f"/api/v1/models/{model_id}/versions").json()
    version_strings = [v["version"] for v in versions]
    assert run["result_version"] in version_strings

    # Verify run appears in history
    runs = client.get(f"/api/v1/models/{model_id}/pipeline/runs").json()
    assert len(runs) >= 1
    assert runs[0]["id"] == run_id

    # Reset runner singleton
    with _runner_lock:
        runner_mod._runner = None


# ── Fork Tests ──


def test_fork_model(client, store):
    """Fork creates new model with version that has lineage fields."""
    model_id = _create_model(client).json()["id"]
    _upload_version(client, model_id, version="1.0.0")
    # Get version UUID
    versions = client.get(f"/api/v1/models/{model_id}/versions").json()
    version_id = versions[0]["id"]

    resp = client.post(
        f"/api/v1/models/{model_id}/fork",
        json={
            "source_version_id": version_id,
            "new_name": "华南短期负荷预测模型",
            "new_owner_org": "华南电网",
        },
    )
    assert resp.status_code == 201
    new_model = resp.json()
    assert new_model["name"] == "华南短期负荷预测模型"
    assert new_model["owner_org"] == "华南电网"
    assert new_model["forked_version_id"] is not None

    # Verify the forked version has lineage
    new_versions = client.get(
        f"/api/v1/models/{new_model['id']}/versions"
    ).json()
    assert len(new_versions) == 1
    fv = new_versions[0]
    assert fv["parent_version_id"] == version_id
    assert fv["source_model_id"] == model_id


def test_fork_model_not_found(client):
    """Fork with non-existent version returns 404."""
    model_id = _create_model(client).json()["id"]
    resp = client.post(
        f"/api/v1/models/{model_id}/fork",
        json={
            "source_version_id": "nonexistent-uuid",
            "new_name": "不存在的Fork",
            "new_owner_org": "测试单位",
        },
    )
    assert resp.status_code == 404


def test_fork_copies_pipeline(client, store):
    """Fork copies pipeline.yaml to new model."""
    model_id = _create_model(client).json()["id"]
    _upload_version(client, model_id, version="1.0.0")

    # Create pipeline
    client.put(
        f"/api/v1/models/{model_id}/pipeline",
        json={"content": _RUN_PIPELINE},
    )

    # Fork
    version_id = client.get(
        f"/api/v1/models/{model_id}/versions"
    ).json()[0]["id"]
    resp = client.post(
        f"/api/v1/models/{model_id}/fork",
        json={
            "source_version_id": version_id,
            "new_name": "Fork带Pipeline",
            "new_owner_org": "测试单位",
        },
    )
    assert resp.status_code == 201
    new_model_id = resp.json()["id"]

    # Verify pipeline was copied
    pipeline_resp = client.get(
        f"/api/v1/models/{new_model_id}/pipeline"
    )
    assert pipeline_resp.status_code == 200
    assert pipeline_resp.json()["exists"] is True
    assert pipeline_resp.json()["data"]["training"]["script"] == "train.py"


def test_pipeline_run_sets_parent_version(client, store):
    """Pipeline run creates new version with parent_version_id set."""
    import modelforge.runner as runner_mod
    from modelforge.runner import _runner_lock

    with _runner_lock:
        runner_mod._runner = None

    model_id = _create_model(client).json()["id"]
    slug = _setup_runnable_version(client, store, model_id)

    # Get base version UUID
    versions = client.get(f"/api/v1/models/{model_id}/versions").json()
    base_version_id = versions[0]["id"]

    # Create pipeline
    client.put(
        f"/api/v1/models/{model_id}/pipeline",
        json={"content": _RUN_PIPELINE},
    )

    # Start run
    resp = client.post(
        f"/api/v1/models/{model_id}/pipeline/run",
        json={"base_version": "v1.0.0"},
    )
    assert resp.status_code == 201
    run_id = resp.json()["id"]

    # Poll until done
    for _ in range(30):
        time.sleep(1)
        run = client.get(
            f"/api/v1/models/{model_id}/pipeline/runs/{run_id}"
        ).json()
        if run["status"] in ("success", "failed"):
            break

    assert run["status"] == "success", f"Run failed: {run.get('log', '')}"

    # Verify parent_version_id on new version
    versions = client.get(f"/api/v1/models/{model_id}/versions").json()
    new_version = next(
        v for v in versions if v["version"] == run["result_version"]
    )
    assert new_version["parent_version_id"] == base_version_id

    with _runner_lock:
        runner_mod._runner = None


def test_stale_run_recovery(client, store):
    """Completed training is recovered after server restart."""
    model_id = _create_model(client).json()["id"]
    slug = _setup_runnable_version(client, store, model_id)

    # Get base version UUID
    versions = client.get(
        f"/api/v1/models/{model_id}/versions",
    ).json()
    base_version_id = versions[0]["id"]

    # Simulate: create run record in "failed" state
    # (as if _cleanup_stale_runs marked it wrongly)
    run = store.create_run(model_id, {
        "base_version": "v1.0.0",
        "target_version": "v1.1.0",
        "pipeline_snapshot": {"output": {"format": "joblib"}},
    })
    run_id = run["id"]
    store.update_run(model_id, run_id, {
        "status": "failed",
        "error": "Server restarted during execution",
    })

    # Simulate: training completed (copy base + write metrics)
    import shutil
    base_dir = store._version_dir(slug, "v1.0.0")
    new_dir = store._version_dir(slug, "v1.1.0")
    shutil.copytree(base_dir, new_dir)
    # Remove version.yaml (real runner deletes it)
    vyaml = new_dir / "version.yaml"
    if vyaml.exists():
        vyaml.unlink()
    # Write metrics as training script would
    import json
    (new_dir / "metrics.json").write_text(
        json.dumps({"mae": 1.0, "rmse": 2.0})
    )

    # Run recovery
    from modelforge.main import _cleanup_stale_runs
    _cleanup_stale_runs(store)

    # Verify run was recovered
    recovered = store.get_run(model_id, run_id)
    assert recovered["status"] == "success"
    assert recovered["result_version"] == "1.1.0"
    assert recovered["metrics"]["mae"] == 1.0

    # Verify version record was created
    versions = client.get(
        f"/api/v1/models/{model_id}/versions",
    ).json()
    assert len(versions) == 2
    v11 = next(v for v in versions if v["version"] == "1.1.0")
    assert v11["parent_version_id"] == base_version_id


# ── Artifact CRUD Tests ──


def test_upload_artifact(client, store):
    model_id = _create_model(client).json()["id"]
    _upload_version(client, model_id)
    version_id = client.get(f"/api/v1/models/{model_id}/versions").json()[0]["id"]

    resp = client.post(
        f"/api/v1/models/{model_id}/versions/{version_id}/artifacts/datasets",
        files={"file": ("test.csv", io.BytesIO(b"a,b\n1,2\n"), "text/csv")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "test.csv"
    assert data["size"] > 0

    listing = client.get(
        f"/api/v1/models/{model_id}/versions/{version_id}/artifacts/datasets",
    ).json()
    names = [f["name"] for f in listing]
    assert "test.csv" in names


def test_upload_artifact_invalid_category(client, store):
    model_id = _create_model(client).json()["id"]
    _upload_version(client, model_id)
    version_id = client.get(f"/api/v1/models/{model_id}/versions").json()[0]["id"]

    resp = client.post(
        f"/api/v1/models/{model_id}/versions/{version_id}/artifacts/invalid",
        files={"file": ("test.csv", io.BytesIO(b"data"), "text/csv")},
    )
    assert resp.status_code == 400


def test_upload_artifact_path_traversal(client, store):
    model_id = _create_model(client).json()["id"]
    _upload_version(client, model_id)
    version_id = client.get(f"/api/v1/models/{model_id}/versions").json()[0]["id"]

    resp = client.post(
        f"/api/v1/models/{model_id}/versions/{version_id}/artifacts/code",
        files={"file": ("../../../etc/passwd", io.BytesIO(b"evil"), "text/plain")},
    )
    assert resp.status_code == 400


def test_save_artifact_text(client, store):
    model_id = _create_model(client).json()["id"]
    _upload_version(client, model_id)
    version_id = client.get(f"/api/v1/models/{model_id}/versions").json()[0]["id"]

    resp = client.put(
        f"/api/v1/models/{model_id}/versions/{version_id}/artifacts/params/train.yaml",
        json={"content": "learning_rate: 0.01\nepochs: 100\n"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "train.yaml"

    resp2 = client.get(
        f"/api/v1/models/{model_id}/versions/{version_id}/artifacts/params/train.yaml",
    )
    assert resp2.status_code == 200
    assert "learning_rate" in resp2.text


def test_save_artifact_text_binary_rejected(client, store):
    model_id = _create_model(client).json()["id"]
    _upload_version(client, model_id)
    version_id = client.get(f"/api/v1/models/{model_id}/versions").json()[0]["id"]

    resp = client.put(
        f"/api/v1/models/{model_id}/versions/{version_id}/artifacts/datasets/data.csv",
        json={"content": "a,b\n1,2\n"},
    )
    assert resp.status_code == 400


def test_delete_artifact(client, store):
    model_id = _create_model(client).json()["id"]
    _upload_version(client, model_id)
    version_id = client.get(f"/api/v1/models/{model_id}/versions").json()[0]["id"]

    client.post(
        f"/api/v1/models/{model_id}/versions/{version_id}/artifacts/code",
        files={"file": ("helper.py", io.BytesIO(b"# helper"), "text/plain")},
    )

    resp = client.delete(
        f"/api/v1/models/{model_id}/versions/{version_id}/artifacts/code/helper.py",
    )
    assert resp.status_code == 204

    listing = client.get(
        f"/api/v1/models/{model_id}/versions/{version_id}/artifacts/code",
    ).json()
    names = [f["name"] for f in listing]
    assert "helper.py" not in names


def test_delete_artifact_not_found(client, store):
    model_id = _create_model(client).json()["id"]
    _upload_version(client, model_id)
    version_id = client.get(f"/api/v1/models/{model_id}/versions").json()[0]["id"]

    resp = client.delete(
        f"/api/v1/models/{model_id}/versions/{version_id}/artifacts/code/nonexistent.py",
    )
    assert resp.status_code == 404


def test_upload_overwrites_existing(client, store):
    model_id = _create_model(client).json()["id"]
    _upload_version(client, model_id)
    version_id = client.get(f"/api/v1/models/{model_id}/versions").json()[0]["id"]

    client.post(
        f"/api/v1/models/{model_id}/versions/{version_id}/artifacts/params",
        files={"file": ("config.yaml", io.BytesIO(b"v1"), "text/plain")},
    )
    client.post(
        f"/api/v1/models/{model_id}/versions/{version_id}/artifacts/params",
        files={"file": ("config.yaml", io.BytesIO(b"v2 longer"), "text/plain")},
    )

    resp = client.get(
        f"/api/v1/models/{model_id}/versions/{version_id}/artifacts/params/config.yaml",
    )
    assert resp.text == "v2 longer"


# ── Draft Version Tests ──


def test_create_draft_version(client, store):
    """Creating a draft copies artifacts but clears weights."""
    model_id = _create_model(client).json()["id"]
    _upload_version(client, model_id, version="1.0.0")

    slug = store._find_slug_by_id(model_id)
    vdir = store._version_dir(slug, "v1.0.0")
    (vdir / "datasets").mkdir(exist_ok=True)
    (vdir / "datasets" / "train.csv").write_text("x,y\n1,2\n")
    (vdir / "code").mkdir(exist_ok=True)
    (vdir / "code" / "train.py").write_text("print('train')")

    resp = client.post(
        "/api/v1/models/" + model_id + "/versions/draft",
        json={"base_version": "v1.0.0", "description": "测试草稿"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["stage"] == "draft"
    assert data["file_path"] is None
    assert data["file_size_bytes"] is None
    assert data["metrics"] is None
    assert data["parent_version_id"] is not None

    draft_vdir = store._version_dir(slug, f"v{data['version']}")
    assert (draft_vdir / "datasets" / "train.csv").exists()
    assert (draft_vdir / "code" / "train.py").exists()
    assert len(list((draft_vdir / "weights").iterdir())) == 0

    versions = client.get(
        f"/api/v1/models/{model_id}/versions",
    ).json()
    assert len(versions) == 2


def test_create_draft_bad_base_version(client):
    """Creating draft with non-existent base returns 404."""
    model_id = _create_model(client).json()["id"]
    resp = client.post(
        f"/api/v1/models/{model_id}/versions/draft",
        json={"base_version": "v99.0.0"},
    )
    assert resp.status_code == 404


def test_draft_version_stage_transitions(client, store):
    """Draft can transition to archived but not to staging."""
    model_id = _create_model(client).json()["id"]
    _upload_version(client, model_id, version="1.0.0")

    draft = client.post(
        f"/api/v1/models/{model_id}/versions/draft",
        json={"base_version": "v1.0.0"},
    ).json()
    draft_id = draft["id"]

    resp = client.patch(
        f"/api/v1/models/{model_id}/versions/{draft_id}/stage",
        json={"target_stage": "staging"},
    )
    assert resp.status_code == 422

    resp = client.patch(
        f"/api/v1/models/{model_id}/versions/{draft_id}/stage",
        json={"target_stage": "archived"},
    )
    assert resp.status_code == 200
    assert resp.json()["stage"] == "archived"


def test_draft_download_blocked(client, store):
    """Cannot download weights from a draft version."""
    model_id = _create_model(client).json()["id"]
    _upload_version(client, model_id, version="1.0.0")

    draft = client.post(
        f"/api/v1/models/{model_id}/versions/draft",
        json={"base_version": "v1.0.0"},
    ).json()

    resp = client.get(
        f"/api/v1/models/{model_id}/versions/{draft['id']}/download",
    )
    assert resp.status_code == 400


def test_draft_artifact_crud(client, store):
    """Can upload/edit/delete artifacts on a draft."""
    model_id = _create_model(client).json()["id"]
    _upload_version(client, model_id, version="1.0.0")

    draft = client.post(
        f"/api/v1/models/{model_id}/versions/draft",
        json={"base_version": "v1.0.0"},
    ).json()
    draft_id = draft["id"]

    resp = client.post(
        f"/api/v1/models/{model_id}/versions/{draft_id}/artifacts/datasets",
        files={"file": ("new.csv", io.BytesIO(b"a,b\n1,2\n"), "text/csv")},
    )
    assert resp.status_code == 200

    resp = client.put(
        f"/api/v1/models/{model_id}/versions/{draft_id}/artifacts/params/hp.yaml",
        json={"content": "lr: 0.01\n"},
    )
    assert resp.status_code == 200

    resp = client.delete(
        f"/api/v1/models/{model_id}/versions/{draft_id}/artifacts/params/hp.yaml",
    )
    assert resp.status_code == 204


def test_run_pipeline_on_draft(client, store):
    """Pipeline run on draft: trains in-place, finalizes to development."""
    import modelforge.runner as runner_mod
    from modelforge.runner import _runner_lock

    with _runner_lock:
        runner_mod._runner = None

    model_id = _create_model(client).json()["id"]
    slug = _setup_runnable_version(client, store, model_id)

    client.put(
        f"/api/v1/models/{model_id}/pipeline",
        json={"content": _RUN_PIPELINE},
    )

    draft = client.post(
        f"/api/v1/models/{model_id}/versions/draft",
        json={"base_version": "v1.0.0"},
    ).json()
    draft_version = draft["version"]
    draft_id = draft["id"]

    resp = client.post(
        f"/api/v1/models/{model_id}/pipeline/run",
        json={
            "base_version": f"v{draft_version}",
            "draft_version": f"v{draft_version}",
        },
    )
    assert resp.status_code == 201
    run_id = resp.json()["id"]

    for _ in range(30):
        time.sleep(1)
        run = client.get(
            f"/api/v1/models/{model_id}/pipeline/runs/{run_id}",
        ).json()
        if run["status"] in ("success", "failed"):
            break

    assert run["status"] == "success", (
        f"Run failed: {run.get('error')} | log: {run.get('log', '')}"
    )

    v = client.get(
        f"/api/v1/models/{model_id}/versions/{draft_id}",
    ).json()
    assert v["stage"] == "development"
    assert v["file_path"] is not None
    assert v["file_size_bytes"] > 0
    assert v["metrics"] is not None

    with _runner_lock:
        runner_mod._runner = None


def test_run_pipeline_on_draft_failure_preserves_dir(client, store):
    """When training fails on a draft, the directory is preserved."""
    import modelforge.runner as runner_mod
    from modelforge.runner import _runner_lock

    with _runner_lock:
        runner_mod._runner = None

    model_id = _create_model(client).json()["id"]
    _upload_version(client, model_id, version="1.0.0")

    slug = store._find_slug_by_id(model_id)
    vdir = store._version_dir(slug, "v1.0.0")
    code_dir = vdir / "code"
    code_dir.mkdir(exist_ok=True)
    (code_dir / "train.py").write_text(
        "raise RuntimeError('intentional failure')"
    )

    client.put(
        f"/api/v1/models/{model_id}/pipeline",
        json={"content": _RUN_PIPELINE},
    )

    draft = client.post(
        f"/api/v1/models/{model_id}/versions/draft",
        json={"base_version": "v1.0.0"},
    ).json()
    draft_version = draft["version"]
    draft_id = draft["id"]

    resp = client.post(
        f"/api/v1/models/{model_id}/pipeline/run",
        json={
            "base_version": f"v{draft_version}",
            "draft_version": f"v{draft_version}",
        },
    )
    assert resp.status_code == 201
    run_id = resp.json()["id"]

    for _ in range(30):
        time.sleep(1)
        run = client.get(
            f"/api/v1/models/{model_id}/pipeline/runs/{run_id}",
        ).json()
        if run["status"] in ("success", "failed"):
            break

    assert run["status"] == "failed"

    draft_vdir = store._version_dir(slug, f"v{draft_version}")
    assert draft_vdir.exists()

    v = client.get(
        f"/api/v1/models/{model_id}/versions/{draft_id}",
    ).json()
    assert v["stage"] == "draft"

    with _runner_lock:
        runner_mod._runner = None


def test_run_non_draft_as_draft_rejected(client, store):
    """Running pipeline with draft_version on non-draft returns 400."""
    import modelforge.runner as runner_mod
    from modelforge.runner import _runner_lock
    with _runner_lock:
        runner_mod._runner = None

    model_id = _create_model(client).json()["id"]
    _setup_runnable_version(client, store, model_id)
    client.put(
        f"/api/v1/models/{model_id}/pipeline",
        json={"content": _RUN_PIPELINE},
    )

    resp = client.post(
        f"/api/v1/models/{model_id}/pipeline/run",
        json={
            "base_version": "v1.0.0",
            "draft_version": "v1.0.0",
        },
    )
    assert resp.status_code == 400

    with _runner_lock:
        runner_mod._runner = None
