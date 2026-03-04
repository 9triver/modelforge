import threading
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ModelRunner(Protocol):
    def load(self, file_path: Path) -> None: ...
    def predict(self, input_data: Any) -> Any: ...
    def unload(self) -> None: ...


class SklearnRunner:
    def __init__(self):
        self._model = None

    def load(self, file_path: Path) -> None:
        import joblib

        self._model = joblib.load(file_path)

    def predict(self, input_data: list[list[float]]) -> list:
        import numpy as np

        X = np.array(input_data)
        result = self._model.predict(X)
        return result.tolist()

    def unload(self) -> None:
        self._model = None


class OnnxRunner:
    def __init__(self):
        self._session = None

    def load(self, file_path: Path) -> None:
        import onnxruntime as ort

        self._session = ort.InferenceSession(str(file_path))

    def predict(self, input_data: dict[str, Any]) -> list:
        result = self._session.run(None, input_data)
        return [r.tolist() for r in result]

    def unload(self) -> None:
        self._session = None


_RUNNERS: dict[str, type] = {
    "pickle": SklearnRunner,
    "joblib": SklearnRunner,
    "onnx": OnnxRunner,
}


class InferenceManager:
    def __init__(self):
        self._runners: dict[str, ModelRunner] = {}
        self._lock = threading.Lock()

    def deploy(self, deployment_id: str, file_path: Path, file_format: str) -> None:
        runner_cls = _RUNNERS.get(file_format)
        if not runner_cls:
            raise ValueError(f"Unsupported model format: {file_format}")

        runner = runner_cls()
        runner.load(file_path)

        with self._lock:
            self._runners[deployment_id] = runner

    def predict(self, deployment_id: str, input_data: Any) -> Any:
        runner = self._runners.get(deployment_id)
        if not runner:
            raise KeyError(f"Deployment {deployment_id} not loaded")
        return runner.predict(input_data)

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


inference_manager = InferenceManager()
