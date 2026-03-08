"""Extended ModelRunner implementations.

Provides runners for sklearn, ONNX, PyTorch, and TensorFlow models.
Each runner conforms to the ModelRunner protocol defined in core.protocols.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any


class SklearnRunner:
    """Runner for scikit-learn models (pickle/joblib format)."""

    def __init__(self):
        self._model = None

    def load(self, model_path: Path, device: str = "cpu", **kwargs: Any) -> None:
        import joblib
        self._model = joblib.load(model_path)

    def predict(self, input_data: list[list[float]]) -> list:
        import numpy as np
        X = np.array(input_data)
        result = self._model.predict(X)
        return result.tolist()

    def predict_batch(self, inputs: list[Any]) -> list[Any]:
        return [self.predict(inp) for inp in inputs]

    def unload(self) -> None:
        self._model = None

    @property
    def input_spec(self) -> dict:
        return {"dtype": "float64", "shape": [-1, -1], "description": "2D array of features"}

    @property
    def output_spec(self) -> dict:
        return {"dtype": "float64", "shape": [-1], "description": "Predictions"}


class OnnxRunner:
    """Runner for ONNX models."""

    def __init__(self):
        self._session = None

    def load(self, model_path: Path, device: str = "cpu", **kwargs: Any) -> None:
        import onnxruntime as ort
        providers = ["CUDAExecutionProvider", "CPUExecutionProvider"] if device != "cpu" else ["CPUExecutionProvider"]
        self._session = ort.InferenceSession(str(model_path), providers=providers)

    def predict(self, input_data: dict[str, Any]) -> list:
        result = self._session.run(None, input_data)
        return [r.tolist() for r in result]

    def predict_batch(self, inputs: list[Any]) -> list[Any]:
        return [self.predict(inp) for inp in inputs]

    def unload(self) -> None:
        self._session = None

    @property
    def input_spec(self) -> dict:
        if self._session:
            inputs = self._session.get_inputs()
            return {
                "inputs": [{"name": i.name, "shape": i.shape, "dtype": i.type} for i in inputs]
            }
        return {}

    @property
    def output_spec(self) -> dict:
        if self._session:
            outputs = self._session.get_outputs()
            return {
                "outputs": [{"name": o.name, "shape": o.shape, "dtype": o.type} for o in outputs]
            }
        return {}


class PyTorchRunner:
    """Runner for PyTorch models (.pt/.pth files)."""

    def __init__(self):
        self._model = None
        self._device = "cpu"

    def load(self, model_path: Path, device: str = "cpu", **kwargs: Any) -> None:
        import torch
        self._device = device
        self._model = torch.load(model_path, map_location=device, weights_only=False)
        if hasattr(self._model, "eval"):
            self._model.eval()

    def predict(self, input_data: Any) -> Any:
        import torch
        with torch.no_grad():
            if isinstance(input_data, list):
                tensor = torch.tensor(input_data, dtype=torch.float32).to(self._device)
            else:
                tensor = input_data
            output = self._model(tensor)
            if hasattr(output, "tolist"):
                return output.cpu().tolist()
            return output

    def predict_batch(self, inputs: list[Any]) -> list[Any]:
        return [self.predict(inp) for inp in inputs]

    def unload(self) -> None:
        self._model = None

    @property
    def input_spec(self) -> dict:
        return {"dtype": "float32", "description": "PyTorch tensor or list"}

    @property
    def output_spec(self) -> dict:
        return {"dtype": "float32", "description": "PyTorch tensor output"}


class TorchScriptRunner:
    """Runner for TorchScript models (.pt files saved with torch.jit)."""

    def __init__(self):
        self._model = None
        self._device = "cpu"

    def load(self, model_path: Path, device: str = "cpu", **kwargs: Any) -> None:
        import torch
        self._device = device
        self._model = torch.jit.load(str(model_path), map_location=device)
        self._model.eval()

    def predict(self, input_data: Any) -> Any:
        import torch
        with torch.no_grad():
            if isinstance(input_data, list):
                tensor = torch.tensor(input_data, dtype=torch.float32).to(self._device)
            else:
                tensor = input_data
            output = self._model(tensor)
            if hasattr(output, "tolist"):
                return output.cpu().tolist()
            return output

    def predict_batch(self, inputs: list[Any]) -> list[Any]:
        return [self.predict(inp) for inp in inputs]

    def unload(self) -> None:
        self._model = None

    @property
    def input_spec(self) -> dict:
        return {"dtype": "float32", "description": "TorchScript input tensor"}

    @property
    def output_spec(self) -> dict:
        return {"dtype": "float32", "description": "TorchScript output tensor"}


class TFSavedModelRunner:
    """Runner for TensorFlow SavedModel format."""

    def __init__(self):
        self._model = None

    def load(self, model_path: Path, device: str = "cpu", **kwargs: Any) -> None:
        import tensorflow as tf
        if device == "cpu":
            tf.config.set_visible_devices([], "GPU")
        self._model = tf.saved_model.load(str(model_path))

    def predict(self, input_data: Any) -> Any:
        import tensorflow as tf
        if isinstance(input_data, list):
            tensor = tf.constant(input_data, dtype=tf.float32)
        else:
            tensor = input_data
        infer = self._model.signatures.get("serving_default")
        if infer is None:
            raise RuntimeError("SavedModel has no 'serving_default' signature")
        result = infer(tensor)
        return {k: v.numpy().tolist() for k, v in result.items()}

    def predict_batch(self, inputs: list[Any]) -> list[Any]:
        return [self.predict(inp) for inp in inputs]

    def unload(self) -> None:
        self._model = None

    @property
    def input_spec(self) -> dict:
        return {"dtype": "float32", "description": "TensorFlow tensor or list"}

    @property
    def output_spec(self) -> dict:
        return {"dtype": "float32", "description": "TensorFlow SavedModel output"}


# ── Runner Registry ──

RUNNER_REGISTRY: dict[str, type] = {
    "pickle": SklearnRunner,
    "joblib": SklearnRunner,
    "sklearn": SklearnRunner,
    "onnx": OnnxRunner,
    "pytorch": PyTorchRunner,
    "pt": PyTorchRunner,
    "pth": PyTorchRunner,
    "torchscript": TorchScriptRunner,
    "tf_savedmodel": TFSavedModelRunner,
    "tensorflow": TFSavedModelRunner,
}


def get_runner_class(file_format: str) -> type | None:
    """Look up a runner class by model file format."""
    return RUNNER_REGISTRY.get(file_format)


# ── Inference Manager (updated) ──


class InferenceManager:
    """Manages loaded model runners for serving predictions.

    Drop-in replacement for the original InferenceManager that now
    supports the extended runner registry.
    """

    def __init__(self):
        self._runners: dict[str, Any] = {}
        self._lock = threading.Lock()

    def deploy(self, deployment_id: str, file_path: Path, file_format: str, device: str = "cpu") -> None:
        runner_cls = get_runner_class(file_format)
        if not runner_cls:
            raise ValueError(f"Unsupported model format: {file_format}")

        runner = runner_cls()
        runner.load(file_path, device=device)

        with self._lock:
            self._runners[deployment_id] = runner

    def predict(self, deployment_id: str, input_data: Any) -> Any:
        runner = self._runners.get(deployment_id)
        if not runner:
            raise KeyError(f"Deployment {deployment_id} not loaded")
        return runner.predict(input_data)

    def predict_batch(self, deployment_id: str, inputs: list[Any]) -> list[Any]:
        runner = self._runners.get(deployment_id)
        if not runner:
            raise KeyError(f"Deployment {deployment_id} not loaded")
        return runner.predict_batch(inputs)

    def undeploy(self, deployment_id: str) -> None:
        with self._lock:
            runner = self._runners.pop(deployment_id, None)
        if runner:
            runner.unload()

    def is_loaded(self, deployment_id: str) -> bool:
        return deployment_id in self._runners

    @property
    def active_count(self) -> int:
        return len(self._runners)

    def get_runner(self, deployment_id: str) -> Any:
        return self._runners.get(deployment_id)


# Module-level singleton
inference_manager = InferenceManager()
