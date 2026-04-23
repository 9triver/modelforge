"""Phase 4b 迁移学习：image-classification。

三种方法：
  - linear_probe: 冻结 backbone，sklearn 分类头（CPU 秒级）
  - fine_tune_full: 解冻最后 N 层 + 新分类头（GPU 分钟级）
  - fine_tune_lora: LoRA adapter + 新分类头（GPU 分钟级，权重小）
"""
from __future__ import annotations

import base64
import hashlib
import json
import pickle
import shutil
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from .metrics import classification as cls_metrics
from .tasks.base import TaskHandler

if TYPE_CHECKING:
    from PIL.Image import Image

METHODS = ["linear_probe", "fine_tune_full", "fine_tune_lora"]


@dataclass
class TransferResult:
    method: str = "linear_probe"
    classes: list[str] = field(default_factory=list)
    n_samples: int = 0
    n_holdout: int = 0
    weights_b64: str = ""
    weights_path: str | None = None
    hparams: dict[str, Any] = field(default_factory=dict)
    after_metrics: dict[str, Any] = field(default_factory=dict)
    primary_metric: str = "accuracy"
    after_value: float = 0.0
    status: str = "ok"
    error: str | None = None


# ---------- algorithm ----------

def linear_probe(
    handler: TaskHandler,
    images: "list[Image]",
    labels: list[str],
    holdout_ratio: float = 0.3,
    random_state: int = 42,
) -> TransferResult:
    """Linear probe: 冻结 backbone → 提特征 → 训练 sklearn 分类头。"""
    if len(images) != len(labels):
        return TransferResult(status="error", error="images/labels 数量不一致")

    classes = sorted(set(labels))
    n_classes = len(classes)
    if n_classes < 2:
        return TransferResult(status="error", error=f"至少需要 2 个类别，当前只有 {n_classes}")

    # 每类至少 4 张（split + 至少 1 张 holdout）
    counts = {c: labels.count(c) for c in classes}
    too_few = [c for c, n in counts.items() if n < 4]
    if too_few:
        return TransferResult(
            status="error",
            error=f"类别样本太少（每类至少 4 张）：{too_few} ({counts})",
        )

    try:
        from sklearn.linear_model import LogisticRegression
        from sklearn.model_selection import train_test_split
    except ImportError:
        return TransferResult(status="error", error="需要 scikit-learn（pip install scikit-learn）")

    try:
        features = handler.extract_features(images)  # (N, D)
    except NotImplementedError as e:
        return TransferResult(status="error", error=str(e))
    except Exception as e:  # noqa: BLE001
        return TransferResult(status="error", error=f"extract_features 失败：{e}")

    cls_idx = {c: i for i, c in enumerate(classes)}
    y = [cls_idx[lbl] for lbl in labels]

    try:
        X_tr, X_ho, y_tr, y_ho = train_test_split(
            features, y,
            test_size=holdout_ratio,
            stratify=y,
            random_state=random_state,
        )
    except ValueError as e:
        return TransferResult(status="error", error=f"split 失败：{e}")

    clf = LogisticRegression(max_iter=1000)
    clf.fit(X_tr, y_tr)

    pred_idx = clf.predict(X_ho)
    truth = [classes[i] for i in y_ho]
    preds = [classes[i] for i in pred_idx]
    metrics = cls_metrics.compute_all(truth, preds)
    accuracy = float(metrics.get("accuracy", 0.0))

    return TransferResult(
        method="linear_probe",
        classes=classes,
        n_samples=len(images),
        n_holdout=len(y_ho),
        weights_b64=base64.b64encode(pickle.dumps(clf)).decode(),
        after_metrics=metrics,
        primary_metric="accuracy",
        after_value=accuracy,
    )


_TRANSFER_METHODS = {
    "linear_probe": linear_probe,
}


def _fine_tune_wrapper(
    handler: TaskHandler,
    images: "list[Image]",
    labels: list[str],
    holdout_ratio: float = 0.3,
    *,
    ft_method: str,
    hparams: dict[str, Any] | None = None,
    progress_cb: Callable[[int, int, dict[str, Any]], None] | None = None,
) -> TransferResult:
    """fine_tune_full / fine_tune_lora 的共享 wrapper。"""
    hp = hparams or {}
    epochs = int(hp.get("epochs", 10))
    lr = float(hp.get("lr", 1e-5))
    unfreeze_layers = int(hp.get("unfreeze_layers", 2))

    try:
        result = handler.fine_tune(
            images, labels,
            method=ft_method,
            epochs=epochs,
            lr=lr,
            unfreeze_layers=unfreeze_layers,
            progress_cb=progress_cb,
        )
    except NotImplementedError as e:
        return TransferResult(status="error", error=str(e))
    except Exception as e:  # noqa: BLE001
        return TransferResult(status="error", error=f"fine_tune 失败：{e}")

    classes = result.get("classes", [])
    weights_path = result.get("weights_path")

    # holdout 评估已在 handler.fine_tune 内完成，从 progress_cb 最后一次拿
    # 但也可以从 result 里拿 — 让 handler 返回 metrics
    after_metrics = result.get("metrics", {})
    if not after_metrics and progress_cb:
        pass  # metrics 已通过 progress_cb 更新到 DB

    return TransferResult(
        method=f"fine_tune_{ft_method}",
        classes=classes,
        n_samples=len(images),
        weights_path=weights_path,
        hparams={"method": ft_method, "epochs": epochs, "lr": lr,
                 "unfreeze_layers": unfreeze_layers},
        after_metrics=after_metrics,
        primary_metric="accuracy",
        after_value=float(after_metrics.get("val_accuracy", 0.0)),
    )


