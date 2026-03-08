"""Tests for core abstraction layer and metadata-based lineage API."""

import io

import pytest

from modelforge.adapters.filesystem.artifact_store import (
    LocalArtifactStore,
)


# ── ArtifactStore Tests ──


@pytest.fixture
def artifact_store(tmp_path):
    return LocalArtifactStore(tmp_path / "artifacts")


class TestLocalArtifactStore:
    def test_put_and_get(self, artifact_store):
        data = b"model weights binary data"
        artifact_store.put(
            "models/test/weights/model.pkl",
            io.BytesIO(data),
        )
        with artifact_store.get(
            "models/test/weights/model.pkl",
        ) as f:
            assert f.read() == data

    def test_exists(self, artifact_store):
        assert not artifact_store.exists("missing/key")
        artifact_store.put_bytes("test/file.bin", b"hello")
        assert artifact_store.exists("test/file.bin")

    def test_delete(self, artifact_store):
        artifact_store.put_bytes("test/file.bin", b"hello")
        assert artifact_store.exists("test/file.bin")
        artifact_store.delete("test/file.bin")
        assert not artifact_store.exists("test/file.bin")

    def test_list_keys(self, artifact_store):
        artifact_store.put_bytes("dir/a.txt", b"a")
        artifact_store.put_bytes("dir/b.txt", b"b")
        artifact_store.put_bytes("other/c.txt", b"c")

        keys = artifact_store.list_keys("dir")
        assert len(keys) == 2
        assert any("a.txt" in k for k in keys)
        assert any("b.txt" in k for k in keys)

    def test_copy(self, artifact_store):
        artifact_store.put_bytes("src/file.bin", b"data")
        artifact_store.copy("src/file.bin", "dst/file.bin")
        assert artifact_store.get_bytes("dst/file.bin") == b"data"

    def test_get_local_path(self, artifact_store):
        artifact_store.put_bytes("test/f.bin", b"x")
        p = artifact_store.get_local_path("test/f.bin")
        assert p is not None
        assert p.exists()

    def test_get_local_path_missing(self, artifact_store):
        p = artifact_store.get_local_path("nonexistent")
        assert p is None

    def test_get_missing_raises(self, artifact_store):
        with pytest.raises(FileNotFoundError):
            artifact_store.get("no/such/key")

    def test_copy_tree(self, artifact_store):
        artifact_store.put_bytes("src/a.txt", b"a")
        artifact_store.put_bytes("src/sub/b.txt", b"b")
        artifact_store.copy_tree("src", "dst")
        assert artifact_store.get_bytes("dst/a.txt") == b"a"
        assert artifact_store.get_bytes("dst/sub/b.txt") == b"b"

    def test_remove_tree(self, artifact_store):
        artifact_store.put_bytes("dir/a.txt", b"a")
        artifact_store.put_bytes("dir/b.txt", b"b")
        artifact_store.remove_tree("dir")
        assert not artifact_store.exists("dir/a.txt")


# ── Metadata-based Lineage API Tests ──


def _create_model(client, name="test-model"):
    return client.post("/api/v1/models", json={
        "name": name,
        "description": "test",
        "task_type": "regression",
        "algorithm_type": "GradientBoosting",
        "framework": "sklearn",
        "owner_org": "test-org",
    })


def _upload_version(client, model_id, version="1.0.0"):
    return client.post(
        "/api/v1/models/" + model_id + "/versions",
        data={
            "version": version,
            "description": "v" + version,
            "file_format": "joblib",
        },
        files={
            "file": ("model.joblib", b"fake-weights", "application/octet-stream"),
        },
    )


class TestLineageAPI:
    def test_version_provenance(self, client):
        model = _create_model(client).json()
        mid = model["id"]
        ver = _upload_version(client, mid).json()
        vid = ver["id"]

        resp = client.get(
            "/api/v1/lineage/versions/"
            + mid + "/" + vid,
        )
        assert resp.status_code == 200
        prov = resp.json()
        assert prov["version_id"] == vid
        assert prov["model_id"] == mid
        assert "artifacts" in prov
        assert "datasets" in prov["artifacts"]

    def test_upstream_single_version(self, client):
        model = _create_model(client).json()
        mid = model["id"]
        ver = _upload_version(client, mid).json()
        vid = ver["id"]

        resp = client.get(
            "/api/v1/lineage/upstream/"
            + mid + "/" + vid,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["version_id"] == vid
        assert len(data["chain"]) == 1
        assert data["chain"][0]["version_id"] == vid

    def test_upstream_with_parent(self, client):
        model = _create_model(client).json()
        mid = model["id"]

        v1 = _upload_version(client, mid, "1.0.0").json()

        v2 = client.post(
            "/api/v1/models/" + mid + "/versions",
            data={
                "version": "2.0.0",
                "description": "child",
                "file_format": "joblib",
                "parent_version_id": v1["id"],
            },
            files={
                "file": (
                    "model.joblib",
                    b"fake-weights-v2",
                    "application/octet-stream",
                ),
            },
        ).json()

        resp = client.get(
            "/api/v1/lineage/upstream/"
            + mid + "/" + v2["id"],
        )
        assert resp.status_code == 200
        chain = resp.json()["chain"]
        assert len(chain) == 2
        assert chain[0]["version_id"] == v2["id"]
        assert chain[1]["version_id"] == v1["id"]

    def test_diff_versions(self, client):
        model = _create_model(client).json()
        mid = model["id"]

        v1 = _upload_version(client, mid, "1.0.0").json()
        v2 = _upload_version(client, mid, "2.0.0").json()

        resp = client.get(
            "/api/v1/lineage/diff/" + mid,
            params={
                "version_a": v1["id"],
                "version_b": v2["id"],
            },
        )
        assert resp.status_code == 200
        diff = resp.json()
        assert diff["version_a"]["version_id"] == v1["id"]
        assert diff["version_b"]["version_id"] == v2["id"]
        assert "artifact_diff" in diff
        assert "metric_diff" in diff
