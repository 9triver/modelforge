"""Tests for runtime.metrics.object_detection (pycocotools mAP)."""
from __future__ import annotations

import pytest

pycocotools = pytest.importorskip("pycocotools")

from modelforge.runtime.metrics.object_detection import compute_all  # noqa: E402


def _make_gt_dict():
    return {
        "images": [
            {"id": 1, "file_name": "a.jpg", "width": 100, "height": 100},
        ],
        "annotations": [
            {"id": 1, "image_id": 1, "category_id": 1,
             "bbox": [10, 10, 30, 30], "area": 900, "iscrowd": 0},
        ],
        "categories": [{"id": 1, "name": "cat"}],
    }


class TestComputeAll:
    def test_perfect_detection(self):
        gt = _make_gt_dict()
        preds = [[{"label": "cat", "bbox": [10, 10, 30, 30], "score": 0.99}]]
        image_ids = [1]
        m = compute_all(gt, preds, image_ids)
        assert m["mAP"] > 0.9
        assert m["mAP_50"] > 0.9
        assert "mAP_75" in m
        assert "mAR" in m

    def test_no_detections(self):
        gt = _make_gt_dict()
        preds = [[]]
        image_ids = [1]
        m = compute_all(gt, preds, image_ids)
        assert m["mAP"] == 0.0

    def test_wrong_label_ignored(self):
        gt = _make_gt_dict()
        preds = [[{"label": "dog", "bbox": [10, 10, 30, 30], "score": 0.99}]]
        image_ids = [1]
        m = compute_all(gt, preds, image_ids)
        assert m["mAP"] == 0.0

    def test_shifted_bbox_lower_map(self):
        gt = _make_gt_dict()
        preds = [[{"label": "cat", "bbox": [50, 50, 30, 30], "score": 0.99}]]
        image_ids = [1]
        m = compute_all(gt, preds, image_ids)
        assert m["mAP"] < 0.5
