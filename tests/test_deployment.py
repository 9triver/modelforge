import io
import json

import pytest

PREFIX = "/api/v1"


@pytest.fixture
def model_file():
    """Create a real sklearn model for testing."""
    import joblib
    import numpy as np
    from sklearn.linear_model import LinearRegression

    model = LinearRegression()
    X = np.array([[1, 2], [3, 4], [5, 6], [7, 8]])
    y = np.array([3, 7, 11, 15])
    model.fit(X, y)

    buf = io.BytesIO()
    joblib.dump(model, buf)
    buf.seek(0)
    return buf


def _setup_model_and_version(client, model_file):
    """Create a model asset and upload a version, return (model_id, version_id)."""
    model = client.post(
        f"{PREFIX}/models",
        json={
            "name": "测试部署模型",
            "task_type": "load_forecast",
            "algorithm_type": "LinearRegression",
            "framework": "sklearn",
            "owner_org": "测试省公司",
        },
    ).json()

    version = client.post(
        f"{PREFIX}/models/{model['id']}/versions",
        data={
            "version": "1.0.0",
            "file_format": "joblib",
            "metrics": json.dumps({"mae": 0.1}),
        },
        files={"file": ("model.joblib", model_file, "application/octet-stream")},
    ).json()

    return model["id"], version["id"]


def test_create_deployment(client, model_file):
    _, version_id = _setup_model_and_version(client, model_file)

    resp = client.post(
        f"{PREFIX}/deployments",
        json={"name": "测试部署", "model_version_id": version_id},
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "pending"


def test_start_and_predict(client, model_file):
    _, version_id = _setup_model_and_version(client, model_file)

    # Create deployment
    deploy = client.post(
        f"{PREFIX}/deployments",
        json={"name": "测试部署", "model_version_id": version_id},
    ).json()

    # Start
    resp = client.post(f"{PREFIX}/deployments/{deploy['id']}/start")
    assert resp.status_code == 200
    assert resp.json()["status"] == "running"

    # Predict
    resp = client.post(
        f"{PREFIX}/deployments/{deploy['id']}/predict",
        json={"input_data": [[1, 2], [3, 4]]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["output"]) == 2
    assert data["latency_ms"] >= 0
    # LinearRegression on [1,2],[3,4],[5,6],[7,8] -> [3,7,11,15]
    # predict [1,2] should be ~3, [3,4] should be ~7
    assert abs(data["output"][0] - 3.0) < 0.1
    assert abs(data["output"][1] - 7.0) < 0.1


def test_predict_when_not_running(client, model_file):
    _, version_id = _setup_model_and_version(client, model_file)

    deploy = client.post(
        f"{PREFIX}/deployments",
        json={"name": "测试部署", "model_version_id": version_id},
    ).json()

    resp = client.post(
        f"{PREFIX}/deployments/{deploy['id']}/predict",
        json={"input_data": [[1, 2]]},
    )
    assert resp.status_code == 400


def test_stop_deployment(client, model_file):
    _, version_id = _setup_model_and_version(client, model_file)

    deploy = client.post(
        f"{PREFIX}/deployments",
        json={"name": "测试部署", "model_version_id": version_id},
    ).json()

    client.post(f"{PREFIX}/deployments/{deploy['id']}/start")

    resp = client.post(f"{PREFIX}/deployments/{deploy['id']}/stop")
    assert resp.status_code == 200
    assert resp.json()["status"] == "stopped"

    # Predict after stop should fail
    resp = client.post(
        f"{PREFIX}/deployments/{deploy['id']}/predict",
        json={"input_data": [[1, 2]]},
    )
    assert resp.status_code == 400


def test_list_deployments(client, model_file):
    _, version_id = _setup_model_and_version(client, model_file)

    client.post(
        f"{PREFIX}/deployments",
        json={"name": "部署A", "model_version_id": version_id},
    )
    client.post(
        f"{PREFIX}/deployments",
        json={"name": "部署B", "model_version_id": version_id},
    )

    resp = client.get(f"{PREFIX}/deployments")
    assert len(resp.json()) == 2


def test_predict_by_name(client, model_file):
    _, version_id = _setup_model_and_version(client, model_file)

    deploy = client.post(
        f"{PREFIX}/deployments",
        json={"name": "load-forecast-prod", "model_version_id": version_id},
    ).json()
    client.post(f"{PREFIX}/deployments/{deploy['id']}/start")

    resp = client.post(
        f"{PREFIX}/predict/load-forecast-prod",
        json={"input_data": [[1, 2], [3, 4]]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["output"]) == 2
    assert abs(data["output"][0] - 3.0) < 0.1


def test_predict_by_name_not_found(client):
    resp = client.post(
        f"{PREFIX}/predict/nonexistent",
        json={"input_data": [[1, 2]]},
    )
    assert resp.status_code == 404


def test_delete_deployment(client, model_file):
    _, version_id = _setup_model_and_version(client, model_file)

    deploy = client.post(
        f"{PREFIX}/deployments",
        json={"name": "测试部署", "model_version_id": version_id},
    ).json()

    resp = client.delete(f"{PREFIX}/deployments/{deploy['id']}")
    assert resp.status_code == 204
