"""数据模型（dataclass）。"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class User:
    id: int
    name: str
    created_at: str


@dataclass
class Token:
    token: str
    user_id: int
    description: str | None
    created_at: str


@dataclass
class Repo:
    id: int
    namespace: str
    name: str
    owner_id: int
    is_private: bool
    created_at: str

    @property
    def full_name(self) -> str:
        return f"{self.namespace}/{self.name}"


@dataclass
class RepoCard:
    repo_id: int
    revision: str
    library_name: str | None
    pipeline_tag: str | None
    license: str | None
    tags_json: str | None
    base_model: str | None
    best_metric_name: str | None
    best_metric_value: float | None
    updated_at: str
    repo_type: str = "model"
    data_format: str | None = None


@dataclass
class Evaluation:
    id: int
    repo_id: int
    revision: str
    task: str
    status: str
    metrics_json: str | None
    primary_metric: str | None
    primary_value: float | None
    duration_ms: int | None
    error: str | None
    created_at: str


@dataclass
class Calibration:
    id: int
    source_repo_id: int
    source_revision: str
    target_repo: str | None
    target_revision: str | None
    method: str
    params_json: str | None
    before_metrics_json: str | None
    after_metrics_json: str | None
    primary_metric: str | None
    before_value: float | None
    after_value: float | None
    status: str
    duration_ms: int | None
    error: str | None
    created_at: str


@dataclass
class Transfer:
    id: int
    source_repo_id: int
    source_revision: str
    target_repo: str | None
    target_revision: str | None
    method: str
    classes_json: str | None
    n_classes: int | None
    n_samples: int | None
    weights_b64: str | None
    after_metrics_json: str | None
    primary_metric: str | None
    after_value: float | None
    hparams_json: str | None
    current_epoch: int | None
    total_epochs: int | None
    status: str
    duration_ms: int | None
    error: str | None
    created_at: str
