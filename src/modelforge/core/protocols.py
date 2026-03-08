"""Abstract Protocol definitions for the ModelForge platform.

All backend implementations (filesystem, MinIO, DVC, MLflow, …) conform to
one or more of these protocols.  The API / service layer depends *only* on
these interfaces.
"""

from __future__ import annotations

import enum
from datetime import datetime
from pathlib import Path
from typing import IO, Any, Protocol, runtime_checkable


# ── Value Objects / Enums ──


class ArtifactType(str, enum.Enum):
    MODEL_WEIGHTS = "model_weights"
    DATASET = "dataset"
    CODE = "code"
    PARAMETERS = "parameters"
    FEATURES = "features"
    METRICS = "metrics"
    PREPROCESS_CONFIG = "preprocess"
    ENVIRONMENT = "environment"


class LineageEventType(str, enum.Enum):
    TRAINING = "training"
    EVALUATION = "evaluation"
    FORK = "fork"
    IMPORT = "import"
    EXPORT = "export"
    FINE_TUNE = "fine_tune"
    DEPLOYMENT = "deployment"


class JobState(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Modality(str, enum.Enum):
    TABULAR = "tabular"
    IMAGE = "image"
    VIDEO = "video"
    TEXT = "text"
    MULTIMODAL = "multimodal"


# ── Artifact Store ──


@runtime_checkable
class ArtifactStore(Protocol):
    """Binary object storage abstraction.

    Implementations: local filesystem, MinIO / S3, etc.
    Keys use forward-slash paths (e.g. ``models/slug/versions/v1/weights/model.pkl``).
    """

    def put(self, key: str, data: IO[bytes], metadata: dict[str, str] | None = None) -> str:
        """Store binary data. Returns the key."""
        ...

    def get(self, key: str) -> IO[bytes]:
        """Retrieve binary data by key."""
        ...

    def delete(self, key: str) -> None:
        """Delete a single object."""
        ...

    def list_keys(self, prefix: str) -> list[str]:
        """List all keys under *prefix*."""
        ...

    def exists(self, key: str) -> bool:
        """Check whether a key exists."""
        ...

    def copy(self, src_key: str, dst_key: str) -> None:
        """Copy an object within the store."""
        ...

    def get_local_path(self, key: str) -> Path | None:
        """Return a local filesystem path if the store is local, else *None*.

        This is an optimisation hook: callers that need a ``Path`` (e.g. to
        pass to a subprocess) can avoid downloading when running locally.
        """
        ...


# ── Metadata Store ──


@runtime_checkable
class MetadataStore(Protocol):
    """Structured metadata persistence (models, versions, deployments, …).

    Implementations: YAML-file, SQLite, PostgreSQL, etc.
    """

    # -- Models --

    def create_model(self, data: dict) -> dict:
        ...

    def list_models(
        self,
        *,
        task_type: str | None = None,
        framework: str | None = None,
        status: str | None = None,
        owner_org: str | None = None,
        search: str | None = None,
        scenario: str | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> list[dict]:
        ...

    def get_model(self, model_id: str) -> dict:
        ...

    def update_model(self, model_id: str, updates: dict) -> dict:
        ...

    def delete_model(self, model_id: str) -> None:
        ...

    def transition_status(self, model_id: str, target_status: str) -> dict:
        ...

    # -- Versions --

    def create_version(self, model_id: str, data: dict) -> dict:
        ...

    def list_versions(self, model_id: str) -> list[dict]:
        ...

    def get_version(self, model_id: str, version_id: str) -> dict:
        ...

    def update_version(self, model_id: str, version_id: str, updates: dict) -> dict:
        ...

    def transition_stage(self, model_id: str, version_id: str, target_stage: str) -> dict:
        ...

    def find_version_globally(self, version_id: str) -> tuple[str, str, str, dict] | None:
        """Return *(model_id, slug, version_str, data)* or *None*."""
        ...

    # -- Deployments --

    def create_deployment(self, data: dict) -> dict:
        ...

    def list_deployments(
        self,
        *,
        status: str | None = None,
        model_version_id: str | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> list[dict]:
        ...

    def get_deployment(self, deployment_id: str) -> dict:
        ...

    def get_deployment_by_name(self, name: str) -> dict:
        ...

    def update_deployment(self, deployment_id: str, updates: dict) -> dict:
        ...

    def delete_deployment(self, deployment_id: str) -> None:
        ...

    # -- Pipeline runs --

    def create_run(self, model_id: str, data: dict) -> dict:
        ...

    def get_run(self, model_id: str, run_id: str) -> dict:
        ...

    def list_runs(self, model_id: str) -> list[dict]:
        ...

    def update_run(self, model_id: str, run_id: str, updates: dict) -> dict:
        ...

    # -- Pipelines --

    def get_pipeline(self, model_id: str) -> dict | None:
        ...

    def save_pipeline(self, model_id: str, yaml_text: str) -> dict:
        ...

    def delete_pipeline(self, model_id: str) -> None:
        ...

    # -- Prediction logs --

    def log_prediction(self, deployment_id: str, input_data: Any, output: Any, latency_ms: float) -> dict:
        ...

    def list_predictions(
        self,
        deployment_id: str,
        *,
        skip: int = 0,
        limit: int = 50,
    ) -> list[dict]:
        ...

    def submit_actuals(self, deployment_id: str, actuals: list[dict]) -> tuple[int, list[str]]:
        ...

    def compute_metrics(
        self,
        deployment_id: str,
        *,
        metric_type: str = "rmse",
        window: str | None = None,
    ) -> dict:
        ...

    def compute_stats(
        self,
        deployment_id: str,
        *,
        field: str = "output",
        window: str | None = None,
    ) -> dict:
        ...

    # -- Feature catalog --

    def create_feature_definition(self, data: dict) -> dict:
        ...

    def list_feature_definitions(
        self,
        *,
        category: str | None = None,
        source: str | None = None,
        search: str | None = None,
    ) -> list[dict]:
        ...

    def get_feature_definition(self, feature_id: str) -> dict:
        ...

    def update_feature_definition(self, feature_id: str, updates: dict) -> dict:
        ...

    def delete_feature_definition(self, feature_id: str) -> None:
        ...

    def create_feature_group(self, data: dict) -> dict:
        ...

    def list_feature_groups(self, *, scenario: str | None = None) -> list[dict]:
        ...

    def get_feature_group(self, group_id: str) -> dict:
        ...

    def update_feature_group(self, group_id: str, updates: dict) -> dict:
        ...

    def delete_feature_group(self, group_id: str) -> None:
        ...

    def associate_model_group(self, model_id: str, group_id: str) -> None:
        ...

    def disassociate_model_group(self, model_id: str, group_id: str) -> None:
        ...

    def list_model_groups(self, model_id: str) -> list[dict]:
        ...

    # -- Parameter templates --

    def create_parameter_template(self, data: dict) -> dict:
        ...

    def list_parameter_templates(
        self,
        *,
        algorithm_type: str | None = None,
        search: str | None = None,
    ) -> list[dict]:
        ...

    def get_parameter_template(self, template_id: str) -> dict:
        ...

    def update_parameter_template(self, template_id: str, updates: dict) -> dict:
        ...

    def delete_parameter_template(self, template_id: str) -> None:
        ...

    def compare_parameters(self, request: Any) -> dict:
        ...

    # -- Export / Import --

    def get_model_slug(self, model_id: str) -> str | None:
        """Return the slug for a model ID (used by artifact layer)."""
        ...


# ── Dataset Manager ──


@runtime_checkable
class DatasetManager(Protocol):
    """Dataset lifecycle management.

    Implementations: local filesystem, DVC, LakeFS, etc.
    """

    def register(self, name: str, schema: dict) -> dict:
        ...

    def add_version(
        self,
        dataset_id: str,
        source: str | IO[bytes],
        metadata: dict | None = None,
    ) -> dict:
        ...

    def get_version(self, dataset_id: str, version: str) -> dict:
        ...

    def list_datasets(
        self,
        *,
        modality: str | None = None,
        search: str | None = None,
    ) -> list[dict]:
        ...

    def compare_versions(self, dataset_id: str, v1: str, v2: str) -> dict:
        ...

    def validate(self, dataset_id: str, version: str, rules: list[dict] | None = None) -> dict:
        ...


# ── Training Backend ──


@runtime_checkable
class TrainingBackend(Protocol):
    """Training job execution abstraction.

    Implementations: local subprocess, Docker, Ray, Kubernetes, etc.
    """

    def submit(self, job: dict) -> str:
        """Submit a training job. Returns job_id."""
        ...

    def get_status(self, job_id: str) -> dict:
        ...

    def get_logs(self, job_id: str, tail: int = 100) -> list[str]:
        ...

    def cancel(self, job_id: str) -> None:
        ...

    def list_jobs(self, filters: dict | None = None) -> list[dict]:
        ...


# ── Model Runner (Inference) ──


@runtime_checkable
class ModelRunner(Protocol):
    """Model inference abstraction.

    Each implementation handles one model format (sklearn, ONNX, PyTorch, TF, …).
    """

    def load(self, model_path: Path, device: str = "cpu", **kwargs: Any) -> None:
        ...

    def predict(self, input_data: Any) -> Any:
        ...

    def predict_batch(self, inputs: list[Any]) -> list[Any]:
        ...

    def unload(self) -> None:
        ...

    @property
    def input_spec(self) -> dict:
        """Describe expected input format (shape, dtype, etc.)."""
        ...

    @property
    def output_spec(self) -> dict:
        """Describe output format."""
        ...


# ── Evaluator ──


@runtime_checkable
class Evaluator(Protocol):
    """Model evaluation plugin interface.

    Implementations provide task-specific metrics and diagnostics.
    """

    @property
    def supported_tasks(self) -> list[str]:
        """Task types this evaluator handles (e.g. 'regression', 'classification', 'object_detection')."""
        ...

    def evaluate(
        self,
        predictions: Any,
        ground_truth: Any,
        **kwargs: Any,
    ) -> dict:
        """Compute metrics. Returns {metric_name: value}."""
        ...

    def diagnose(
        self,
        model_path: Path,
        dataset: Any,
        **kwargs: Any,
    ) -> dict:
        """Run diagnostics (SHAP, drift, GradCAM, etc.). Returns structured report."""
        ...
