"""Dataset 管理测试：schema 校验、DB 迁移、CSV 预览。"""
from __future__ import annotations

import csv
import io
import json

import pytest

from modelforge import config, db
from modelforge.schema import (
    DatasetCardMetadata,
    ModelCardError,
    ModelCardMetadata,
    validate_model_card,
)


class TestDatasetSchema:
    def test_valid_dataset_card(self):
        content = (
            "---\nrepo_type: dataset\nlicense: mit\ndata_format: csv\n"
            "task_categories:\n  - time-series-forecasting\ntags:\n  - load\n"
            "---\n# My Dataset\n"
        )
        result = validate_model_card(content)
        assert isinstance(result, DatasetCardMetadata)
        assert result.repo_type == "dataset"
        assert result.license == "mit"
        assert result.data_format == "csv"
        assert result.task_categories == ["time-series-forecasting"]

    def test_dataset_no_library_name_ok(self):
        content = "---\nrepo_type: dataset\nlicense: apache-2.0\n---\n# DS\n"
        result = validate_model_card(content)
        assert isinstance(result, DatasetCardMetadata)
        assert result.license == "apache-2.0"

    def test_dataset_missing_license_fails(self):
        content = "---\nrepo_type: dataset\ndata_format: csv\n---\n# DS\n"
        with pytest.raises(ModelCardError, match="license"):
            validate_model_card(content)

    def test_model_card_still_works(self):
        content = "---\nlicense: mit\nlibrary_name: transformers\n---\n# M\n"
        result = validate_model_card(content)
        assert isinstance(result, ModelCardMetadata)
        assert result.library_name == "transformers"

    def test_model_card_without_repo_type(self):
        content = "---\nlicense: mit\nlibrary_name: lightgbm\n---\n# M\n"
        result = validate_model_card(content)
        assert isinstance(result, ModelCardMetadata)

    def test_dataset_image_folder(self):
        content = "---\nrepo_type: dataset\nlicense: cc-by-4.0\ndata_format: image_folder\nsize_category: 1K<n<10K\n---\n# I\n"
        result = validate_model_card(content)
        assert isinstance(result, DatasetCardMetadata)
        assert result.data_format == "image_folder"
        assert result.size_category == "1K<n<10K"


@pytest.fixture
def isolated_db(tmp_path):
    config.reset_settings(data_dir=tmp_path)
    yield
    config.reset_settings()


class TestDatasetDB:
    def test_repo_card_with_repo_type(self, isolated_db):
        user = db.create_user("ds_user")
        repo = db.create_repo("test_ds", "my-dataset", owner_id=user.id)
        card = db.RepoCard(
            repo_id=repo.id, revision="abc123",
            library_name=None, pipeline_tag=None, license="mit",
            tags_json=json.dumps(["load"]), base_model=None,
            best_metric_name=None, best_metric_value=None,
            updated_at="2024-01-01T00:00:00Z",
            repo_type="dataset", data_format="csv",
        )
        db.upsert_repo_card(card)
        fetched = db.get_repo_card(repo.id)
        assert fetched is not None
        assert fetched.repo_type == "dataset"
        assert fetched.data_format == "csv"

    def test_search_by_repo_type(self, isolated_db):
        user = db.create_user("ds_user2")
        repo = db.create_repo("ns", "ds1", owner_id=user.id)
        card = db.RepoCard(
            repo_id=repo.id, revision="abc",
            library_name=None, pipeline_tag=None, license="mit",
            tags_json=None, base_model=None,
            best_metric_name=None, best_metric_value=None,
            updated_at="2024-01-01T00:00:00Z",
            repo_type="dataset", data_format="csv",
        )
        db.upsert_repo_card(card)
        results = db.search_repos(repo_type="dataset")
        assert len(results) >= 1
        for _, c in results:
            if c:
                assert c.repo_type == "dataset"

    def test_search_excludes_other_type(self, isolated_db):
        user = db.create_user("ds_user3")
        r1 = db.create_repo("ns", "model1", owner_id=user.id)
        db.upsert_repo_card(db.RepoCard(
            repo_id=r1.id, revision="a", library_name="torch",
            pipeline_tag=None, license="mit", tags_json=None,
            base_model=None, best_metric_name=None, best_metric_value=None,
            updated_at="2024-01-01T00:00:00Z",
            repo_type="model", data_format=None,
        ))
        r2 = db.create_repo("ns", "ds2", owner_id=user.id)
        db.upsert_repo_card(db.RepoCard(
            repo_id=r2.id, revision="b", library_name=None,
            pipeline_tag=None, license="mit", tags_json=None,
            base_model=None, best_metric_name=None, best_metric_value=None,
            updated_at="2024-01-01T00:00:00Z",
            repo_type="dataset", data_format="csv",
        ))
        datasets = db.search_repos(repo_type="dataset")
        models = db.search_repos(repo_type="model")
        ds_names = {r.name for r, _ in datasets}
        m_names = {r.name for r, _ in models}
        assert "ds2" in ds_names
        assert "model1" not in ds_names
        assert "model1" in m_names


class TestCsvPreview:
    def test_csv_parsing(self):
        content = "timestamp,load\n2024-01-01,100\n2024-01-02,200\n"
        reader = csv.reader(io.StringIO(content))
        rows = list(reader)
        assert rows[0] == ["timestamp", "load"]
        assert len(rows[1:]) == 2
