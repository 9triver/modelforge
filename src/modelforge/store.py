"""Backward-compatible facade over the new adapter layer.

``ModelStore`` now delegates to ``YAMLMetadataStore`` (and other adapters)
while preserving the exact same public API that the existing API routes
and tests rely on.

New code should import from ``modelforge.core`` or directly from adapters.
This module exists solely for backward compatibility during the migration.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from modelforge.adapters.filesystem.metadata_store import (
    YAMLMetadataStore,
    slugify,
)
from modelforge.adapters.filesystem.yaml_io import JSONLFile, YAMLFile

__all__ = ["ModelStore", "YAMLFile", "JSONLFile", "slugify", "get_store"]


class ModelStore(YAMLMetadataStore):
    """Backward-compatible facade.

    Inherits from ``YAMLMetadataStore`` so every method that used to exist
    on the old monolithic ``ModelStore`` is still available.  The only
    additions are convenience methods that the old API routes call with
    a slightly different signature (e.g. ``create_version`` with file upload).
    """

    def __init__(self, base_path: Path) -> None:
        super().__init__(base_path)

    # ── Overrides for API routes that pass an UploadFile ──

    def create_version(self, model_id: str, data: dict, file: Any = None) -> dict:
        """Create a version, optionally uploading a weights file.

        If *file* is ``None`` the base class ``create_version`` (metadata-only)
        is called.  If *file* is provided the weights are written to disk and
        the version record is enriched with file_path / file_size_bytes.
        """
        if file is None:
            return super().create_version(model_id, data)

        from fastapi import HTTPException

        slug = self._find_slug_by_id(model_id)
        if not slug:
            raise HTTPException(404, "Model not found")

        version_str = data["version"]
        vdir = self._version_dir(slug, version_str)
        if vdir.exists():
            raise HTTPException(409, f"Version '{version_str}' already exists for this model")

        vdir.mkdir(parents=True)
        weights_dir = vdir / "weights"
        weights_dir.mkdir()

        filename = getattr(file, "filename", "model.bin")
        dest = weights_dir / filename
        size = 0
        with open(dest, "wb") as f:
            while chunk := file.file.read(8192):
                f.write(chunk)
                size += len(chunk)

        for sub in ("datasets", "code", "features", "params"):
            (vdir / sub).mkdir(exist_ok=True)

        enriched = dict(data)
        enriched["file_path"] = f"weights/{filename}"
        enriched["file_size_bytes"] = size
        enriched["stage"] = "development"

        from modelforge.adapters.filesystem.metadata_store import _now_str, _new_id

        now = _now_str()
        version_data = {
            "id": _new_id(),
            "version": version_str,
            "description": data.get("description"),
            "file_format": data.get("file_format", "joblib"),
            "file_path": f"weights/{filename}",
            "file_size_bytes": size,
            "metrics": data.get("metrics"),
            "stage": "development",
            "parent_version_id": data.get("parent_version_id"),
            "created_at": now,
            "updated_at": now,
        }

        YAMLFile.write(vdir / "version.yaml", version_data)

        model_data = YAMLFile.read(self._model_yaml_path(slug))
        model_data["updated_at"] = now
        YAMLFile.write(self._model_yaml_path(slug), model_data)
        self._update_index_entry(model_data)

        version_data["asset_id"] = model_id
        return version_data

    # ── Aliases used by old API routes ──

    def delete_deployment(self, deployment_id: str, inference_manager: Any = None) -> None:
        """Delete a deployment, optionally stopping the inference runner."""
        if inference_manager is not None:
            self.delete_deployment_with_inference(deployment_id, inference_manager)
        else:
            super().delete_deployment(deployment_id)

    def _update_deployment(self, deployment_id: str, updates: dict) -> dict:
        """Alias kept for backward compat (old store used underscore prefix)."""
        return self.update_deployment(deployment_id, updates)

    # ── _find_version_globally alias ──

    def _find_version_globally(self, version_id: str):
        return self.find_version_globally(version_id)


# ── Dependency injection ──

_store: ModelStore | None = None


def get_store() -> ModelStore:
    global _store
    if _store is None:
        from modelforge.config import settings

        _store = ModelStore(settings.MODEL_STORE_PATH)
    return _store
