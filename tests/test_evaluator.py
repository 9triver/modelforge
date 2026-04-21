"""Unit tests for runtime.evaluator (in-process backend, mock handlers)."""
from __future__ import annotations

from pathlib import Path

import pytest

pd = pytest.importorskip("pandas")
PIL_Image = pytest.importorskip("PIL.Image")

from modelforge.runtime import evaluate  # noqa: E402
from modelforge.runtime.evaluator import HandlerLoadError, load_handler  # noqa: E402
from modelforge.schema import ModelCardMetadata  # noqa: E402


# ---------- helpers ----------


def _write_handler(model_dir: Path, body: str) -> None:
    (model_dir / "handler.py").write_text(body)


def _fc_metadata(target: str = "load") -> ModelCardMetadata:
    return ModelCardMetadata(
        license="mit",
        library_name="dummy",
        pipeline_tag="time-series-forecasting",
        forecasting={"target": target, "features": {"required": []}},
    )


def _ic_metadata() -> ModelCardMetadata:
    return ModelCardMetadata(
        license="mit",
        library_name="dummy",
        pipeline_tag="image-classification",
    )


# ---------- handler loading ----------


class TestLoadHandler:
    def test_missing_handler_file(self, tmp_path: Path):
        with pytest.raises(HandlerLoadError, match="缺少 handler.py"):
            load_handler(tmp_path, "time-series-forecasting")

    def test_missing_handler_class(self, tmp_path: Path):
        _write_handler(tmp_path, "x = 1\n")
        with pytest.raises(HandlerLoadError, match="必须定义名为 'Handler'"):
            load_handler(tmp_path, "time-series-forecasting")

    def test_wrong_base_class(self, tmp_path: Path):
        _write_handler(
            tmp_path,
            "from modelforge.runtime.tasks import ImageClassificationHandler\n"
            "class Handler(ImageClassificationHandler):\n"
            "    def predict(self, x): return []\n",
        )
        with pytest.raises(HandlerLoadError, match="必须继承"):
            load_handler(tmp_path, "time-series-forecasting")

    def test_import_error_propagates(self, tmp_path: Path):
        _write_handler(tmp_path, "raise RuntimeError('boom')\n")
        with pytest.raises(HandlerLoadError, match="导入失败"):
            load_handler(tmp_path, "time-series-forecasting")


# ---------- forecasting end-to-end ----------


PERFECT_FC_HANDLER = """
import pandas as pd
from modelforge.runtime.tasks import ForecastingHandler

class Handler(ForecastingHandler):
    def predict(self, df):
        return pd.DataFrame({"timestamp": df["timestamp"], "prediction": df["load"]})
"""

OFFSET_FC_HANDLER = """
import pandas as pd
from modelforge.runtime.tasks import ForecastingHandler

class Handler(ForecastingHandler):
    def predict(self, df):
        return pd.DataFrame({"timestamp": df["timestamp"], "prediction": df["load"] + 1.0})
"""

BAD_OUTPUT_FC_HANDLER = """
import pandas as pd
from modelforge.runtime.tasks import ForecastingHandler

class Handler(ForecastingHandler):
    def predict(self, df):
        return pd.DataFrame({"ts": df["timestamp"], "y_hat": df["load"]})
"""


class TestForecastingEval:
    def _make_csv(self, tmp_path: Path) -> Path:
        csv = tmp_path / "data.csv"
        csv.write_text(
            "timestamp,load\n"
            "2024-01-01 00:00,10\n"
            "2024-01-01 01:00,20\n"
            "2024-01-01 02:00,30\n"
            "2024-01-01 03:00,40\n"
        )
        return csv

    def test_perfect_prediction(self, tmp_path: Path):
        model_dir = tmp_path / "model"; model_dir.mkdir()
        _write_handler(model_dir, PERFECT_FC_HANDLER)
        csv = self._make_csv(tmp_path)

        result = evaluate(model_dir, csv, _fc_metadata())
        assert result.status == "ok"
        assert result.task == "time-series-forecasting"
        assert result.primary_metric == "mape"
        assert result.primary_value == 0.0
        assert result.metrics["mae"] == 0.0
        assert result.duration_ms >= 0

    def test_offset_prediction(self, tmp_path: Path):
        model_dir = tmp_path / "model"; model_dir.mkdir()
        _write_handler(model_dir, OFFSET_FC_HANDLER)
        csv = self._make_csv(tmp_path)

        result = evaluate(model_dir, csv, _fc_metadata())
        assert result.status == "ok"
        assert result.metrics["mae"] == pytest.approx(1.0)
        # mape: mean(1/10, 1/20, 1/30, 1/40)
        assert result.primary_value == pytest.approx(
            (1/10 + 1/20 + 1/30 + 1/40) / 4
        )

    def test_bad_output_columns(self, tmp_path: Path):
        model_dir = tmp_path / "model"; model_dir.mkdir()
        _write_handler(model_dir, BAD_OUTPUT_FC_HANDLER)
        csv = self._make_csv(tmp_path)

        result = evaluate(model_dir, csv, _fc_metadata())
        assert result.status == "error"
        assert "timestamp" in result.error and "prediction" in result.error

    def test_unknown_task(self, tmp_path: Path):
        result = evaluate(
            tmp_path,
            tmp_path / "x",
            ModelCardMetadata(license="mit", library_name="x", pipeline_tag="nope"),
        )
        assert result.status == "error"
        assert "不支持" in result.error


# ---------- image-classification end-to-end ----------


PERFECT_IC_HANDLER = """
from modelforge.runtime.tasks import ImageClassificationHandler

class Handler(ImageClassificationHandler):
    # 训练数据按颜色编码 label：在测试里我们让 setup 把文件名当 label
    # mock：直接用每张图的 mode 做"预测"，对所有图都返回固定 label
    def __init__(self, model_dir):
        super().__init__(model_dir)
        self._fixed = "cat"
    def set_fixed(self, label):
        self._fixed = label
    def predict(self, images):
        return [[{"label": self._fixed, "score": 1.0}] for _ in images]
"""


class TestImageClassificationEval:
    def _make_folder(self, tmp_path: Path, classes=("cat", "dog"), per_class=2) -> Path:
        tmp_path.mkdir(parents=True, exist_ok=True)
        for cls in classes:
            d = tmp_path / cls; d.mkdir()
            for i in range(per_class):
                PIL_Image.new("RGB", (4, 4)).save(d / f"{i}.png")
        return tmp_path

    def test_constant_label(self, tmp_path: Path):
        model_dir = tmp_path / "model"; model_dir.mkdir()
        _write_handler(model_dir, PERFECT_IC_HANDLER)
        data = self._make_folder(tmp_path / "data")

        result = evaluate(model_dir, data, _ic_metadata())
        assert result.status == "ok"
        # 预测全 "cat"，2 张 cat + 2 张 dog → accuracy = 0.5
        assert result.primary_metric == "accuracy"
        assert result.primary_value == 0.5

    def test_zip_input(self, tmp_path: Path):
        import zipfile
        data = self._make_folder(tmp_path / "data")
        zip_path = tmp_path / "data.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            for p in data.rglob("*"):
                if p.is_file():
                    zf.write(p, arcname=str(p.relative_to(data.parent)))

        model_dir = tmp_path / "model"; model_dir.mkdir()
        _write_handler(model_dir, PERFECT_IC_HANDLER)

        result = evaluate(model_dir, zip_path, _ic_metadata())
        assert result.status == "ok"
        assert result.primary_value == 0.5