def transfer_by_method(
    method: str,
    handler: TaskHandler,
    images: "list[Image]",
    labels: list[str],
    holdout_ratio: float = 0.3,
    *,
    hparams: dict[str, Any] | None = None,
    progress_cb: Callable[[int, int, dict[str, Any]], None] | None = None,
) -> TransferResult:
    if method == "linear_probe":
        return linear_probe(handler, images, labels, holdout_ratio)
    if method in ("fine_tune_full", "fine_tune_lora"):
        ft_method = method.replace("fine_tune_", "")
        return _fine_tune_wrapper(
            handler, images, labels, holdout_ratio,
            ft_method=ft_method, hparams=hparams, progress_cb=progress_cb,
        )
    return TransferResult(
        status="error", error=f"未知方法 '{method}'，支持：{METHODS}",
    )


# ---------- handler templates ----------

HANDLER_TEMPLATE_LINEAR_PROBE = textwrap.dedent('''\
    """Linear probe handler — wraps base model with new classification head."""
    from __future__ import annotations

    import base64
    import json
    import pickle
    from pathlib import Path

    from PIL import Image

    from modelforge.runtime.tasks import ImageClassificationHandler
    from modelforge.runtime.evaluator import load_handler


    class Handler(ImageClassificationHandler):
        def __init__(self, model_dir: str):
            super().__init__(model_dir)
            base_dir = str(Path(model_dir) / "base_model")
            self.base = load_handler(base_dir, "image-classification")
            meta = json.loads((Path(model_dir) / "transfer.json").read_text())
            self.classes = meta["classes"]
            self.clf = pickle.loads(base64.b64decode(meta["weights_b64"]))

        def warmup(self):
            self.base.warmup()

        def predict(self, images):
            features = self.base.extract_features(images)
            probs = self.clf.predict_proba(features)
            results = []
            for row in probs:
                preds = [
                    {"label": self.classes[i], "score": float(p)}
                    for i, p in enumerate(row)
                ]
                preds.sort(key=lambda d: d["score"], reverse=True)
                results.append(preds[:5])
            return results

        def extract_features(self, images):
            return self.base.extract_features(images)
''')


HANDLER_TEMPLATE_FINE_TUNE_FULL = textwrap.dedent('''\
    """Fine-tune (full) handler — loads fine-tuned weights directly."""
    from __future__ import annotations

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

        def predict(self, images):
            results = []
            for img in images:
                inputs = self.processor(images=img, return_tensors="pt").to(self.device)
                with torch.no_grad():
                    logits = self.model(**inputs).logits
                probs = torch.softmax(logits, dim=-1)[0]
                top_k = probs.topk(min(5, len(probs)))
                preds = [
                    {"label": self.model.config.id2label.get(idx.item(), str(idx.item())),
                     "score": round(score.item(), 4)}
                    for score, idx in zip(top_k.values, top_k.indices)
                ]
                results.append(preds)
            return results

        def extract_features(self, images):
            import numpy as np
            feats = []
            for img in images:
                inputs = self.processor(images=img, return_tensors="pt").to(self.device)
                with torch.no_grad():
                    outputs = self.model(**inputs, output_hidden_states=True)
                    cls_token = outputs.hidden_states[-1][:, 0, :]
                feats.append(cls_token.cpu().numpy())
            return np.concatenate(feats, axis=0)
''')


HANDLER_TEMPLATE_FINE_TUNE_LORA = textwrap.dedent('''\
    """Fine-tune (LoRA) handler — loads base model + LoRA adapter."""
    from __future__ import annotations

    from pathlib import Path

    import torch
    from PIL import Image
    from modelforge.runtime.tasks import ImageClassificationHandler


    class Handler(ImageClassificationHandler):
        def __init__(self, model_dir: str):
            super().__init__(model_dir)
            from transformers import AutoImageProcessor, AutoModelForImageClassification
            from peft import PeftModel

            self.device = "cuda" if torch.cuda.is_available() else "cpu"
            base_dir = str(Path(model_dir) / "base_model")
            self.processor = AutoImageProcessor.from_pretrained(base_dir)
            base = AutoModelForImageClassification.from_pretrained(
                base_dir, low_cpu_mem_usage=False,
            )
            self.model = PeftModel.from_pretrained(base, model_dir).to(self.device)
            self.model.eval()

        def predict(self, images):
            results = []
            for img in images:
                inputs = self.processor(images=img, return_tensors="pt").to(self.device)
                with torch.no_grad():
                    logits = self.model(**inputs).logits
                probs = torch.softmax(logits, dim=-1)[0]
                top_k = probs.topk(min(5, len(probs)))
                cfg = self.model.config if hasattr(self.model, "config") else self.model.base_model.config
                id2label = cfg.id2label if hasattr(cfg, "id2label") else {}
                preds = [
                    {"label": id2label.get(idx.item(), str(idx.item())),
                     "score": round(score.item(), 4)}
                    for score, idx in zip(top_k.values, top_k.indices)
                ]
                results.append(preds)
            return results
''')

