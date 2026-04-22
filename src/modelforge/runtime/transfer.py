"""Phase 4b 迁移学习：image-classification linear probe。

冻结 base 模型的 backbone，提取倒数第二层特征向量（通过
ImageClassificationHandler.extract_features），用 sklearn
LogisticRegression 训练新的分类头。fork 出的新仓库自包含：

  base_model/                # base 模型完整复制
  handler.py                 # 加载 base + transfer.json，predict 时
                             #   features = base.extract_features(images)
                             #   probs = clf.predict_proba(features)
  transfer.json              # {classes, weights_b64, ...}
  README.md                  # frontmatter 写明 base_model + transfer 元数据
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
from typing import TYPE_CHECKING, Any

from .metrics import classification as cls_metrics
from .tasks.base import TaskHandler

if TYPE_CHECKING:
    from PIL.Image import Image

METHODS = ["linear_probe"]


@dataclass
class TransferResult:
    method: str = "linear_probe"
    classes: list[str] = field(default_factory=list)
    n_samples: int = 0
    n_holdout: int = 0
    weights_b64: str = ""
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


def transfer_by_method(
    method: str,
    handler: TaskHandler,
    images: "list[Image]",
    labels: list[str],
    holdout_ratio: float = 0.3,
) -> TransferResult:
    fn = _TRANSFER_METHODS.get(method)
    if fn is None:
        return TransferResult(
            status="error", error=f"未知方法 '{method}'，支持：{list(_TRANSFER_METHODS)}",
        )
    return fn(handler, images, labels, holdout_ratio)


# ---------- handler template ----------

HANDLER_TEMPLATE = textwrap.dedent('''\
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
            # 透传给 base，让链式 transfer 也能跑
            return self.base.extract_features(images)
''')


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
    """组装 fork 仓库：base_model/ + handler.py + transfer.json + README.md。"""
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_dir, dest / "base_model")

    transfer_meta = {
        "method": result.method,
        "classes": result.classes,
        "n_samples": result.n_samples,
        "weights_b64": result.weights_b64,
    }
    (dest / "transfer.json").write_text(json.dumps(transfer_meta, indent=2))
    (dest / "handler.py").write_text(HANDLER_TEMPLATE)

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
    readme = textwrap.dedent(f"""\
        ---
        license: {src_meta.get('license', 'unknown')}
        library_name: {src_meta.get('library_name', 'unknown')}
        pipeline_tag: image-classification
        base_model: {source_repo}
        tags:
          - image-classification
          - transfer-learning
          - linear-probe
        transfer:
          method: {result.method}
          source_repo: {source_repo}
          source_revision: {source_revision}
          target_data_hash: "sha256:{data_hash}"
          n_classes: {len(result.classes)}
          n_samples: {result.n_samples}
          after_accuracy: {after_acc}
        ---

        # {ns}/{name}

        Linear probe transferred from [{source_repo}](/{source_repo}).

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


def compute_data_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]
