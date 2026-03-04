import io
import json


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
