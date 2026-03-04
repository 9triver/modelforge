PREFIX = "/api/v1"


def _create_feature(client, name="temperature", **overrides):
    data = {
        "name": name,
        "data_type": "float",
        "description": "环境温度",
        "unit": "celsius",
        "value_range": {"min": -40, "max": 50},
    }
    data.update(overrides)
    return client.post(f"{PREFIX}/features/definitions", json=data)


def test_create_feature_definition(client):
    resp = _create_feature(client)
    assert resp.status_code == 201
    assert resp.json()["name"] == "temperature"
    assert resp.json()["unit"] == "celsius"


def test_duplicate_feature(client):
    _create_feature(client, name="temperature")
    resp = _create_feature(client, name="temperature")
    assert resp.status_code == 409


def test_list_features(client):
    _create_feature(client, name="temperature")
    _create_feature(client, name="humidity", data_type="float", unit="percent")

    resp = client.get(f"{PREFIX}/features/definitions")
    assert len(resp.json()) == 2

    resp = client.get(f"{PREFIX}/features/definitions", params={"q": "temp"})
    assert len(resp.json()) == 1


def test_update_feature(client):
    fid = _create_feature(client).json()["id"]
    resp = client.put(f"{PREFIX}/features/definitions/{fid}", json={"unit": "fahrenheit"})
    assert resp.status_code == 200
    assert resp.json()["unit"] == "fahrenheit"


def test_delete_feature(client):
    fid = _create_feature(client).json()["id"]
    resp = client.delete(f"{PREFIX}/features/definitions/{fid}")
    assert resp.status_code == 204


# ── FeatureGroup ──


def _create_group(client, feature_ids, name="华东负荷预测特征集"):
    return client.post(
        f"{PREFIX}/features/groups",
        json={
            "name": name,
            "description": "华东地区标准特征集",
            "scenario_tags": {"region": "华东"},
            "feature_ids": feature_ids,
        },
    )


def test_create_feature_group(client):
    f1 = _create_feature(client, name="temperature").json()["id"]
    f2 = _create_feature(client, name="humidity").json()["id"]

    resp = _create_group(client, [f1, f2])
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "华东负荷预测特征集"
    assert len(data["features"]) == 2


def test_update_feature_group(client):
    f1 = _create_feature(client, name="temperature").json()["id"]
    f2 = _create_feature(client, name="humidity").json()["id"]
    f3 = _create_feature(client, name="hour", data_type="int").json()["id"]

    group_id = _create_group(client, [f1, f2]).json()["id"]

    resp = client.put(
        f"{PREFIX}/features/groups/{group_id}",
        json={"feature_ids": [f1, f2, f3]},
    )
    assert resp.status_code == 200
    assert len(resp.json()["features"]) == 3


# ── Model ↔ FeatureGroup ──


def test_model_feature_group_association(client):
    # Create model
    model_resp = client.post(
        f"{PREFIX}/models",
        json={
            "name": "测试模型",
            "task_type": "load_forecast",
            "algorithm_type": "GBR",
            "framework": "sklearn",
            "owner_org": "华东省公司",
        },
    )
    model_id = model_resp.json()["id"]

    # Create features and group
    f1 = _create_feature(client, name="temperature").json()["id"]
    group_id = _create_group(client, [f1]).json()["id"]

    # Associate
    resp = client.post(f"{PREFIX}/models/{model_id}/feature-groups/{group_id}")
    assert resp.status_code == 204

    # List
    resp = client.get(f"{PREFIX}/models/{model_id}/feature-groups")
    assert len(resp.json()) == 1
    assert resp.json()[0]["id"] == group_id

    # Disassociate
    resp = client.delete(f"{PREFIX}/models/{model_id}/feature-groups/{group_id}")
    assert resp.status_code == 204

    resp = client.get(f"{PREFIX}/models/{model_id}/feature-groups")
    assert len(resp.json()) == 0
