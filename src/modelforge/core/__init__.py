"""Core domain layer — protocols, types, and dependency injection.

This package defines the abstract interfaces (Protocols) that all backend
implementations must satisfy.  The platform's API and service layers depend
only on these protocols, never on concrete implementations.

Usage::

    from modelforge.core import get_metadata_store, get_artifact_store
"""

from modelforge.core.protocols import (
    ArtifactStore,
    ArtifactType,
    DatasetManager,
    Evaluator,
    JobState,
    LineageEventType,
    MetadataStore,
    Modality,
    ModelRunner,
    TrainingBackend,
)
from modelforge.core.types import (
    ArtifactRef,
    CheckpointPolicy,
    ColumnDef,
    DatasetSchema,
    EnvironmentSpec,
    ImageSpec,
    IOSpec,
    PreprocessConfig,
    TrainingJob,
)

__all__ = [
    # Protocols
    "ArtifactStore",
    "MetadataStore",
    "DatasetManager",
    "TrainingBackend",
    "ModelRunner",
    "Evaluator",
    # Enums
    "ArtifactType",
    "LineageEventType",
    "JobState",
    "Modality",
    # Types
    "ArtifactRef",
    "ColumnDef",
    "ImageSpec",
    "DatasetSchema",
    "EnvironmentSpec",
    "CheckpointPolicy",
    "TrainingJob",
    "IOSpec",
    "PreprocessConfig",
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
