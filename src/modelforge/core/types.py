"""Domain value objects and data structures.

These are plain Pydantic models used by protocols, services, and APIs.
They carry no business logic — just structured data.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from modelforge.core.protocols import ArtifactType, Modality


# ── Artifact Reference ──


class ArtifactRef(BaseModel):
    """A pointer to a versioned artifact in the platform."""

    type: ArtifactType
    id: str
    version: str | None = None
    uri: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


# ── Dataset Schema ──


class ColumnDef(BaseModel):
    """Column definition for tabular datasets."""

    name: str
    dtype: str = "float64"
    description: str = ""
    nullable: bool = True
    value_range: list[float] | None = None
    categories: list[str] | None = None


class ImageSpec(BaseModel):
    """Image specification for vision datasets."""

    channels: int = 3
    min_width: int | None = None
    min_height: int | None = None
    format: str = "jpg"  # jpg, png, bmp, etc.


class DatasetSchema(BaseModel):
    """Unified schema covering tabular and vision modalities."""

    format: str = "tabular_csv"  # tabular_csv, image_folder, coco_json, voc_xml
    modality: Modality = Modality.TABULAR
    columns: list[ColumnDef] | None = None
    image_spec: ImageSpec | None = None
    annotation_format: str | None = None
    class_map: dict[int, str] | None = None
    split_strategy: str = "random"
    sample_count: int | None = None


# ── Training Job ──


class EnvironmentSpec(BaseModel):
    """Reproducibility environment specification."""

    docker_image: str | None = None
    requirements: list[str] = Field(default_factory=list)
    conda_env: str | None = None
    env_vars: dict[str, str] = Field(default_factory=dict)
    python_version: str | None = None


class CheckpointPolicy(BaseModel):
    """Configurable checkpoint saving during training."""

    save_interval_epochs: int | None = None
    keep_last_n: int = 3
    save_best_metric: str | None = None
    save_best_mode: str = "min"  # min or max
    export_formats: list[str] = Field(default_factory=list)  # onnx, torchscript, etc.


class TrainingJob(BaseModel):
    """A training job specification submitted to a TrainingBackend."""

    id: str = ""
    model_id: str
    version_id: str
    script: str
    working_dir: str
    args: list[str] = Field(default_factory=list)
    env: EnvironmentSpec = Field(default_factory=EnvironmentSpec)
    checkpoint_policy: CheckpointPolicy | None = None
    overrides: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class JobStatus(BaseModel):
    """Status of a submitted training job."""

    job_id: str
    state: str  # pending, running, success, failed, cancelled
    started_at: datetime | None = None
    finished_at: datetime | None = None
    metrics: dict[str, float] | None = None
    error: str | None = None


# ── IO Spec for ModelRunner ──


class IOSpec(BaseModel):
    """Describes the input/output format of a model."""

    dtype: str = "float32"
    shape: list[int | str] = Field(default_factory=list)  # e.g. [-1, 3, 224, 224]
    description: str = ""
    example: Any = None


class PreprocessConfig(BaseModel):
    """Preprocessing pipeline configuration stored with a model."""

    steps: list[dict[str, Any]] = Field(default_factory=list)
    # e.g. [{"type": "normalize", "mean": [0.485], "std": [0.229]}]
