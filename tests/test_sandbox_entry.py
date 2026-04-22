"""Unit tests for runtime.sandbox_entry (container entrypoint, no Docker needed)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pd = pytest.importorskip("pandas")

from modelforge.runtime.sandbox_entry import main  # noqa: E402


def _fc_metadata(target: str = "load") -> dict:
    return {
        "license": "mit",
        "library_name": "dummy",
        "pipeline_tag": "time-series-forecasting",
        "forecasting": {"target": target, "features": {"required": []}},
    }


def _write_handler(model_dir: Path, body: str) -> None:
    (model_dir / "handler.py").write_text(body)


def _fc_csv(path: Path, n: int = 50) -> None:
    import datetime
    rows = ["timestamp,load"]
    start = datetime.datetime(2024, 1, 1)
    for i in range(n):
        t = start + datetime.timedelta(hours=i)
        rows.append(f"{t.isoformat()},{50 + i * 0.1}")
    path.write_text("\n".join(rows))


class TestEvaluateMode:
    def test_success_roundtrip(self, tmp_path: Path):
        model_dir = tmp_path / "model"
        model_dir.mkdir()
        _write_handler(
            model_dir,
            "import pandas as pd\n"
            "from modelforge.runtime.tasks import ForecastingHandler\n"
            "class Handler(ForecastingHandler):\n"
            "    def predict(self, df):\n"
            "        return pd.DataFrame({'timestamp': df['timestamp'], 'prediction': df['load']})\n",
        )

        ds = tmp_path / "data.csv"
        _fc_csv(ds)

        input_dir = tmp_path / "input"
        input_dir.mkdir()
        (input_dir / "manifest.json").write_text(json.dumps({
            "mode": "evaluate",
            "model_dir": str(model_dir),
            "dataset_path": str(ds),
            "metadata": _fc_metadata(),
        }))

        output_dir = tmp_path / "output"
        main(
            manifest_path=str(input_dir / "manifest.json"),
            output_path=str(output_dir / "result.json"),
        )

        result = json.loads((output_dir / "result.json").read_text())
        assert result["status"] == "ok"
        assert result["primary_metric"] == "mape"
        assert result["primary_value"] is not None
        assert result["primary_value"] < 0.001  # perfect handler

    def test_unknown_mode_exits(self, tmp_path: Path):
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        (input_dir / "manifest.json").write_text(json.dumps({
            "mode": "bogus",
            "metadata": _fc_metadata(),
        }))
        output_dir = tmp_path / "output"
        with pytest.raises(SystemExit):
            main(
                manifest_path=str(input_dir / "manifest.json"),
                output_path=str(output_dir / "result.json"),
            )


class TestCalibrateMode:
    def test_calibrate_roundtrip(self, tmp_path: Path):
        model_dir = tmp_path / "model"
        model_dir.mkdir()
        _write_handler(
            model_dir,
            "import pandas as pd\n"
            "from modelforge.runtime.tasks import ForecastingHandler\n"
            "class Handler(ForecastingHandler):\n"
            "    def predict(self, df):\n"
            "        return pd.DataFrame({\n"
            "            'timestamp': df['timestamp'],\n"
            "            'prediction': df['load'] * 1.1 + 5,\n"
            "        })\n",
        )

        ds = tmp_path / "data.csv"
        _fc_csv(ds, n=100)

        input_dir = tmp_path / "input"
        input_dir.mkdir()
        (input_dir / "manifest.json").write_text(json.dumps({
            "mode": "calibrate",
            "model_dir": str(model_dir),
            "dataset_path": str(ds),
            "metadata": _fc_metadata(),
            "calibrate_method": "linear_bias",
            "target_col": "load",
        }))

        output_dir = tmp_path / "output"
        main(
            manifest_path=str(input_dir / "manifest.json"),
            output_path=str(output_dir / "result.json"),
        )

        result = json.loads((output_dir / "result.json").read_text())
        assert result["status"] == "ok"
        assert result["method"] == "linear_bias"
        assert result["after_value"] < result["before_value"]
