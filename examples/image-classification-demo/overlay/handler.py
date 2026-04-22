"""ViT Cats-vs-Dogs handler for ModelForge image-classification evaluator.

I/O contract:
  predict(images: list[PIL.Image]) -> list[list[{label, score}]]
  extract_features(images: list[PIL.Image]) -> np.ndarray (N, D)
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

    def extract_features(self, images: list[Image.Image]):
        import numpy as np
        feats = []
        for img in images:
            inputs = self.processor(images=img, return_tensors="pt").to(self.device)
            with torch.no_grad():
                outputs = self.model(**inputs, output_hidden_states=True)
                cls_token = outputs.hidden_states[-1][:, 0, :]
            feats.append(cls_token.cpu().numpy())
        return np.concatenate(feats, axis=0)
