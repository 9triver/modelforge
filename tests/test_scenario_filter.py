def _create_model(client, **overrides):
    data = {
        "name": "测试模型",
        "description": "测试",
        "task_type": "load_forecast",
        "algorithm_type": "XGBoost",
        "framework": "sklearn",
        "owner_org": "测试单位",
        "applicable_scenarios": {"region": ["华东"], "season": ["all"]},
    }
    data.update(overrides)
    return client.post("/api/v1/models", json=data)


def test_filter_by_region(client):
    _create_model(client, name="华东模型", applicable_scenarios={"region": ["华东"]})
    _create_model(client, name="华北模型", applicable_scenarios={"region": ["华北"]})

    resp = client.get("/api/v1/models", params={"region": "华东"})
    assert resp.status_code == 200
    names = [m["name"] for m in resp.json()]
    assert "华东模型" in names
    assert "华北模型" not in names


def test_filter_by_season(client):
    _create_model(client, name="全季节模型", applicable_scenarios={"season": ["all"]})
    _create_model(client, name="夏季模型", applicable_scenarios={"season": ["summer"]})

    # "all" should match any season filter
    resp = client.get("/api/v1/models", params={"season": "winter"})
    names = [m["name"] for m in resp.json()]
    assert "全季节模型" in names
    assert "夏季模型" not in names

    resp = client.get("/api/v1/models", params={"season": "summer"})
    names = [m["name"] for m in resp.json()]
    assert "全季节模型" in names
    assert "夏季模型" in names


def test_filter_combined(client):
    _create_model(
        client,
        name="华东负荷",
        task_type="load_forecast",
        applicable_scenarios={"region": ["华东"]},
    )
    _create_model(
        client,
        name="华东异常",
        task_type="anomaly_detection",
        applicable_scenarios={"region": ["华东"]},
    )
    _create_model(
        client,
        name="华北负荷",
        task_type="load_forecast",
        applicable_scenarios={"region": ["华北"]},
    )

    resp = client.get(
        "/api/v1/models", params={"region": "华东", "task_type": "load_forecast"}
    )
    names = [m["name"] for m in resp.json()]
    assert names == ["华东负荷"]


def test_filter_no_scenarios(client):
    _create_model(client, name="无场景模型", applicable_scenarios=None)
    _create_model(client, name="有场景模型", applicable_scenarios={"region": ["华东"]})

    resp = client.get("/api/v1/models", params={"region": "华东"})
    names = [m["name"] for m in resp.json()]
    assert "有场景模型" in names
    assert "无场景模型" not in names
