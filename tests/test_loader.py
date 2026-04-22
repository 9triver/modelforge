"""Tests for modelforge.load() — mock ModelHub to avoid network."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from modelforge.loader import load
from modelforge.runtime.evaluator import HandlerLoadError


HANDLER_PY = """\
from modelforge.runtime.tasks import ForecastingHandler
import pandas as pd

class Handler(ForecastingHandler):
    def predict(self, df):
        return pd.DataFrame({"timestamp": df["timestamp"], "prediction": df["load"]})
"""

README_MD = """\
---
license: mit
library_name: dummy
pipeline_tag: time-series-forecasting
---
# Test
"""


def _make_model_dir(tmp_path: Path) -> Path:
    d = tmp_path / "snapshots" / "ns" / "m" / "main"
    d.mkdir(parents=True)
    (d / "handler.py").write_text(HANDLER_PY)
    (d / "README.md").write_text(README_MD)
    return d


class TestLoad:
    def test_returns_handler(self, tmp_path):
        model_dir = _make_model_dir(tmp_path)
        with patch("modelforge.loader.ModelHub") as MockHub:
            MockHub.return_value.snapshot_download.return_value = model_dir
            handler = load("ns/m", endpoint="http://fake:8000")
        assert handler.task == "time-series-forecasting"
        assert hasattr(handler, "predict")

    def test_missing_readme_raises(self, tmp_path):
        d = tmp_path / "snapshots" / "ns" / "m" / "main"
        d.mkdir(parents=True)
        (d / "handler.py").write_text(HANDLER_PY)
        with patch("modelforge.loader.ModelHub") as MockHub:
            MockHub.return_value.snapshot_download.return_value = d
            with pytest.raises(ValueError, match="缺少 README.md"):
                load("ns/m", endpoint="http://fake:8000")

    def test_missing_pipeline_tag_raises(self, tmp_path):
        d = tmp_path / "snapshots" / "ns" / "m" / "main"
        d.mkdir(parents=True)
        (d / "handler.py").write_text(HANDLER_PY)
        (d / "README.md").write_text("---\nlicense: mit\nlibrary_name: x\n---\n# hi\n")
        with patch("modelforge.loader.ModelHub") as MockHub:
            MockHub.return_value.snapshot_download.return_value = d
            with pytest.raises(ValueError, match="pipeline_tag 未声明"):
                load("ns/m", endpoint="http://fake:8000")

    def test_missing_handler_raises(self, tmp_path):
        d = tmp_path / "snapshots" / "ns" / "m" / "main"
        d.mkdir(parents=True)
        (d / "README.md").write_text(README_MD)
        with patch("modelforge.loader.ModelHub") as MockHub:
            MockHub.return_value.snapshot_download.return_value = d
            with pytest.raises(HandlerLoadError, match="缺少 handler.py"):
                load("ns/m", endpoint="http://fake:8000")

    def test_predict_works(self, tmp_path):
        import pandas as pd
        model_dir = _make_model_dir(tmp_path)
        with patch("modelforge.loader.ModelHub") as MockHub:
            MockHub.return_value.snapshot_download.return_value = model_dir
            handler = load("ns/m", endpoint="http://fake:8000")
        df = pd.DataFrame({"timestamp": ["2024-01-01"], "load": [42.0]})
        result = handler.predict(df)
        assert list(result.columns) == ["timestamp", "prediction"]
        assert result["prediction"].iloc[0] == 42.0
