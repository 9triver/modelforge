"""Tests for db.Evaluation CRUD + aggregate."""
from __future__ import annotations

import json

import pytest

from modelforge import config, db


@pytest.fixture
def isolated_db(tmp_path):
    config.reset_settings(data_dir=tmp_path)
    yield
    config.reset_settings()


def _make_repo() -> int:
    user = db.create_user("alice")
    repo = db.create_repo("alice", "test-repo", owner_id=user.id)
    return repo.id


class TestEvaluationCrud:
    def test_create_and_get(self, isolated_db):
        repo_id = _make_repo()
        rec = db.create_evaluation(repo_id, "abc123", "time-series-forecasting")
        assert rec.id > 0
        assert rec.status == "queued"
        assert rec.metrics_json is None

        got = db.get_evaluation(rec.id)
        assert got.task == "time-series-forecasting"
        assert got.status == "queued"

    def test_update_to_ok(self, isolated_db):
        repo_id = _make_repo()
        rec = db.create_evaluation(repo_id, "abc", "time-series-forecasting")
        db.update_evaluation(
            rec.id,
            status="ok",
            metrics_json=json.dumps({"mape": 0.08, "rmse": 1.2}),
            primary_metric="mape",
            primary_value=0.08,
            duration_ms=123,
        )
        got = db.get_evaluation(rec.id)
        assert got.status == "ok"
        assert got.primary_value == 0.08
        assert json.loads(got.metrics_json)["rmse"] == 1.2

    def test_update_to_error(self, isolated_db):
        repo_id = _make_repo()
        rec = db.create_evaluation(repo_id, "abc", "image-classification")
        db.update_evaluation(rec.id, status="error", error="handler crashed")
        got = db.get_evaluation(rec.id)
        assert got.status == "error"
        assert got.error == "handler crashed"

    def test_get_missing(self, isolated_db):
        assert db.get_evaluation(99999) is None


class TestAggregate:
    def test_empty(self, isolated_db):
        repo_id = _make_repo()
        agg = db.aggregate_repo_metrics(repo_id)
        assert agg["count"] == 0
        assert agg["metric"] is None
        assert agg["median"] is None

    def test_single(self, isolated_db):
        repo_id = _make_repo()
        rec = db.create_evaluation(repo_id, "x", "time-series-forecasting")
        db.update_evaluation(rec.id, status="ok", primary_metric="mape", primary_value=0.1)
        agg = db.aggregate_repo_metrics(repo_id)
        assert agg["count"] == 1
        assert agg["median"] == 0.1
        assert agg["p25"] == 0.1 and agg["p75"] == 0.1

    def test_multiple_quartiles(self, isolated_db):
        repo_id = _make_repo()
        for v in [0.1, 0.2, 0.3, 0.4, 0.5]:
            rec = db.create_evaluation(repo_id, "x", "time-series-forecasting")
            db.update_evaluation(
                rec.id, status="ok", primary_metric="mape", primary_value=v
            )
        agg = db.aggregate_repo_metrics(repo_id)
        assert agg["count"] == 5
        assert agg["median"] == pytest.approx(0.3)
        assert agg["p25"] == pytest.approx(0.2)
        assert agg["p75"] == pytest.approx(0.4)

    def test_skips_failed_evals(self, isolated_db):
        repo_id = _make_repo()
        rec1 = db.create_evaluation(repo_id, "x", "tsf")
        db.update_evaluation(rec1.id, status="ok", primary_metric="mape", primary_value=0.1)
        rec2 = db.create_evaluation(repo_id, "x", "tsf")
        db.update_evaluation(rec2.id, status="error", error="boom")
        agg = db.aggregate_repo_metrics(repo_id)
        assert agg["count"] == 1