HANDLER_TEMPLATE = HANDLER_TEMPLATE_LINEAR_PROBE  # 向后兼容


# ---------- repo generation ----------

def generate_transfer_repo(
    source_dir: Path,
    result: TransferResult,
    source_repo: str,
    source_revision: str,
    target_repo: str,
    data_hash: str,
    dest: Path,
) -> None:
    """组装 fork 仓库。按 method 分三种结构：
      - linear_probe: base_model/ + handler.py + transfer.json
      - fine_tune_full: handler.py + 直接放权重文件
      - fine_tune_lora: base_model/ + adapter_* + handler.py
    """
    dest.mkdir(parents=True, exist_ok=True)
    method = result.method

    if method == "fine_tune_full":
        _assemble_full(source_dir, result, dest)
        handler_template = HANDLER_TEMPLATE_FINE_TUNE_FULL
    elif method == "fine_tune_lora":
        _assemble_lora(source_dir, result, dest)
        handler_template = HANDLER_TEMPLATE_FINE_TUNE_LORA
    else:  # linear_probe
        shutil.copytree(source_dir, dest / "base_model")
        handler_template = HANDLER_TEMPLATE_LINEAR_PROBE

    transfer_meta: dict[str, Any] = {
        "method": method,
        "classes": result.classes,
        "n_samples": result.n_samples,
        "hparams": result.hparams,
    }
    if result.weights_b64:
        transfer_meta["weights_b64"] = result.weights_b64
    (dest / "transfer.json").write_text(json.dumps(transfer_meta, indent=2))
    (dest / "handler.py").write_text(handler_template)

    src_meta = {}
    src_readme = source_dir / "README.md"
    if src_readme.is_file():
        from ..schema import parse_frontmatter
        try:
            src_meta, _ = parse_frontmatter(src_readme.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pass

    ns, name = target_repo.split("/", 1)
    classes_str = ", ".join(result.classes)
    after_acc = result.after_value
    after_f1 = result.after_metrics.get("f1_macro", "N/A")
    method_tag = method.replace("_", "-")
    readme = textwrap.dedent(f"""\
        ---
        license: {src_meta.get('license', 'unknown')}
        library_name: {src_meta.get('library_name', 'unknown')}
        pipeline_tag: image-classification
        base_model: {source_repo}
        tags:
          - image-classification
          - transfer-learning
          - {method_tag}
        transfer:
          method: {method}
          source_repo: {source_repo}
          source_revision: {source_revision}
          target_data_hash: "sha256:{data_hash}"
          n_classes: {len(result.classes)}
          n_samples: {result.n_samples}
          after_accuracy: {after_acc}
        ---

        # {ns}/{name}

        Transferred from [{source_repo}](/{source_repo}) via **{method}**.

        - **Classes** ({len(result.classes)}): {classes_str}
        - **Training samples**: {result.n_samples} (holdout: {result.n_holdout})

        | Metric | Value |
        |--------|-------|
        | Accuracy | {after_acc:.4f} |
        | F1 (macro) | {after_f1 if isinstance(after_f1, str) else f'{after_f1:.4f}'} |
    """)
    (dest / "README.md").write_text(readme)

    gitattr = source_dir / ".gitattributes"
    if gitattr.is_file():
        shutil.copy2(gitattr, dest / ".gitattributes")


def _assemble_full(source_dir: Path, result: TransferResult, dest: Path) -> None:
    """fine_tune_full：权重文件直接放在 dest 顶层，不保留 base_model/。"""
    if not result.weights_path:
        raise ValueError("fine_tune_full 结果缺少 weights_path")
    src = Path(result.weights_path)
    for p in src.iterdir():
        if p.is_file():
            shutil.copy2(p, dest / p.name)


def _assemble_lora(source_dir: Path, result: TransferResult, dest: Path) -> None:
    """fine_tune_lora：base_model/ 保留 LFS 指针 + LoRA adapter 文件在顶层。"""
    shutil.copytree(source_dir, dest / "base_model")
    if not result.weights_path:
        raise ValueError("fine_tune_lora 结果缺少 weights_path")
    src = Path(result.weights_path)
    for p in src.iterdir():
        if p.is_file() and (p.name.startswith("adapter_") or p.name == "preprocessor_config.json"):
            shutil.copy2(p, dest / p.name)


def compute_data_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]
