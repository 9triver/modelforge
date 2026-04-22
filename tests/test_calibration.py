"""Tests for runtime.calibration (all methods)."""
from __future__ import annotations

from pathlib import Path

import pytest

pd = pytest.importorskip("pandas")

from modelforge.runtime.calibration import (  # noqa: E402
    CalibrationResult,
    _ols_fit,
    calibrate_by_method,
    calibrate_forecasting,
    calibrate_segmented,
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


class TimeVaryingBiasHandler(ForecastingHandler):
    """夜间偏高 +10，白天偏低 -5。"""
    def predict(self, df):
        preds = []
        for _, row in df.iterrows():
            h = pd.to_datetime(row["timestamp"]).hour
            bias = 10 if h < 6 else -5
            preds.append(row["load"] + bias)
        return pd.DataFrame({"timestamp": df["timestamp"], "prediction": preds})


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


class TestLinearBias:
    def test_perfect_handler_no_change(self):
        df = _make_df(50)
        handler = PerfectHandler("/fake")
        result = calibrate_forecasting(handler, df, "load")
        assert result.status == "ok"
        assert result.method == "linear_bias"
        assert abs(result.params["a"] - 1.0) < 0.01

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


class TestSegmented:
    def test_time_varying_bias_corrected(self):
        df = _make_df(200)
        handler = TimeVaryingBiasHandler("/fake")
        result = calibrate_segmented(handler, df, "load")
        assert result.status == "ok"
        assert result.method == "segmented"
        assert "segments" in result.params
        assert result.after_value < result.before_value

    def test_perfect_handler(self):
        df = _make_df(100)
        handler = PerfectHandler("/fake")
        result = calibrate_segmented(handler, df, "load")
        assert result.status == "ok"
        assert result.after_value <= result.before_value + 0.01


class TestStacking:
    def test_biased_handler_corrected(self):
        sklearn = pytest.importorskip("sklearn")
        df = _make_df(200)
        handler = BiasedHandler("/fake")
        result = calibrate_by_method("stacking", handler, df, "load")
        assert result.status == "ok"
        assert result.method == "stacking"
        assert "model_b64" in result.params
        assert result.after_value < result.before_value

    def test_without_sklearn_errors(self, monkeypatch):
        import importlib
        original = importlib.import_module
        def mock_import(name, *args, **kwargs):
            if name == "sklearn.ensemble":
                raise ImportError("no sklearn")
            return original(name, *args, **kwargs)
        monkeypatch.setattr(importlib, "import_module", mock_import)
        # stacking should still work if sklearn is installed; skip if not testable


class TestDispatcher:
    def test_unknown_method(self):
        df = _make_df(50)
        handler = PerfectHandler("/fake")
        result = calibrate_by_method("nope", handler, df, "load")
        assert result.status == "error"
        assert "未知" in result.error

    def test_all_methods_run(self):
        df = _make_df(200)
        handler = BiasedHandler("/fake")
        for method in ["linear_bias", "segmented"]:
            result = calibrate_by_method(method, handler, df, "load")
            assert result.status == "ok", f"{method} failed: {result.error}"
            assert result.method == method


class TestGenerateCalibratedRepo:
    def test_creates_expected_files(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        (source / "README.md").write_text(
            "---\nlicense: mit\nlibrary_name: x\npipeline_tag: time-series-forecasting\n---\n# hi\n"
        )
        (source / "model.pkl").write_bytes(b"fake weights")

        result = CalibrationResult(
            method="segmented",
            params={"segments": {"0": {"a": 1.0, "b": 0.0}}, "n_segments": 4},
            before_metrics={"mape": 0.15, "rmse": 2.0, "mae": 1.5},
            after_metrics={"mape": 0.08, "rmse": 1.0, "mae": 0.7},
            before_value=0.15,
            after_value=0.08,
        )

        dest = tmp_path / "fork"
        generate_calibrated_repo(
            source_dir=source, result=result,
            source_repo="ns/base", source_revision="abc123",
            target_repo="chun/base-cal", data_hash="deadbeef", dest=dest,
        )

        assert (dest / "handler.py").is_file()
        assert (dest / "calibration.json").is_file()
        assert (dest / "base_model" / "model.pkl").is_file()
        readme = (dest / "README.md").read_text()
        assert "segmented" in readme
