"""YOLOv8n handler for ModelForge object-detection evaluator.

I/O contract:
  predict(images: list[PIL.Image]) -> list[list[{label, bbox, score}]]
  bbox 是 COCO 格式 [x, y, w, h]（左上角 + 宽高）。
"""
from __future__ import annotations

from pathlib import Path

import torch
from PIL import Image

from modelforge.runtime.tasks import ObjectDetectionHandler


class Handler(ObjectDetectionHandler):
    def __init__(self, model_dir: str):
        super().__init__(model_dir)
        from ultralytics import YOLO

        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = YOLO(Path(model_dir) / "yolov8n.pt")

    def predict(self, images: list[Image.Image]) -> list[list[dict]]:
        results = []
        for img in images:
            r = self.model(img, verbose=False, device=self.device)[0]
            dets = []
            for box in r.boxes:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                dets.append({
                    "label": r.names[int(box.cls)],
                    "bbox": [x1, y1, x2 - x1, y2 - y1],
                    "score": round(float(box.conf), 4),
                })
            results.append(sorted(dets, key=lambda d: -d["score"]))
        return results
