"""Core domain layer — protocols, types, and dependency injection.

This package defines the abstract interfaces (Protocols) and domain models
that represent every entity in the platform.

Usage::

    from modelforge.core import ModelAsset, ModelVersion, get_metadata_store
"""

from modelforge.core.protocols import (
    MetadataStore,
    ModelRunner,
    TrainingBackend,
)
from modelforge.core.types import (
    ArtifactLocation,
    Deployment,
    FeatureDefinition,
    FeatureGroup,
    ModelAsset,
    ModelVersion,
    ParameterTemplate,
    PipelineRun,
    PredictionLog,
)

__all__ = [
    # Protocols
    "MetadataStore",
    "TrainingBackend",
    "ModelRunner",
    # Domain models
    "ArtifactLocation",
    "ModelAsset",
    "ModelVersion",
    "Deployment",
    "PipelineRun",
    "PredictionLog",
    "FeatureDefinition",
    "FeatureGroup",
    "ParameterTemplate",
    # DI
    "get_metadata_store",
    "get_artifact_store",
]

# ── Dependency Injection (lazy singletons) ──

_metadata_store = None
_artifact_store = None


def get_metadata_store():
    """Return the singleton MetadataStore instance."""
    global _metadata_store
    if _metadata_store is None:
        from modelforge.config import settings
        from modelforge.adapters.filesystem.metadata_store import (
            YAMLMetadataStore,
        )

        _metadata_store = YAMLMetadataStore(settings.MODEL_STORE_PATH)
    return _metadata_store


def get_artifact_store():
    """Return the singleton ArtifactStore instance."""
    global _artifact_store
    if _artifact_store is None:
        from modelforge.config import settings
        from modelforge.adapters.filesystem.artifact_store import (
            LocalArtifactStore,
        )

        _artifact_store = LocalArtifactStore(settings.MODEL_STORE_PATH)
    return _artifact_store
