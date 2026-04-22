"""Unit tests for runtime.docker_backend (mock subprocess.run, no real Docker)."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from modelforge.config import reset_settings
from modelforge.runtime.docker_backend import (
    _build_cmd,
    docker_calibrate,
    docker_evaluate,
)
from modelforge.schema import ModelCardMetadata


@pytest.fixture(autouse=True)
def _docker_settings(tmp_path: Path):
    reset_settings(
        data_dir=tmp_path / "data",
        eval_backend="docker",
        docker_timeout=60,
        docker_gpu=True,
    )
    yield
    reset_settings()


def _fc_metadata() -> ModelCardMetadata:
    return ModelCardMetadata(
        license="mit",
        library_name="dummy",
        pipeline_tag="time-series-forecasting",
        forecasting={"target": "load", "features": {"required": []}},
    )


def _ic_metadata() -> ModelCardMetadata:
    return ModelCardMetadata(
        license="mit",
        library_name="dummy",
        pipeline_tag="image-classification",
    )


class TestBuildCmd:
    def test_forecasting_no_gpu(self, tmp_path: Path):
        cmd = _build_cmd(
            container_name="mf-test",
            image="modelforge-runtime:timeseries",
            model_dir=tmp_path / "model",
            input_dir=tmp_path / "in",
            dataset_path=tmp_path / "data.csv",
            output_dir=tmp_path / "out",
            task="time-series-forecasting",
        )
        assert cmd[:3] == ["docker", "run", "--rm"]
        assert "--network" in cmd and "none" in cmd
        assert "--memory" in cmd
        assert "--gpus" not in cmd  # forecasting doesn't get GPU
        assert "modelforge-runtime:timeseries" in cmd
        # volume mounts
        joined = " ".join(cmd)
        assert ":/model:ro" in joined
        assert ":/input:ro" in joined
        assert ":/data:ro" in joined
        assert ":/output" in joined

    def test_vision_with_gpu(self, tmp_path: Path):
        cmd = _build_cmd(
            container_name="mf-test",
            image="modelforge-runtime:vision",
            model_dir=tmp_path / "model",
            input_dir=tmp_path / "in",
            dataset_path=tmp_path / "data.zip",
            output_dir=tmp_path / "out",
            task="image-classification",
        )
        assert "--gpus" in cmd
        idx = cmd.index("--gpus")
        assert cmd[idx + 1] == "all"

    def test_vision_no_gpu_when_disabled(self, tmp_path: Path):
        reset_settings(
            data_dir=tmp_path / "data",
            eval_backend="docker",
            docker_gpu=False,
        )
        cmd = _build_cmd(
            container_name="mf-test",
            image="modelforge-runtime:vision",
            model_dir=tmp_path / "model",
            input_dir=tmp_path / "in",
            dataset_path=tmp_path / "data.zip",
            output_dir=tmp_path / "out",
            task="image-classification",
        )
        assert "--gpus" not in cmd


class TestDockerEvaluate:
    def test_success_path(self, tmp_path: Path):
        model_dir = tmp_path / "model"
        model_dir.mkdir()
        ds = tmp_path / "data.csv"
        ds.write_text("timestamp,load\n2024-01-01,50\n")

        def fake_run(cmd, **kwargs):
            # find the -v {output_dir}:/output arg and write result there
            for i, arg in enumerate(cmd):
                if arg == "-v" and ":/output" in cmd[i + 1] and ":/output:ro" not in cmd[i + 1]:
                    host = cmd[i + 1].split(":/output")[0]
                    (Path(host) / "result.json").write_text(json.dumps({
                        "task": "time-series-forecasting",
                        "status": "ok",
                        "metrics": {"mape": 0.08},
                        "primary_metric": "mape",
                        "primary_value": 0.08,
                        "duration_ms": 100,
                    }))
                    break
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        with patch("modelforge.runtime.docker_backend.subprocess.run", side_effect=fake_run):
            result = docker_evaluate(model_dir, ds, _fc_metadata())

        assert result.status == "ok"
        assert result.primary_value == 0.08

    def test_timeout(self, tmp_path: Path):
        model_dir = tmp_path / "model"
        model_dir.mkdir()
        ds = tmp_path / "data.csv"
        ds.write_text("timestamp,load\n")

        def fake_run(cmd, **kwargs):
            if cmd[:2] == ["docker", "run"]:
                raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout", 0))
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        with patch("modelforge.runtime.docker_backend.subprocess.run", side_effect=fake_run):
            result = docker_evaluate(model_dir, ds, _fc_metadata())

        assert result.status == "error"
        assert "超时" in result.error

    def test_nonzero_exit(self, tmp_path: Path):
        model_dir = tmp_path / "model"
        model_dir.mkdir()
        ds = tmp_path / "data.csv"
        ds.write_text("timestamp,load\n")

        def fake_run(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="boom")

        with patch("modelforge.runtime.docker_backend.subprocess.run", side_effect=fake_run):
            result = docker_evaluate(model_dir, ds, _fc_metadata())

        assert result.status == "error"
        assert "docker backend" in result.error

    def test_vision_selects_vision_image(self, tmp_path: Path):
        model_dir = tmp_path / "model"
        model_dir.mkdir()
        ds = tmp_path / "data.zip"
        ds.write_text("")

        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            # simulate container failure so we don't need a result.json
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="")

        with patch("modelforge.runtime.docker_backend.subprocess.run", side_effect=fake_run):
            docker_evaluate(model_dir, ds, _ic_metadata())

        assert "modelforge-runtime:vision" in captured["cmd"]


class TestDockerCalibrate:
    def test_success_path(self, tmp_path: Path):
        model_dir = tmp_path / "model"
        model_dir.mkdir()
        ds = tmp_path / "data.csv"
        ds.write_text("timestamp,load\n2024-01-01,50\n")

        def fake_run(cmd, **kwargs):
            for i, arg in enumerate(cmd):
                if arg == "-v" and ":/output" in cmd[i + 1] and ":/output:ro" not in cmd[i + 1]:
                    host = cmd[i + 1].split(":/output")[0]
                    (Path(host) / "result.json").write_text(json.dumps({
                        "method": "linear_bias",
                        "params": {"a": 1.0, "b": 0.0},
                        "before_metrics": {"mape": 0.15},
                        "after_metrics": {"mape": 0.08},
                        "primary_metric": "mape",
                        "before_value": 0.15,
                        "after_value": 0.08,
                        "status": "ok",
                        "error": None,
                    }))
                    break
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        with patch("modelforge.runtime.docker_backend.subprocess.run", side_effect=fake_run):
            result = docker_calibrate(
                model_dir, ds, _fc_metadata(),
                method="linear_bias", target_col="load",
            )

        assert result.status == "ok"
        assert result.method == "linear_bias"
        assert result.after_value == 0.08

    def test_uses_timeseries_image(self, tmp_path: Path):
        model_dir = tmp_path / "model"
        model_dir.mkdir()
        ds = tmp_path / "data.csv"
        ds.write_text("")

        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="")

        with patch("modelforge.runtime.docker_backend.subprocess.run", side_effect=fake_run):
            docker_calibrate(
                model_dir, ds, _fc_metadata(),
                method="linear_bias", target_col="load",
            )

        assert "modelforge-runtime:timeseries" in captured["cmd"]
