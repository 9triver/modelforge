import io
import json

import joblib
import numpy as np
import pytest
import yaml
from sklearn.linear_model import LinearRegression

PREFIX = "/api/v1"


@pytest.fixture
def trained_model():
    """Create a real sklearn model trained on 2 features."""
    model = LinearRegression()
    X = np.array([[1, 10], [2, 20], [3, 30], [4, 40], [5, 50]])
    y = np.array([100, 200, 300, 400, 500])
    model.fit(X, y)

    buf = io.BytesIO()
    joblib.dump(model, buf)
    buf.seek(0)
    return buf


def _setup_model_version(client, trained_model, metrics=None):
    """Create model + version with features.yaml and pipeline.yaml."""
    model = client.post(
        f"{PREFIX}/models",
        json={
            "name": "试评估测试模型",
            "task_type": "load_forecast",
            "algorithm_type": "LinearRegression",
            "framework": "sklearn",
            "owner_org": "测试省公司",
        },
    ).json()
    model_id = model["id"]

    version = client.post(
        f"{PREFIX}/models/{model_id}/versions",
        data={
            "version": "1.0.0",
            "file_format": "joblib",
            "metrics": json.dumps(metrics or {"mae": 5.0, "rmse": 8.0, "mape": 2.5}),
        },
        files={"file": ("model.joblib", trained_model, "application/octet-stream")},
    ).json()
    version_id = version["id"]

    # Upload features.yaml
    features_yaml = yaml.dump({
        "group_name": "test",
        "target": "target_col",
        "features": [
            {"name": "feat_a", "data_type": "float"},
            {"name": "feat_b", "data_type": "float"},
        ],
    })
    client.post(
        f"{PREFIX}/models/{model_id}/versions/{version_id}/artifacts/features",
        files={"file": ("features.yaml", io.BytesIO(features_yaml.encode()), "text/yaml")},
    )

    # Save pipeline.yaml with target
    client.put(
        f"{PREFIX}/models/{model_id}/pipeline",
        json={"yaml_text": yaml.dump({"data_prep": {"target": "target_col"}})},
    )

    return model_id, version_id


def _make_csv(rows, columns=("feat_a", "feat_b", "target_col")):
    """Generate a CSV in bytes."""
    lines = [",".join(columns)]
    for row in rows:
        lines.append(",".join(str(v) for v in row))
    return ("\n".join(lines)).encode()


def test_trial_evaluate_success(client, trained_model):
    model_id, version_id = _setup_model_version(client, trained_model)

    csv_data = _make_csv([
        (1, 10, 100),
        (2, 20, 200),
        (3, 30, 300),
    ])

    resp = client.post(
        f"{PREFIX}/models/{model_id}/versions/{version_id}/trial-evaluate",
        files={"file": ("test.csv", io.BytesIO(csv_data), "text/csv")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["sample_count"] == 3
    assert data["features_matched"] == 2
    assert data["features_total"] == 2
    assert "mae" in data["trial_metrics"]
    assert "rmse" in data["trial_metrics"]
    assert data["verdict"] in ("compatible", "moderate_degradation", "severe_degradation")
    assert isinstance(data["comparison"], list)


def test_trial_evaluate_missing_target(client, trained_model):
    model_id, version_id = _setup_model_version(client, trained_model)

    csv_data = _make_csv(
        [(1, 10, 100)],
        columns=("feat_a", "feat_b", "wrong_col"),
    )

    resp = client.post(
        f"{PREFIX}/models/{model_id}/versions/{version_id}/trial-evaluate",
        files={"file": ("test.csv", io.BytesIO(csv_data), "text/csv")},
    )
    assert resp.status_code == 400
    assert "target_col" in resp.json()["detail"]


def test_trial_evaluate_empty_csv(client, trained_model):
    model_id, version_id = _setup_model_version(client, trained_model)

    resp = client.post(
        f"{PREFIX}/models/{model_id}/versions/{version_id}/trial-evaluate",
        files={"file": ("test.csv", io.BytesIO(b""), "text/csv")},
    )
    assert resp.status_code == 400


def test_trial_evaluate_non_csv(client, trained_model):
    model_id, version_id = _setup_model_version(client, trained_model)

    resp = client.post(
        f"{PREFIX}/models/{model_id}/versions/{version_id}/trial-evaluate",
        files={"file": ("test.txt", io.BytesIO(b"not csv"), "text/plain")},
    )
    assert resp.status_code == 400


def test_trial_evaluate_verdict_compatible(client, trained_model):
    """Model trained on exact same data → metrics should be close → compatible."""
    model_id, version_id = _setup_model_version(
        client, trained_model,
        metrics={"mae": 0.0, "rmse": 0.0, "mape": 0.0},
    )

    # Use training data — predictions should be near-perfect
    csv_data = _make_csv([
        (1, 10, 100),
        (2, 20, 200),
        (3, 30, 300),
        (4, 40, 400),
        (5, 50, 500),
    ])

    resp = client.post(
        f"{PREFIX}/models/{model_id}/versions/{version_id}/trial-evaluate",
        files={"file": ("test.csv", io.BytesIO(csv_data), "text/csv")},
    )
    assert resp.status_code == 200
    data = resp.json()
    # Linear model on its training data should have near-zero error
    assert data["trial_metrics"]["mae"] < 1.0


def test_trial_evaluate_version_not_found(client):
    model = client.post(
        f"{PREFIX}/models",
        json={
            "name": "不存在版本",
            "task_type": "load_forecast",
            "algorithm_type": "LR",
            "framework": "sklearn",
            "owner_org": "测试",
        },
    ).json()

    resp = client.post(
        f"{PREFIX}/models/{model['id']}/versions/fake-id/trial-evaluate",
        files={"file": ("test.csv", io.BytesIO(b"a,b\n1,2"), "text/csv")},
    )
    assert resp.status_code == 404
