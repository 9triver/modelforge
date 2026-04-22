"""object-detection 默认指标（pycocotools wrapper）。

用 COCO 官方 COCOeval 算：
  - mAP   = mAP@IoU=0.50:0.95（COCO 主指标）
  - mAP_50 = mAP@IoU=0.50
  - mAP_75 = mAP@IoU=0.75
  - mAR   = mean Average Recall（max=100 detections）

依赖 pycocotools（来自 runtime-detection extras）。
"""
from __future__ import annotations

import io
import contextlib
from typing import Any


def compute_all(
    coco_gt_dict: dict[str, Any],
    predictions: list[list[dict]],
    image_ids: list[int],
) -> dict[str, float]:
    """用 pycocotools 算 COCO mAP。

    Args:
        coco_gt_dict: 原始 COCO annotation dict（含 images/annotations/categories）
        predictions: handler 输出，每张图一个 list[{label, bbox, score}]
        image_ids: 与 predictions 对应的 image_id 列表

    Returns:
        {"mAP": ..., "mAP_50": ..., "mAP_75": ..., "mAR": ...}
    """
    from pycocotools.coco import COCO
    from pycocotools.cocoeval import COCOeval

    # 构建 category name → id 映射
    cat_name_to_id: dict[str, int] = {}
    for cat in coco_gt_dict.get("categories", []):
        cat_name_to_id[cat["name"]] = cat["id"]

    # 构建 COCO gt 对象（suppress stdout）
    with contextlib.redirect_stdout(io.StringIO()):
        coco_gt = COCO()
        coco_gt.dataset = coco_gt_dict
        coco_gt.createIndex()

    # 构建 COCO results 列表
    results: list[dict] = []
    det_id = 1
    for img_id, preds in zip(image_ids, predictions):
        for det in preds:
            cat_id = cat_name_to_id.get(det["label"])
            if cat_id is None:
                continue
            bbox = det["bbox"]  # [x, y, w, h]
            results.append({
                "image_id": img_id,
                "category_id": cat_id,
                "bbox": bbox,
                "score": det["score"],
            })
            det_id += 1

    if not results:
        return {"mAP": 0.0, "mAP_50": 0.0, "mAP_75": 0.0, "mAR": 0.0}

    with contextlib.redirect_stdout(io.StringIO()):
        coco_dt = coco_gt.loadRes(results)
        coco_eval = COCOeval(coco_gt, coco_dt, "bbox")
        coco_eval.evaluate()
        coco_eval.accumulate()
        coco_eval.summarize()

    # stats 顺序：[AP@.5:.95, AP@.5, AP@.75, AP_small, AP_medium, AP_large,
    #              AR@1, AR@10, AR@100, AR_small, AR_medium, AR_large]
    stats = coco_eval.stats
    return {
        "mAP": round(float(stats[0]), 4),
        "mAP_50": round(float(stats[1]), 4),
        "mAP_75": round(float(stats[2]), 4),
        "mAR": round(float(stats[8]), 4),  # AR@100
    }
