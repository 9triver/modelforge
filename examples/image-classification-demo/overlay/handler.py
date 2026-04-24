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
        if self.device == "cuda":
            torch.backends.cudnn.enabled = False
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

    def fine_tune(self, images, labels, *, method="full", epochs=10,
                  lr=1e-5, unfreeze_layers=2, progress_cb=None):
        import copy
        import tempfile
        from torch.utils.data import DataLoader, Dataset
        from transformers import AutoModelForImageClassification

        classes = sorted(set(labels))
        cls_idx = {c: i for i, c in enumerate(classes)}
        n_classes = len(classes)

        class _DS(Dataset):
            def __init__(self, imgs, lbls, proc, dev):
                self.imgs, self.lbls, self.proc, self.dev = imgs, lbls, proc, dev
            def __len__(self): return len(self.imgs)
            def __getitem__(self, i):
                px = self.proc(images=self.imgs[i], return_tensors="pt")
                return {k: v.squeeze(0).to(self.dev) for k, v in px.items()}, self.lbls[i]

        y = [cls_idx[l] for l in labels]
        from sklearn.model_selection import train_test_split
        idx_tr, idx_ho = train_test_split(range(len(images)), test_size=0.3,
                                          stratify=y, random_state=42)
        imgs_tr = [images[i] for i in idx_tr]
        y_tr = [y[i] for i in idx_tr]
        imgs_ho = [images[i] for i in idx_ho]
        y_ho = [y[i] for i in idx_ho]

        model = AutoModelForImageClassification.from_pretrained(
            self.model_dir, low_cpu_mem_usage=False,
            num_labels=n_classes,
            id2label={i: c for i, c in enumerate(classes)},
            label2id=cls_idx,
            ignore_mismatched_sizes=True,
        ).to(self.device)

        if method == "lora":
            from peft import LoraConfig, get_peft_model
            lora_cfg = LoraConfig(r=8, lora_alpha=16,
                                  target_modules=["query", "value"],
                                  lora_dropout=0.1,
                                  modules_to_save=["classifier"])
            model = get_peft_model(model, lora_cfg)
        else:
            for p in model.parameters():
                p.requires_grad = False
            layers = model.vit.encoder.layer
            for i in range(max(0, len(layers) - unfreeze_layers), len(layers)):
                for p in layers[i].parameters():
                    p.requires_grad = True
            for p in model.classifier.parameters():
                p.requires_grad = True

        train_ds = _DS(imgs_tr, y_tr, self.processor, self.device)
        loader = DataLoader(train_ds, batch_size=8, shuffle=True)
        optimizer = torch.optim.AdamW(
            [p for p in model.parameters() if p.requires_grad], lr=lr,
        )

        model.train()
        for epoch in range(epochs):
            total_loss = 0.0
            for batch_inputs, batch_labels in loader:
                labels_t = torch.tensor(batch_labels, device=self.device)
                out = model(**batch_inputs, labels=labels_t)
                out.loss.backward()
                optimizer.step()
                optimizer.zero_grad()
                total_loss += out.loss.item()
            avg_loss = total_loss / max(len(loader), 1)

            # holdout accuracy
            model.eval()
            correct = 0
            with torch.no_grad():
                for img, lbl in zip(imgs_ho, y_ho):
                    px = self.processor(images=img, return_tensors="pt").to(self.device)
                    logits = model(**px).logits
                    if logits.argmax(-1).item() == lbl:
                        correct += 1
            val_acc = correct / max(len(y_ho), 1)
            model.train()

            if progress_cb:
                progress_cb(epoch + 1, epochs, {"train_loss": avg_loss, "val_accuracy": val_acc})

        # save
        out_dir = tempfile.mkdtemp(prefix="mf_ft_")
        if method == "lora":
            model.save_pretrained(out_dir)
            model.config.save_pretrained(out_dir)
        else:
            model.save_pretrained(out_dir)
        self.processor.save_pretrained(out_dir)

        return {
            "weights_path": out_dir,
            "config": {"method": method, "epochs": epochs, "lr": lr,
                       "unfreeze_layers": unfreeze_layers},
            "classes": classes,
        }
