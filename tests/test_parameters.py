PREFIX = "/api/v1"


def _create_template(client, name="GBR华东推荐参数", **overrides):
    data = {
        "name": name,
        "algorithm_type": "GradientBoosting",
        "scenario_tags": {"region": "华东", "forecast_horizon": "24h"},
        "parameters": {
            "n_estimators": 200,
            "max_depth": 6,
            "learning_rate": 0.1,
        },
        "performance_notes": "华东2024全年数据，MAPE=2.8%",
    }
    data.update(overrides)
    return client.post(f"{PREFIX}/parameter-templates", json=data)


def test_create_template(client):
    resp = _create_template(client)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "GBR华东推荐参数"
    assert data["parameters"]["n_estimators"] == 200


def test_list_templates(client):
    _create_template(client, name="模板A")
    _create_template(client, name="模板B", algorithm_type="LSTM")

    resp = client.get(f"{PREFIX}/parameter-templates")
    assert len(resp.json()) == 2

    resp = client.get(f"{PREFIX}/parameter-templates", params={"algorithm_type": "LSTM"})
    assert len(resp.json()) == 1
    assert resp.json()[0]["name"] == "模板B"


def test_update_template(client):
    tid = _create_template(client).json()["id"]
    resp = client.put(
        f"{PREFIX}/parameter-templates/{tid}",
        json={"parameters": {"n_estimators": 300, "max_depth": 8}},
    )
    assert resp.status_code == 200
    assert resp.json()["parameters"]["n_estimators"] == 300


def test_delete_template(client):
    tid = _create_template(client).json()["id"]
    resp = client.delete(f"{PREFIX}/parameter-templates/{tid}")
    assert resp.status_code == 204

    resp = client.get(f"{PREFIX}/parameter-templates/{tid}")
    assert resp.status_code == 404


def test_template_linked_to_model(client):
    # Create a model first
    model = client.post(
        f"{PREFIX}/models",
        json={
            "name": "测试模型",
            "task_type": "load_forecast",
            "algorithm_type": "GBR",
            "framework": "sklearn",
            "owner_org": "华东省公司",
        },
    ).json()

    resp = _create_template(client, model_asset_id=model["id"])
    assert resp.status_code == 201
    assert resp.json()["model_asset_id"] == model["id"]

    # Search by model
    resp = client.get(
        f"{PREFIX}/parameter-templates", params={"model_asset_id": model["id"]}
    )
    assert len(resp.json()) == 1
