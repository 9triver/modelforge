"""Tests for runtime.calibration (bias correction)."""
from __future__ import annotations

from pathlib import Path

import pytest

pd = pytest.importorskip("pandas")

from modelforge.runtime.calibration import (  # noqa: E402
    CalibrationResult,
    _ols_fit,
    calibrate_forecasting,
    generate_calibrated_repo,
)
from modelforge.runtime.tasks import ForecastingHandler  # noqa: E402


class PerfectHandler(ForecastingHandler):
    def predict(self, df):
        return pd.DataFrame({"timestamp": df["timestamp"], "prediction": df["load"]})


class BiasedHandler(ForecastingHandler):
    """pred = load * 1.1 + 5 (systematic bias)."""
    def predict(self, df):
        return pd.DataFrame({
            "timestamp": df["timestamp"],
            "prediction": df["load"] * 1.1 + 5,
        })


def _make_df(n: int = 100) -> pd.DataFrame:
    import datetime
    start = datetime.datetime(2024, 1, 1)
    return pd.DataFrame({
        "timestamp": pd.date_range(start, periods=n, freq="h"),
        "load": [50 + i * 0.1 for i in range(n)],
    })


class TestOlsFit:
    def test_identity(self):
        a, b = _ols_fit([1, 2, 3], [1, 2, 3])
        assert abs(a - 1.0) < 1e-6
        assert abs(b) < 1e-6

    def test_offset(self):
        a, b = _ols_fit([11, 12, 13], [1, 2, 3])
        assert abs(a - 1.0) < 1e-6
        assert abs(b - 10.0) < 1e-6

    def test_scale(self):
        a, b = _ols_fit([2, 4, 6], [1, 2, 3])
        assert abs(a - 2.0) < 1e-6
        assert abs(b) < 1e-6


class TestCalibrateForecasting:
    def test_perfect_handler_no_change(self):
        df = _make_df(50)
        handler = PerfectHandler("/fake")
        result = calibrate_forecasting(handler, df, "load")
        assert result.status == "ok"
        assert abs(result.params["a"] - 1.0) < 0.01
        assert abs(result.params["b"]) < 0.5

    def test_biased_handler_corrected(self):
        df = _make_df(100)
        handler = BiasedHandler("/fake")
        result = calibrate_forecasting(handler, df, "load")
        assert result.status == "ok"
        assert result.after_value < result.before_value

    def test_too_few_points(self):
        df = _make_df(2)
        handler = PerfectHandler("/fake")
        result = calibrate_forecasting(handler, df, "load")
        assert result.status == "error"
        assert "太少" in result.error


class TestGenerateCalibratedRepo:
    def test_creates_expected_files(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        (source / "README.md").write_text(
            "---\nlicense: mit\nlibrary_name: x\npipeline_tag: time-series-forecasting\n---\n# hi\n"
        )
        (source / "model.pkl").write_bytes(b"fake weights")

        result = CalibrationResult(
            params={"a": 1.05, "b": -2.3},
            before_metrics={"mape": 0.15, "rmse": 2.0, "mae": 1.5},
            after_metrics={"mape": 0.08, "rmse": 1.0, "mae": 0.7},
            before_value=0.15,
            after_value=0.08,
        )

        dest = tmp_path / "fork"
        generate_calibrated_repo(
            source_dir=source,
            result=result,
            source_repo="ns/base",
            source_revision="abc123",
            target_repo="chun/base-cal",
            data_hash="deadbeef",
            dest=dest,
        )

        assert (dest / "handler.py").is_file()
        assert (dest / "calibration.json").is_file()
        assert (dest / "README.md").is_file()
        assert (dest / "base_model" / "model.pkl").is_file()

        import json
        params = json.loads((dest / "calibration.json").read_text())
        assert params["a"] == 1.05
        assert params["b"] == -2.3

        readme = (dest / "README.md").read_text()
        assert "base_model: ns/base" in readme
        assert "0.0800" in readme
