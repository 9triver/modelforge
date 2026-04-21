"""Unit tests for runtime.datasets."""
from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

pd = pytest.importorskip("pandas")
PIL_Image = pytest.importorskip("PIL.Image")

from modelforge.runtime.datasets import forecasting, image_classification  # noqa: E402


class TestForecasting:
    def test_load_csv_sorts_and_parses(self, tmp_path: Path):
        csv = tmp_path / "data.csv"
        csv.write_text(
            "timestamp,load,temp\n"
            "2024-01-02 00:00,11,21\n"
            "2024-01-01 00:00,10,20\n"
        )
        df = forecasting.load_forecasting_csv(
            csv, target_col="load", required_features=["temp"]
        )
        assert list(df["load"]) == [10, 11]
        assert pd.api.types.is_datetime64_any_dtype(df["timestamp"])

    def test_missing_target_raises(self, tmp_path: Path):
        csv = tmp_path / "x.csv"
        csv.write_text("timestamp,load\n2024-01-01,1\n")
        with pytest.raises(forecasting.DatasetError, match="缺少目标列"):
            forecasting.load_forecasting_csv(csv, target_col="power")

    def test_missing_feature_raises(self, tmp_path: Path):
        csv = tmp_path / "x.csv"
        csv.write_text("timestamp,load\n2024-01-01,1\n")
        with pytest.raises(forecasting.DatasetError, match="缺少必需特征列"):
            forecasting.load_forecasting_csv(
                csv, target_col="load", required_features=["temp"]
            )

    def test_bad_timestamp(self, tmp_path: Path):
        csv = tmp_path / "x.csv"
        csv.write_text("timestamp,load\nnot-a-date,1\n")
        with pytest.raises(forecasting.DatasetError, match="无法解析为时间"):
            forecasting.load_forecasting_csv(csv, target_col="load")

    def test_unsupported_suffix(self, tmp_path: Path):
        p = tmp_path / "data.txt"
        p.write_text("x")
        with pytest.raises(forecasting.DatasetError, match="不支持的文件格式"):
            forecasting.load_forecasting_csv(p, target_col="load")


class TestImageClassification:
    def _make_folder(self, root: Path) -> None:
        for cls in ("cat", "dog"):
            d = root / cls
            d.mkdir()
            for i in range(2):
                img = PIL_Image.new("RGB", (4, 4), color=(i * 40, 0, 0))
                img.save(d / f"{i}.png")

    def test_iter_image_folder(self, tmp_path: Path):
        self._make_folder(tmp_path)
        items = list(image_classification.iter_image_folder(tmp_path))
        assert len(items) == 4
        labels = [label for _, label in items]
        assert labels == ["cat", "cat", "dog", "dog"]

    def test_load_image_folder(self, tmp_path: Path):
        self._make_folder(tmp_path)
        imgs, labels = image_classification.load_image_folder(tmp_path)
        assert len(imgs) == 4 and len(labels) == 4

    def test_empty_folder_raises(self, tmp_path: Path):
        with pytest.raises(image_classification.DatasetError, match="没有类别子目录"):
            image_classification.load_image_folder(tmp_path)

    def test_unpack_zip_strips_single_top_dir(self, tmp_path: Path):
        # zip 内含 root/cat/0.png root/dog/0.png
        src = tmp_path / "src"
        (src / "root" / "cat").mkdir(parents=True)
        (src / "root" / "dog").mkdir(parents=True)
        PIL_Image.new("RGB", (4, 4)).save(src / "root" / "cat" / "0.png")
        PIL_Image.new("RGB", (4, 4)).save(src / "root" / "dog" / "0.png")

        zip_path = tmp_path / "data.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            for p in (src / "root").rglob("*"):
                zf.write(p, arcname=str(p.relative_to(src)))

        extract_dir = tmp_path / "out"
        result = image_classification.unpack_zip(zip_path, extract_dir)
        assert result.name == "root"
        imgs, labels = image_classification.load_image_folder(result)
        assert len(imgs) == 2
        assert set(labels) == {"cat", "dog"}

    def test_unpack_zip_rejects_slip(self, tmp_path: Path):
        # writestr 会规范化路径，需要手动构造 ZipInfo 保留 ../
        zip_path = tmp_path / "evil.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            info = zipfile.ZipInfo(filename="../../outside.txt")
            zf.writestr(info, b"x")
        with pytest.raises(image_classification.DatasetError, match="zip-slip"):
            image_classification.unpack_zip(zip_path, tmp_path / "out")
