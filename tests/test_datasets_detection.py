"""Tests for runtime.datasets.object_detection (COCO loader)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

PIL_Image = pytest.importorskip("PIL.Image")

from modelforge.runtime.datasets.object_detection import (  # noqa: E402
    DatasetError,
    load_coco_dataset,
)


def _make_coco_dataset(root: Path, n_images: int = 3) -> None:
    images_dir = root / "images"
    images_dir.mkdir(parents=True)

    img_entries = []
    ann_entries = []
    ann_id = 1
    for i in range(n_images):
        fname = f"{i:06d}.jpg"
        PIL_Image.new("RGB", (100, 80)).save(images_dir / fname)
        img_entries.append({"id": i + 1, "file_name": fname, "width": 100, "height": 80})
        ann_entries.append({
            "id": ann_id,
            "image_id": i + 1,
            "category_id": 1,
            "bbox": [10, 10, 30, 30],
            "area": 900,
            "iscrowd": 0,
        })
        ann_id += 1

    coco = {
        "images": img_entries,
        "annotations": ann_entries,
        "categories": [{"id": 1, "name": "cat"}],
    }
    (root / "annotations.json").write_text(json.dumps(coco))


class TestLoadCocoDataset:
    def test_loads_correctly(self, tmp_path):
        _make_coco_dataset(tmp_path, 3)
        images, ids, coco_dict = load_coco_dataset(tmp_path)
        assert len(images) == 3
        assert ids == [1, 2, 3]
        assert len(coco_dict["annotations"]) == 3

    def test_missing_annotations_raises(self, tmp_path):
        tmp_path.mkdir(exist_ok=True)
        with pytest.raises(DatasetError, match="缺少 annotations.json"):
            load_coco_dataset(tmp_path)

    def test_missing_image_raises(self, tmp_path):
        coco = {
            "images": [{"id": 1, "file_name": "nope.jpg", "width": 10, "height": 10}],
            "annotations": [],
            "categories": [],
        }
        (tmp_path / "annotations.json").write_text(json.dumps(coco))
        with pytest.raises(DatasetError, match="图片不存在"):
            load_coco_dataset(tmp_path)

    def test_bad_json_raises(self, tmp_path):
        (tmp_path / "annotations.json").write_text("not json")
        with pytest.raises(DatasetError, match="解析失败"):
            load_coco_dataset(tmp_path)

    def test_missing_fields_raises(self, tmp_path):
        (tmp_path / "annotations.json").write_text(json.dumps({"images": []}))
        with pytest.raises(DatasetError, match="annotations"):
            load_coco_dataset(tmp_path)
