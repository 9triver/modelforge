"""Unit tests for runtime.transfer (linear probe)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("sklearn")
np = pytest.importorskip("numpy")
PIL_Image = pytest.importorskip("PIL.Image")

from modelforge.runtime.tasks import ImageClassificationHandler  # noqa: E402
from modelforge.runtime.transfer import (  # noqa: E402
    TransferResult,
    generate_transfer_repo,
    linear_probe,
    transfer_by_method,
)


class _SeparableHandler(ImageClassificationHandler):
    """每张图返回随机但按 label 偏移的特征 → 线性可分。"""
    def __init__(self, model_dir: str = "/fake"):
        super().__init__(model_dir)
        self._rng = np.random.default_rng(42)
        self._label_to_offset: dict[str, np.ndarray] = {}

    def predict(self, images):
        return [[{"label": "?", "score": 1.0}]] * len(images)

    def extract_features(self, images):
        # 测试里我们通过 _hint_labels 注入伪标签
        labels = getattr(self, "_hint_labels", None)
        n = len(images)
        D = 16
        feats = np.zeros((n, D), dtype=np.float32)
        for i in range(n):
            base = self._rng.standard_normal(D) * 0.1
            if labels is not None and i < len(labels):
                if labels[i] not in self._label_to_offset:
                    # 给每个 label 一个固定的、相互正交的偏移
                    seed = sum(ord(c) for c in labels[i])
                    rng2 = np.random.default_rng(seed)
                    off = rng2.standard_normal(D) * 5
                    self._label_to_offset[labels[i]] = off
                base = base + self._label_to_offset[labels[i]]
            feats[i] = base
        return feats


def _make_images(n: int) -> list:
    return [PIL_Image.new("RGB", (8, 8), color=(i, i, i)) for i in range(n)]


class TestLinearProbe:
    def test_separable_data_high_accuracy(self):
        labels = ["cat"] * 10 + ["dog"] * 10
        images = _make_images(len(labels))
        h = _SeparableHandler()
        h._hint_labels = labels
        result = linear_probe(h, images, labels)
        assert result.status == "ok"
        assert result.method == "linear_probe"
        assert sorted(result.classes) == ["cat", "dog"]
        assert result.after_value > 0.8  # linearly separable
        assert result.weights_b64
        assert result.n_samples == 20

    def test_too_few_per_class(self):
        labels = ["a", "a", "b", "b"]  # < 4 per class
        images = _make_images(4)
        result = linear_probe(_SeparableHandler(), images, labels)
        assert result.status == "error"
        assert "至少" in result.error or "太少" in result.error

    def test_single_class(self):
        labels = ["only"] * 8
        images = _make_images(8)
        result = linear_probe(_SeparableHandler(), images, labels)
        assert result.status == "error"
        assert "类别" in result.error

    def test_extract_features_not_implemented(self):
        class BareHandler(ImageClassificationHandler):
            def predict(self, images): return [[]] * len(images)
        labels = ["a"] * 5 + ["b"] * 5
        result = linear_probe(BareHandler("/fake"), _make_images(10), labels)
        assert result.status == "error"
        assert "extract_features" in result.error or "迁移" in result.error

    def test_dispatcher(self):
        labels = ["a"] * 5 + ["b"] * 5
        h = _SeparableHandler()
        h._hint_labels = labels
        result = transfer_by_method("linear_probe", h, _make_images(10), labels)
        assert result.status == "ok"

    def test_unknown_method(self):
        result = transfer_by_method("nope", _SeparableHandler(), _make_images(10), ["a"] * 10)
        assert result.status == "error"
        assert "未知" in result.error


class TestGenerateTransferRepo:
    def test_creates_expected_files(self, tmp_path: Path):
        source = tmp_path / "source"
        source.mkdir()
        (source / "README.md").write_text(
            "---\nlicense: mit\nlibrary_name: transformers\n"
            "pipeline_tag: image-classification\n---\n# base\n"
        )
        (source / "weights.bin").write_bytes(b"fake weights")

        result = TransferResult(
            method="linear_probe",
            classes=["broken", "ok"],
            n_samples=30,
            n_holdout=10,
            weights_b64="abc==",
            after_metrics={"accuracy": 0.92, "f1_macro": 0.91},
            after_value=0.92,
        )

        dest = tmp_path / "fork"
        generate_transfer_repo(
            source_dir=source, result=result,
            source_repo="hf/vit-base", source_revision="abc123",
            target_repo="chun/vit-defect", data_hash="deadbeef", dest=dest,
        )

        assert (dest / "handler.py").is_file()
        assert (dest / "transfer.json").is_file()
        assert (dest / "base_model" / "weights.bin").is_file()
        assert (dest / "README.md").is_file()

        meta = json.loads((dest / "transfer.json").read_text())
        assert meta["classes"] == ["broken", "ok"]
        assert meta["weights_b64"] == "abc=="

        readme = (dest / "README.md").read_text()
        assert "linear_probe" in readme
        assert "broken" in readme and "ok" in readme
        assert "base_model: hf/vit-base" in readme


class _MockFineTuneHandler(ImageClassificationHandler):
    """Mock handler that implements fine_tune without real PyTorch."""
    def predict(self, images): return [[{"label": "?", "score": 1.0}]] * len(images)
    def extract_features(self, images): return np.zeros((len(images), 4))

    def fine_tune(self, images, labels, *, method="full", epochs=3, lr=1e-5,
                  unfreeze_layers=2, progress_cb=None):
        import tempfile
        classes = sorted(set(labels))
        out = tempfile.mkdtemp(prefix="mf_mock_ft_")
        Path(out, "model.safetensors").write_bytes(b"fake")
        Path(out, "config.json").write_text('{"num_labels": %d}' % len(classes))
        if method == "lora":
            Path(out, "adapter_model.safetensors").write_bytes(b"fake_adapter")
            Path(out, "adapter_config.json").write_text('{}')
        for epoch in range(epochs):
            if progress_cb:
                progress_cb(epoch + 1, epochs, {"val_accuracy": 0.5 + epoch * 0.1})
        return {
            "weights_path": out,
            "config": {"method": method, "epochs": epochs},
            "classes": classes,
            "metrics": {"val_accuracy": 0.5 + (epochs - 1) * 0.1},
        }


class TestFineTuneDispatch:
    def test_fine_tune_full(self):
        labels = ["a"] * 5 + ["b"] * 5
        h = _MockFineTuneHandler("/fake")
        result = transfer_by_method(
            "fine_tune_full", h, _make_images(10), labels,
            hparams={"epochs": 3, "lr": 1e-4, "unfreeze_layers": 1},
        )
        assert result.status == "ok"
        assert result.method == "fine_tune_full"
        assert result.weights_path is not None
        assert result.hparams["method"] == "full"
        assert result.hparams["epochs"] == 3

    def test_fine_tune_lora(self):
        labels = ["x"] * 5 + ["y"] * 5
        h = _MockFineTuneHandler("/fake")
        result = transfer_by_method(
            "fine_tune_lora", h, _make_images(10), labels,
            hparams={"epochs": 2},
        )
        assert result.status == "ok"
        assert result.method == "fine_tune_lora"

    def test_progress_cb_called(self):
        labels = ["a"] * 5 + ["b"] * 5
        h = _MockFineTuneHandler("/fake")
        progress_log = []
        transfer_by_method(
            "fine_tune_full", h, _make_images(10), labels,
            hparams={"epochs": 3},
            progress_cb=lambda e, t, m: progress_log.append((e, t)),
        )
        assert progress_log == [(1, 3), (2, 3), (3, 3)]

    def test_handler_not_implemented(self):
        class BareHandler(ImageClassificationHandler):
            def predict(self, images): return [[]] * len(images)
        labels = ["a"] * 5 + ["b"] * 5
        result = transfer_by_method("fine_tune_full", BareHandler("/fake"), _make_images(10), labels)
        assert result.status == "error"
        assert "fine_tune" in result.error


class TestGenerateTransferRepoFull:
    def test_full_mode_no_base_model(self, tmp_path: Path):
        source = tmp_path / "source"
        source.mkdir()
        (source / "README.md").write_text(
            "---\nlicense: mit\nlibrary_name: transformers\npipeline_tag: image-classification\n---\n# base\n"
        )

        weights_dir = tmp_path / "weights"
        weights_dir.mkdir()
        (weights_dir / "model.safetensors").write_bytes(b"fake")
        (weights_dir / "config.json").write_text('{}')

        result = TransferResult(
            method="fine_tune_full",
            classes=["a", "b"],
            n_samples=20,
            weights_path=str(weights_dir),
            hparams={"method": "full", "epochs": 5},
            after_metrics={"accuracy": 0.9},
            after_value=0.9,
        )

        dest = tmp_path / "fork"
        generate_transfer_repo(
            source_dir=source, result=result,
            source_repo="hf/vit", source_revision="abc",
            target_repo="chun/vit-ft", data_hash="dead", dest=dest,
        )

        assert (dest / "handler.py").is_file()
        assert (dest / "model.safetensors").is_file()
        assert not (dest / "base_model").exists()
        assert "fine-tune-full" in (dest / "README.md").read_text()


class TestGenerateTransferRepoLora:
    def test_lora_mode_has_base_model(self, tmp_path: Path):
        source = tmp_path / "source"
        source.mkdir()
        (source / "README.md").write_text(
            "---\nlicense: mit\nlibrary_name: transformers\npipeline_tag: image-classification\n---\n# base\n"
        )
        (source / "weights.bin").write_bytes(b"base weights")

        weights_dir = tmp_path / "weights"
        weights_dir.mkdir()
        (weights_dir / "adapter_model.safetensors").write_bytes(b"adapter")
        (weights_dir / "adapter_config.json").write_text('{}')
        (weights_dir / "config.json").write_text('{"num_labels": 2}')

        result = TransferResult(
            method="fine_tune_lora",
            classes=["a", "b"],
            n_samples=20,
            weights_path=str(weights_dir),
            hparams={"method": "lora", "epochs": 5},
            after_metrics={"accuracy": 0.85},
            after_value=0.85,
        )

        dest = tmp_path / "fork"
        generate_transfer_repo(
            source_dir=source, result=result,
            source_repo="hf/vit", source_revision="abc",
            target_repo="chun/vit-lora", data_hash="dead", dest=dest,
        )

        assert (dest / "handler.py").is_file()
        assert (dest / "base_model" / "weights.bin").is_file()
        assert (dest / "adapter_model.safetensors").is_file()
        assert (dest / "adapter_config.json").is_file()
        assert (dest / "config.json").is_file()
        assert "fine-tune-lora" in (dest / "README.md").read_text()
