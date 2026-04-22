"""ViT Cats-vs-Dogs handler for ModelForge image-classification evaluator.

I/O contract:
  predict(images: list[PIL.Image]) -> list[list[{label, score}]]
  每张图返回按 score 降序的 top-k 预测。evaluator 取 top-1 比 true_label。
"""
from __future__ import annotations

from pathlib import Path

import torch
from PIL import Image

from modelforge.runtime.tasks import ImageClassificationHandler


class Handler(ImageClassificationHandler):
    def __init__(self, model_dir: str):
        super().__init__(model_dir)
        from transformers import AutoImageProcessor, AutoModelForImageClassification

        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.processor = AutoImageProcessor.from_pretrained(model_dir)
        self.model = AutoModelForImageClassification.from_pretrained(
            model_dir, low_cpu_mem_usage=False,
        ).to(self.device)
        self.model.eval()

    def predict(self, images: list[Image.Image]) -> list[list[dict]]:
        results: list[list[dict]] = []
        for img in images:
            inputs = self.processor(images=img, return_tensors="pt").to(self.device)
            with torch.no_grad():
                logits = self.model(**inputs).logits
            probs = torch.softmax(logits, dim=-1)[0]
            top_k = probs.topk(min(5, len(probs)))
            preds = []
            for score, idx in zip(top_k.values, top_k.indices):
                label = self.model.config.id2label.get(idx.item(), str(idx.item()))
                preds.append({"label": label, "score": round(score.item(), 4)})
            results.append(preds)
        return results
