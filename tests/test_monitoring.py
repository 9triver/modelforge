import io

import pytest

PREFIX = "/api/v1"


@pytest.fixture
def model_file():
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


@pytest.fixture
def running_deployment(client, model_file):
    """Create a model, upload version, create and start deployment."""
    model = client.post(
        f"{PREFIX}/models",
        json={
            "name": "监控测试模型",
            "task_type": "load_forecast",
            "algorithm_type": "LinearRegression",
            "framework": "sklearn",
            "owner_org": "测试省公司",
        },
    ).json()

    version = client.post(
        f"{PREFIX}/models/{model['id']}/versions",
        data={"version": "1.0.0", "file_format": "joblib"},
        files={"file": ("model.joblib", model_file, "application/octet-stream")},
    ).json()

    deploy = client.post(
        f"{PREFIX}/deployments",
        json={"name": "监控测试部署", "model_version_id": version["id"]},
    ).json()

    client.post(f"{PREFIX}/deployments/{deploy['id']}/start")
    return deploy["id"]


def test_predict_creates_log(client, running_deployment):
    deploy_id = running_deployment

    resp = client.post(
        f"{PREFIX}/deployments/{deploy_id}/predict",
        json={"input_data": [[1, 2]]},
    )
    assert resp.status_code == 200
    assert "prediction_id" in resp.json()

    # Check prediction log
    logs = client.get(f"{PREFIX}/deployments/{deploy_id}/predictions").json()
    assert len(logs) == 1
    assert logs[0]["deployment_id"] == deploy_id


def test_submit_actuals_and_metrics(client, running_deployment):
    deploy_id = running_deployment

    # Make predictions
    prediction_ids = []
    inputs = [[1, 2], [3, 4], [5, 6]]
    for inp in inputs:
        resp = client.post(
            f"{PREFIX}/deployments/{deploy_id}/predict",
            json={"input_data": [inp]},
        )
        prediction_ids.append(resp.json()["prediction_id"])

    # Submit actuals
    actuals = [
        {"prediction_id": prediction_ids[0], "actual_value": 3.0},
        {"prediction_id": prediction_ids[1], "actual_value": 7.0},
        {"prediction_id": prediction_ids[2], "actual_value": 11.0},
    ]
    resp = client.post(
        f"{PREFIX}/deployments/{deploy_id}/actuals",
        json={"actuals": actuals},
    )
    assert resp.status_code == 200
    assert resp.json()["updated"] == 3
    assert resp.json()["not_found"] == []

    # Get metrics
    resp = client.get(f"{PREFIX}/deployments/{deploy_id}/metrics")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 3
    assert data["mae"] is not None
    assert data["rmse"] is not None
    # The model is nearly perfect on training data, so errors should be small
    assert data["mae"] < 1.0


def test_submit_actuals_not_found(client, running_deployment):
    deploy_id = running_deployment

    resp = client.post(
        f"{PREFIX}/deployments/{deploy_id}/actuals",
        json={"actuals": [{"prediction_id": "nonexistent", "actual_value": 5.0}]},
    )
    assert resp.json()["updated"] == 0
    assert "nonexistent" in resp.json()["not_found"]


def test_stats(client, running_deployment):
    deploy_id = running_deployment

    # Make a few predictions
    for i in range(5):
        client.post(
            f"{PREFIX}/deployments/{deploy_id}/predict",
            json={"input_data": [[1, 2]]},
        )

    resp = client.get(f"{PREFIX}/deployments/{deploy_id}/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_predictions"] == 5
    assert data["error_count"] == 0
    assert data["error_rate"] == 0.0
    assert data["avg_latency_ms"] > 0
    assert data["p95_latency_ms"] > 0


def test_metrics_empty(client, running_deployment):
    deploy_id = running_deployment

    resp = client.get(f"{PREFIX}/deployments/{deploy_id}/metrics")
    assert resp.json()["count"] == 0
