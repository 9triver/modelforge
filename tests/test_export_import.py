import io
import json
import zipfile

PREFIX = "/api/v1"


def _create_model(client, name="导出测试模型", **overrides):
    data = {
        "name": name,
        "task_type": "load_forecast",
        "algorithm_type": "GradientBoosting",
        "framework": "sklearn",
        "owner_org": "华东省公司",
    }
    data.update(overrides)
    return client.post(f"{PREFIX}/models", json=data)


def _upload_version(client, model_id, version="1.0.0"):
    return client.post(
        f"{PREFIX}/models/{model_id}/versions",
        data={
            "version": version,
            "file_format": "joblib",
            "metrics": json.dumps({"mae": 12.5}),
            "description": "Test version",
        },
        files={"file": ("model.joblib", io.BytesIO(b"fake model"), "application/octet-stream")},
    )


def test_export_model(client):
    model_id = _create_model(client).json()["id"]
    _upload_version(client, model_id, "1.0.0")

    resp = client.post(
        f"{PREFIX}/models/{model_id}/export",
        json={},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"

    # Verify ZIP contents
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    names = zf.namelist()
    assert "model.yaml" in names
    assert "manifest.json" in names
    # Should have version files
    assert any("versions/v1.0.0/" in n for n in names)

    manifest = json.loads(zf.read("manifest.json"))
    assert manifest["source_model_id"] == model_id
    assert manifest["format_version"] == "1.0"
    assert len(manifest["versions_included"]) == 1


def test_export_selected_versions(client):
    model_id = _create_model(client).json()["id"]
    _upload_version(client, model_id, "1.0.0")
    v2 = _upload_version(client, model_id, "2.0.0").json()

    # Export only v2
    resp = client.post(
        f"{PREFIX}/models/{model_id}/export",
        json={"version_ids": [v2["id"]]},
    )
    assert resp.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    names = zf.namelist()
    assert any("versions/v2.0.0/" in n for n in names)
    assert not any("versions/v1.0.0/" in n for n in names)


def test_import_model(client):
    # Create and export
    model_id = _create_model(client, name="源模型").json()["id"]
    _upload_version(client, model_id, "1.0.0")

    export_resp = client.post(f"{PREFIX}/models/{model_id}/export", json={})
    assert export_resp.status_code == 200

    # Import
    import_resp = client.post(
        f"{PREFIX}/models/import",
        files={"file": ("export.zip", io.BytesIO(export_resp.content), "application/zip")},
        data={"new_name": "导入模型"},
    )
    assert import_resp.status_code == 201
    data = import_resp.json()
    assert data["name"] == "导入模型"
    assert data["id"] != model_id
    assert data["imported_from"]["source_model_id"] == model_id

    # Verify imported model has versions
    versions = client.get(f"{PREFIX}/models/{data['id']}/versions").json()
    assert len(versions) == 1


def test_import_name_collision(client):
    # Create model with specific name
    model_id = _create_model(client, name="冲突模型").json()["id"]
    _upload_version(client, model_id, "1.0.0")

    export_resp = client.post(f"{PREFIX}/models/{model_id}/export", json={})

    # Import without new_name — should use suggested_name with "导入" suffix
    preview_resp = client.post(
        f"{PREFIX}/models/import/preview",
        files={"file": ("export.zip", io.BytesIO(export_resp.content), "application/zip")},
    )
    assert preview_resp.status_code == 200
    preview = preview_resp.json()
    assert preview["name_collision"] is True
    assert "导入" in preview["suggested_name"]


def test_import_preview(client):
    model_id = _create_model(client, name="预览模型").json()["id"]
    _upload_version(client, model_id, "1.0.0")
    _upload_version(client, model_id, "2.0.0")

    export_resp = client.post(f"{PREFIX}/models/{model_id}/export", json={})

    preview_resp = client.post(
        f"{PREFIX}/models/import/preview",
        files={"file": ("export.zip", io.BytesIO(export_resp.content), "application/zip")},
    )
    assert preview_resp.status_code == 200
    data = preview_resp.json()
    assert data["model_name"] == "预览模型"
    assert data["algorithm_type"] == "GradientBoosting"
    assert len(data["versions"]) == 2
    # Source model still exists, so name collision is expected
    assert data["name_collision"] is True
    assert "导入" in data["suggested_name"]


def test_roundtrip(client):
    """Export -> Import -> verify all artifacts preserved."""
    model_id = _create_model(client, name="往返模型").json()["id"]
    v_resp = _upload_version(client, model_id, "1.0.0")
    version_id = v_resp.json()["id"]

    # Upload an artifact to params
    client.post(
        f"{PREFIX}/models/{model_id}/versions/{version_id}/artifacts/params",
        files={"file": ("training_params.yaml", io.BytesIO(b"lr: 0.01\nepochs: 100"), "application/x-yaml")},
    )

    # Export
    export_resp = client.post(f"{PREFIX}/models/{model_id}/export", json={})
    assert export_resp.status_code == 200

    # Import
    import_resp = client.post(
        f"{PREFIX}/models/import",
        files={"file": ("export.zip", io.BytesIO(export_resp.content), "application/zip")},
        data={"new_name": "往返导入"},
    )
    assert import_resp.status_code == 201
    new_model_id = import_resp.json()["id"]

    # Verify versions
    versions = client.get(f"{PREFIX}/models/{new_model_id}/versions").json()
    assert len(versions) == 1
    new_version_id = versions[0]["id"]

    # Verify artifact preserved
    artifacts = client.get(f"{PREFIX}/models/{new_model_id}/versions/{new_version_id}/artifacts/params").json()
    param_files = [a["name"] for a in artifacts]
    assert "training_params.yaml" in param_files
