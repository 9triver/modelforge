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


# ── Comparison tests ──


def test_compare_two_templates(client):
    t1 = _create_template(
        client,
        name="模板A",
        parameters={"lr": 0.1, "epochs": 100, "batch_size": 32},
    ).json()
    t2 = _create_template(
        client,
        name="模板B",
        parameters={"lr": 0.05, "epochs": 100, "dropout": 0.3},
    ).json()

    resp = client.post(
        f"{PREFIX}/parameter-templates/compare",
        json={
            "left_type": "template",
            "left_id": t1["id"],
            "right_type": "template",
            "right_id": t2["id"],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["left_label"] == "模板A"
    assert data["right_label"] == "模板B"

    # lr changed, epochs unchanged
    diff_map = {d["key"]: d for d in data["diff"]}
    assert diff_map["lr"]["changed"] is True
    assert diff_map["epochs"]["changed"] is False

    # batch_size only in left, dropout only in right
    assert "batch_size" in data["left_only"]
    assert "dropout" in data["right_only"]


def test_compare_identical(client):
    t1 = _create_template(
        client,
        name="Same1",
        parameters={"a": 1, "b": 2},
    ).json()
    t2 = _create_template(
        client,
        name="Same2",
        parameters={"a": 1, "b": 2},
    ).json()

    resp = client.post(
        f"{PREFIX}/parameter-templates/compare",
        json={
            "left_type": "template",
            "left_id": t1["id"],
            "right_type": "template",
            "right_id": t2["id"],
        },
    )
    data = resp.json()
    assert all(not d["changed"] for d in data["diff"])
    assert data["left_only"] == []
    assert data["right_only"] == []


def test_compare_missing_template(client):
    t1 = _create_template(client, name="Exists").json()
    resp = client.post(
        f"{PREFIX}/parameter-templates/compare",
        json={
            "left_type": "template",
            "left_id": t1["id"],
            "right_type": "template",
            "right_id": "nonexistent-id",
        },
    )
    assert resp.status_code == 404
