"""File-system + YAML metadata store for ModelForge.

Replaces SQLAlchemy/SQLite with directory structure + YAML/JSONL files.
All model assets are organized under a model-centric directory hierarchy.
"""

import fcntl
import json
import math
import re
import shutil
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from modelforge.enums import (
    ASSET_STATUS_TRANSITIONS,
    VERSION_STAGE_TRANSITIONS,
    AssetStatus,
    VersionStage,
)

# ── Utilities ──


def _now_str() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


def slugify(name: str) -> str:
    """Convert a model name (possibly Chinese) to a filesystem-safe slug."""
    try:
        from pypinyin import lazy_pinyin

        slug = "-".join(lazy_pinyin(name))
    except ImportError:
        ascii_part = re.sub(r"[^a-zA-Z0-9\s-]", "", name).strip()
        if ascii_part:
            slug = ascii_part
        else:
            slug = f"model-{uuid.uuid4().hex[:8]}"

    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-").lower()
    return slug or f"model-{uuid.uuid4().hex[:8]}"


# ── File I/O helpers ──


class YAMLFile:
    """Thread-safe YAML file reader/writer with advisory file locking."""

    @staticmethod
    def read(path: Path) -> dict | list:
        if not path.exists():
            return {}
        with open(path, "r", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_SH)
            try:
                return yaml.safe_load(f) or {}
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    @staticmethod
    def write(path: Path, data: dict | list) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(".yaml.tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
        tmp_path.replace(path)


class JSONLFile:
    """Append-only JSONL file for prediction logs."""

    @staticmethod
    def append(path: Path, record: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False, default=str) + "\n"
        with open(path, "a", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                f.write(line)
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    @staticmethod
    def read_all(path: Path) -> list[dict]:
        if not path.exists():
            return []
        records = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        return records

    @staticmethod
    def write_all(path: Path, records: list[dict]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(".jsonl.tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                for record in records:
                    f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
        tmp_path.replace(path)


# ── ModelStore ──


class ModelStore:
    """Central file-system store managing models, versions, deployments, and logs."""

    def __init__(self, base_path: Path):
        self.base_path = base_path
        self._index_lock = threading.RLock()
        self._write_locks: dict[str, threading.Lock] = {}
        self._index: list[dict] = []

        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.deployments_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.catalog_dir.mkdir(parents=True, exist_ok=True)

        self._rebuild_index()

    @property
    def models_dir(self) -> Path:
        return self.base_path / "models"

    @property
    def deployments_dir(self) -> Path:
        return self.base_path / "deployments"

    @property
    def logs_dir(self) -> Path:
        return self.base_path / "logs"

    @property
    def catalog_dir(self) -> Path:
        return self.base_path / "catalog"

    @property
    def index_path(self) -> Path:
        return self.base_path / "index.yaml"

    # ── Index management ──

    def _rebuild_index(self) -> None:
        index = []
        if self.models_dir.exists():
            for model_dir in sorted(self.models_dir.iterdir()):
                if not model_dir.is_dir():
                    continue
                model_yaml = model_dir / "model.yaml"
                if model_yaml.exists():
                    data = YAMLFile.read(model_yaml)
                    versions_dir = model_dir / "versions"
                    vc = 0
                    if versions_dir.exists():
                        vc = len([d for d in versions_dir.iterdir() if d.is_dir()])
                    index.append(self._index_entry_from_data(data, vc))
        with self._index_lock:
            self._index = index

    def _index_entry_from_data(self, data: dict, version_count: int) -> dict:
        entry = dict(data)
        entry["version_count"] = version_count
        return entry

    def _update_index_entry(self, model_data: dict, version_count: int | None = None) -> None:
        with self._index_lock:
            self._index = [m for m in self._index if m["id"] != model_data["id"]]
            if version_count is None:
                slug = model_data["slug"]
                versions_dir = self.models_dir / slug / "versions"
                version_count = 0
                if versions_dir.exists():
                    version_count = len([d for d in versions_dir.iterdir() if d.is_dir()])
            self._index.append(self._index_entry_from_data(model_data, version_count))

    def _remove_from_index(self, model_id: str) -> None:
        with self._index_lock:
            self._index = [m for m in self._index if m["id"] != model_id]

    # ── Path helpers ──

    def _model_dir(self, slug: str) -> Path:
        return self.models_dir / slug

    def _model_yaml_path(self, slug: str) -> Path:
        return self._model_dir(slug) / "model.yaml"

    def _version_dir(self, slug: str, version: str) -> Path:
        v = version if version.startswith("v") else f"v{version}"
        return self._model_dir(slug) / "versions" / v

    def _find_slug_by_id(self, model_id: str) -> str | None:
        with self._index_lock:
            for entry in self._index:
                if entry["id"] == model_id:
                    return entry["slug"]
        return None

    def _find_version_in_model(self, slug: str, version_id: str) -> tuple[str, dict] | None:
        """Find a version by UUID within a model. Returns (version_string, data)."""
        versions_dir = self._model_dir(slug) / "versions"
        if not versions_dir.exists():
            return None
        for vdir in versions_dir.iterdir():
            if not vdir.is_dir():
                continue
            vyaml = vdir / "version.yaml"
            if vyaml.exists():
                data = YAMLFile.read(vyaml)
                if data.get("id") == version_id:
                    return data["version"], data
        return None

    def _find_version_globally(self, version_id: str) -> tuple[str, str, str, dict] | None:
        """Search all models for a version. Returns (model_id, slug, version_str, data)."""
        with self._index_lock:
            entries = list(self._index)
        for entry in entries:
            result = self._find_version_in_model(entry["slug"], version_id)
            if result:
                return entry["id"], entry["slug"], result[0], result[1]
        return None

    # ── Model Asset CRUD ──

    def create_model(self, data: dict) -> dict:
        from fastapi import HTTPException

        name = data["name"]
        slug = slugify(name)

        # Check name uniqueness
        with self._index_lock:
            for entry in self._index:
                if entry["name"] == name:
                    raise HTTPException(409, f"Model with name '{name}' already exists")

        # Handle slug collision
        original_slug = slug
        counter = 1
        while self._model_dir(slug).exists():
            slug = f"{original_slug}-{counter}"
            counter += 1

        now = _now_str()
        model_data = {
            "id": _new_id(),
            "name": name,
            "slug": slug,
            "description": data.get("description"),
            "task_type": data["task_type"],
            "algorithm_type": data["algorithm_type"],
            "framework": data["framework"],
            "owner_org": data["owner_org"],
            "status": "draft",
            "tags": data.get("tags"),
            "applicable_scenarios": data.get("applicable_scenarios"),
            "algorithm_description": data.get("algorithm_description"),
            "input_schema": data.get("input_schema"),
            "output_schema": data.get("output_schema"),
            "created_at": now,
            "updated_at": now,
        }

        self._model_dir(slug).mkdir(parents=True, exist_ok=True)
        (self._model_dir(slug) / "versions").mkdir(exist_ok=True)
        YAMLFile.write(self._model_yaml_path(slug), model_data)
        self._update_index_entry(model_data, version_count=0)

        return {**model_data, "version_count": 0}

    def list_models(
        self,
        *,
        task_type: str | None = None,
        algorithm_type: str | None = None,
        owner_org: str | None = None,
        framework: str | None = None,
        status: str | None = None,
        q: str | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> list[dict]:
        with self._index_lock:
            results = list(self._index)

        if task_type:
            results = [m for m in results if m["task_type"] == task_type]
        if algorithm_type:
            results = [m for m in results if m["algorithm_type"] == algorithm_type]
        if owner_org:
            results = [m for m in results if m["owner_org"] == owner_org]
        if framework:
            results = [m for m in results if m["framework"] == framework]
        if status:
            status_val = status.value if hasattr(status, "value") else status
            results = [m for m in results if m["status"] == status_val]
        if q:
            q_lower = q.lower()
            results = [
                m
                for m in results
                if q_lower in (m.get("name") or "").lower()
                or q_lower in (m.get("description") or "").lower()
            ]

        results.sort(key=lambda m: m.get("updated_at", ""), reverse=True)
        return results[skip : skip + limit]

    def get_model(self, model_id: str) -> dict:
        from fastapi import HTTPException

        slug = self._find_slug_by_id(model_id)
        if not slug:
            raise HTTPException(404, "Model not found")
        data = YAMLFile.read(self._model_yaml_path(slug))
        versions_dir = self._model_dir(slug) / "versions"
        vc = 0
        if versions_dir.exists():
            vc = len([d for d in versions_dir.iterdir() if d.is_dir()])
        data["version_count"] = vc
        return data

    def update_model(self, model_id: str, updates: dict) -> dict:
        from fastapi import HTTPException

        slug = self._find_slug_by_id(model_id)
        if not slug:
            raise HTTPException(404, "Model not found")

        data = YAMLFile.read(self._model_yaml_path(slug))

        if "name" in updates and updates["name"] is not None and updates["name"] != data["name"]:
            new_name = updates["name"]
            with self._index_lock:
                for entry in self._index:
                    if entry["name"] == new_name and entry["id"] != model_id:
                        raise HTTPException(
                            409, f"Model with name '{new_name}' already exists"
                        )
            new_slug = slugify(new_name)
            if new_slug != slug and self._model_dir(new_slug).exists():
                counter = 1
                while self._model_dir(f"{new_slug}-{counter}").exists():
                    counter += 1
                new_slug = f"{new_slug}-{counter}"
            if new_slug != slug:
                self._model_dir(slug).rename(self._model_dir(new_slug))
                slug = new_slug
                data["slug"] = slug

        for key, value in updates.items():
            if value is not None:
                data[key] = value
        data["updated_at"] = _now_str()

        YAMLFile.write(self._model_yaml_path(slug), data)
        self._update_index_entry(data)

        versions_dir = self._model_dir(slug) / "versions"
        vc = 0
        if versions_dir.exists():
            vc = len([d for d in versions_dir.iterdir() if d.is_dir()])
        data["version_count"] = vc
        return data

    def transition_status(self, model_id: str, target_status: str | AssetStatus) -> dict:
        from fastapi import HTTPException

        slug = self._find_slug_by_id(model_id)
        if not slug:
            raise HTTPException(404, "Model not found")

        data = YAMLFile.read(self._model_yaml_path(slug))
        current = AssetStatus(data["status"])
        target = AssetStatus(target_status) if isinstance(target_status, str) else target_status

        allowed = ASSET_STATUS_TRANSITIONS.get(current, set())
        if target not in allowed:
            raise HTTPException(
                422,
                f"Cannot transition from '{current.value}' to '{target.value}'. "
                f"Allowed: {[s.value for s in allowed]}",
            )

        data["status"] = target.value
        data["updated_at"] = _now_str()
        YAMLFile.write(self._model_yaml_path(slug), data)
        self._update_index_entry(data)

        versions_dir = self._model_dir(slug) / "versions"
        vc = len([d for d in versions_dir.iterdir() if d.is_dir()]) if versions_dir.exists() else 0
        data["version_count"] = vc
        return data

    def delete_model(self, model_id: str) -> None:
        from fastapi import HTTPException

        slug = self._find_slug_by_id(model_id)
        if not slug:
            raise HTTPException(404, "Model not found")
        shutil.rmtree(self._model_dir(slug))
        self._remove_from_index(model_id)

    def get_version_count(self, model_id: str) -> int:
        slug = self._find_slug_by_id(model_id)
        if not slug:
            return 0
        versions_dir = self._model_dir(slug) / "versions"
        if not versions_dir.exists():
            return 0
        return len([d for d in versions_dir.iterdir() if d.is_dir()])

    # ── Pipeline Definition ──

    def get_pipeline(self, model_id: str) -> dict | None:
        from fastapi import HTTPException

        slug = self._find_slug_by_id(model_id)
        if not slug:
            raise HTTPException(404, "Model not found")
        path = self._model_dir(slug) / "pipeline.yaml"
        if not path.exists():
            return None
        return YAMLFile.read(path)

    def save_pipeline(self, model_id: str, yaml_text: str) -> dict:
        from fastapi import HTTPException

        slug = self._find_slug_by_id(model_id)
        if not slug:
            raise HTTPException(404, "Model not found")
        data = yaml.safe_load(yaml_text)
        if not isinstance(data, dict):
            raise HTTPException(422, "Invalid pipeline YAML: must be a mapping")
        path = self._model_dir(slug) / "pipeline.yaml"
        YAMLFile.write(path, data)
        return data

    def delete_pipeline(self, model_id: str) -> None:
        from fastapi import HTTPException

        slug = self._find_slug_by_id(model_id)
        if not slug:
            raise HTTPException(404, "Model not found")
        path = self._model_dir(slug) / "pipeline.yaml"
        if path.exists():
            path.unlink()

    # ── Model Version CRUD ──

    def create_version(self, model_id: str, data: dict, file: Any) -> dict:
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

        # Create subdirectories
        for sub in ("datasets", "code", "features", "params"):
            (vdir / sub).mkdir(exist_ok=True)

        now = _now_str()
        parent_version_id = data.get("parent_version_id")

        version_data = {
            "id": _new_id(),
            "version": version_str,
            "description": data.get("description"),
            "file_format": data.get("file_format", "joblib"),
            "file_path": f"weights/{filename}",
            "file_size_bytes": size,
            "metrics": data.get("metrics"),
            "stage": "development",
            "parent_version_id": parent_version_id,
            "created_at": now,
            "updated_at": now,
        }

        YAMLFile.write(vdir / "version.yaml", version_data)

        # Update model timestamp
        model_data = YAMLFile.read(self._model_yaml_path(slug))
        model_data["updated_at"] = now
        YAMLFile.write(self._model_yaml_path(slug), model_data)
        self._update_index_entry(model_data)

        version_data["asset_id"] = model_id
        return version_data

    def list_versions(self, model_id: str) -> list[dict]:
        from fastapi import HTTPException

        slug = self._find_slug_by_id(model_id)
        if not slug:
            raise HTTPException(404, "Model not found")

        versions = []
        versions_dir = self._model_dir(slug) / "versions"
        if versions_dir.exists():
            for vdir in sorted(versions_dir.iterdir(), reverse=True):
                if not vdir.is_dir():
                    continue
                vyaml = vdir / "version.yaml"
                if vyaml.exists():
                    data = YAMLFile.read(vyaml)
                    data["asset_id"] = model_id
                    versions.append(data)
        return versions

    def get_version(self, model_id: str, version_id: str) -> dict:
        from fastapi import HTTPException

        slug = self._find_slug_by_id(model_id)
        if not slug:
            raise HTTPException(404, "Model not found")
        result = self._find_version_in_model(slug, version_id)
        if not result:
            raise HTTPException(404, "Version not found")
        _, data = result
        data["asset_id"] = model_id
        return data

    def transition_stage(
        self, model_id: str, version_id: str, target_stage: str | VersionStage
    ) -> dict:
        from fastapi import HTTPException

        slug = self._find_slug_by_id(model_id)
        if not slug:
            raise HTTPException(404, "Model not found")
        result = self._find_version_in_model(slug, version_id)
        if not result:
            raise HTTPException(404, "Version not found")

        version_str, data = result
        current = VersionStage(data["stage"])
        target = VersionStage(target_stage) if isinstance(target_stage, str) else target_stage

        allowed = VERSION_STAGE_TRANSITIONS.get(current, set())
        if target not in allowed:
            raise HTTPException(
                422,
                f"Cannot transition from '{current.value}' to '{target.value}'. "
                f"Allowed: {[s.value for s in allowed]}",
            )

        data["stage"] = target.value
        data["updated_at"] = _now_str()
        YAMLFile.write(self._version_dir(slug, version_str) / "version.yaml", data)

        data["asset_id"] = model_id
        return data

    def get_version_file_path(self, model_id: str, version_id: str) -> Path:
        from fastapi import HTTPException

        slug = self._find_slug_by_id(model_id)
        if not slug:
            raise HTTPException(404, "Model not found")
        result = self._find_version_in_model(slug, version_id)
        if not result:
            raise HTTPException(404, "Version not found")
        version_str, data = result
        if not data.get("file_path"):
            raise HTTPException(404, "No file associated with this version")
        path = self._version_dir(slug, version_str) / data["file_path"]
        if not path.exists():
            raise HTTPException(404, "Model file not found on storage")
        return path

    # ── Version Artifacts ──

    _ARTIFACT_CATEGORIES = {"datasets", "code", "features", "params"}

    def _resolve_version_dir(self, model_id: str, version_id: str) -> tuple[str, str, Path]:
        """Resolve model_id + version_id to (slug, version_str, version_dir)."""
        from fastapi import HTTPException

        slug = self._find_slug_by_id(model_id)
        if not slug:
            raise HTTPException(404, "Model not found")
        result = self._find_version_in_model(slug, version_id)
        if not result:
            raise HTTPException(404, "Version not found")
        version_str, _ = result
        return slug, version_str, self._version_dir(slug, version_str)

    def list_version_artifacts(
        self, model_id: str, version_id: str, category: str,
    ) -> list[dict]:
        from fastapi import HTTPException

        if category not in self._ARTIFACT_CATEGORIES:
            raise HTTPException(400, f"Invalid category: {category}")
        _, _, vdir = self._resolve_version_dir(model_id, version_id)
        cat_dir = vdir / category
        if not cat_dir.exists():
            return []
        files = []
        for f in sorted(cat_dir.iterdir()):
            if f.is_file():
                stat = f.stat()
                files.append({
                    "name": f.name,
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(
                        stat.st_mtime, tz=timezone.utc,
                    ).isoformat(),
                })
        return files

    def read_version_artifact(
        self, model_id: str, version_id: str, category: str, filename: str,
    ) -> str:
        from fastapi import HTTPException

        if category not in self._ARTIFACT_CATEGORIES:
            raise HTTPException(400, f"Invalid category: {category}")
        if ".." in filename or "/" in filename:
            raise HTTPException(400, "Invalid filename")
        _, _, vdir = self._resolve_version_dir(model_id, version_id)
        path = vdir / category / filename
        if not path.is_file():
            raise HTTPException(404, f"File not found: {category}/{filename}")
        return path.read_text(encoding="utf-8")

    def preview_dataset(
        self,
        model_id: str,
        version_id: str,
        filename: str,
        offset: int = 0,
        limit: int = 100,
    ) -> dict:
        import pandas as pd
        from fastapi import HTTPException

        if ".." in filename or "/" in filename:
            raise HTTPException(400, "Invalid filename")
        _, _, vdir = self._resolve_version_dir(model_id, version_id)
        path = vdir / "datasets" / filename
        if not path.is_file():
            raise HTTPException(404, f"Dataset not found: {filename}")
        if not filename.endswith(".csv"):
            raise HTTPException(400, "Only CSV files can be previewed")

        df = pd.read_csv(path)
        total_rows = len(df)
        page = df.iloc[offset : offset + limit]

        return {
            "columns": list(df.columns),
            "dtypes": {col: str(dt) for col, dt in df.dtypes.items()},
            "rows": page.values.tolist(),
            "total_rows": total_rows,
            "offset": offset,
            "limit": limit,
        }

    # ── Feature Definitions (Global Catalog) ──

    def _read_feature_catalog(self) -> dict:
        data = YAMLFile.read(self.catalog_dir / "features.yaml")
        if not data:
            return {"definitions": [], "groups": [], "model_associations": []}
        data.setdefault("definitions", [])
        data.setdefault("groups", [])
        data.setdefault("model_associations", [])
        return data

    def _write_feature_catalog(self, data: dict) -> None:
        YAMLFile.write(self.catalog_dir / "features.yaml", data)

    def create_feature_definition(self, data: dict) -> dict:
        from fastapi import HTTPException

        catalog = self._read_feature_catalog()
        defs = catalog["definitions"]

        for d in defs:
            if d["name"] == data["name"]:
                raise HTTPException(409, f"Feature '{data['name']}' already exists")

        now = _now_str()
        feature = {
            "id": _new_id(),
            "name": data["name"],
            "data_type": data["data_type"],
            "description": data.get("description"),
            "unit": data.get("unit"),
            "computation_logic": data.get("computation_logic"),
            "value_range": data.get("value_range"),
            "created_at": now,
            "updated_at": now,
        }
        defs.append(feature)
        catalog["definitions"] = defs
        self._write_feature_catalog(catalog)
        return feature

    def list_feature_definitions(
        self,
        *,
        data_type: str | None = None,
        q: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[dict]:
        catalog = self._read_feature_catalog()
        defs = catalog["definitions"]
        if data_type:
            defs = [d for d in defs if d["data_type"] == data_type]
        if q:
            q_lower = q.lower()
            defs = [d for d in defs if q_lower in d["name"].lower()]
        defs.sort(key=lambda d: d["name"])
        return defs[skip : skip + limit]

    def get_feature_definition(self, feature_id: str) -> dict:
        from fastapi import HTTPException

        catalog = self._read_feature_catalog()
        for d in catalog["definitions"]:
            if d["id"] == feature_id:
                return d
        raise HTTPException(404, "Feature definition not found")

    def update_feature_definition(self, feature_id: str, updates: dict) -> dict:
        from fastapi import HTTPException

        catalog = self._read_feature_catalog()
        for i, d in enumerate(catalog["definitions"]):
            if d["id"] == feature_id:
                for key, value in updates.items():
                    if value is not None:
                        d[key] = value
                d["updated_at"] = _now_str()
                catalog["definitions"][i] = d
                self._write_feature_catalog(catalog)
                return d
        raise HTTPException(404, "Feature definition not found")

    def delete_feature_definition(self, feature_id: str) -> None:
        from fastapi import HTTPException

        catalog = self._read_feature_catalog()
        original_len = len(catalog["definitions"])
        catalog["definitions"] = [d for d in catalog["definitions"] if d["id"] != feature_id]
        if len(catalog["definitions"]) == original_len:
            raise HTTPException(404, "Feature definition not found")
        self._write_feature_catalog(catalog)

    # ── Feature Groups (Global Catalog) ──

    def _resolve_group(self, group: dict, defs: list[dict]) -> dict:
        def_map = {d["id"]: d for d in defs}
        resolved = dict(group)
        resolved["features"] = [
            def_map[fid] for fid in group.get("feature_ids", []) if fid in def_map
        ]
        return resolved

    def create_feature_group(self, data: dict) -> dict:
        from fastapi import HTTPException

        catalog = self._read_feature_catalog()
        groups = catalog["groups"]
        defs = catalog["definitions"]

        for g in groups:
            if g["name"] == data["name"]:
                raise HTTPException(409, f"Feature group '{data['name']}' already exists")

        def_ids = {d["id"] for d in defs}
        for fid in data.get("feature_ids", []):
            if fid not in def_ids:
                raise HTTPException(404, f"Feature definition '{fid}' not found")

        now = _now_str()
        group = {
            "id": _new_id(),
            "name": data["name"],
            "description": data.get("description"),
            "scenario_tags": data.get("scenario_tags"),
            "feature_ids": data.get("feature_ids", []),
            "created_at": now,
            "updated_at": now,
        }
        groups.append(group)
        catalog["groups"] = groups
        self._write_feature_catalog(catalog)
        return self._resolve_group(group, defs)

    def list_feature_groups(
        self, *, q: str | None = None, skip: int = 0, limit: int = 50
    ) -> list[dict]:
        catalog = self._read_feature_catalog()
        groups = catalog["groups"]
        defs = catalog["definitions"]
        if q:
            q_lower = q.lower()
            groups = [g for g in groups if q_lower in g["name"].lower()]
        groups.sort(key=lambda g: g["name"])
        return [self._resolve_group(g, defs) for g in groups[skip : skip + limit]]

    def get_feature_group(self, group_id: str) -> dict:
        from fastapi import HTTPException

        catalog = self._read_feature_catalog()
        for g in catalog["groups"]:
            if g["id"] == group_id:
                return self._resolve_group(g, catalog["definitions"])
        raise HTTPException(404, "Feature group not found")

    def update_feature_group(self, group_id: str, updates: dict) -> dict:
        from fastapi import HTTPException

        catalog = self._read_feature_catalog()
        defs = catalog["definitions"]

        if "feature_ids" in updates:
            def_ids = {d["id"] for d in defs}
            for fid in updates["feature_ids"]:
                if fid not in def_ids:
                    raise HTTPException(404, f"Feature definition '{fid}' not found")

        for i, g in enumerate(catalog["groups"]):
            if g["id"] == group_id:
                for key, value in updates.items():
                    if value is not None:
                        g[key] = value
                g["updated_at"] = _now_str()
                catalog["groups"][i] = g
                self._write_feature_catalog(catalog)
                return self._resolve_group(g, defs)
        raise HTTPException(404, "Feature group not found")

    def delete_feature_group(self, group_id: str) -> None:
        from fastapi import HTTPException

        catalog = self._read_feature_catalog()
        original_len = len(catalog["groups"])
        catalog["groups"] = [g for g in catalog["groups"] if g["id"] != group_id]
        if len(catalog["groups"]) == original_len:
            raise HTTPException(404, "Feature group not found")
        catalog["model_associations"] = [
            a for a in catalog["model_associations"] if a["group_id"] != group_id
        ]
        self._write_feature_catalog(catalog)

    # ── Model ↔ FeatureGroup Association ──

    def associate_model_group(self, model_id: str, group_id: str) -> None:
        from fastapi import HTTPException

        if not self._find_slug_by_id(model_id):
            raise HTTPException(404, "Model not found")
        self.get_feature_group(group_id)

        catalog = self._read_feature_catalog()
        associations = catalog["model_associations"]
        if any(a["model_id"] == model_id and a["group_id"] == group_id for a in associations):
            return
        associations.append({"model_id": model_id, "group_id": group_id})
        catalog["model_associations"] = associations
        self._write_feature_catalog(catalog)

    def disassociate_model_group(self, model_id: str, group_id: str) -> None:
        catalog = self._read_feature_catalog()
        catalog["model_associations"] = [
            a
            for a in catalog["model_associations"]
            if not (a["model_id"] == model_id and a["group_id"] == group_id)
        ]
        self._write_feature_catalog(catalog)

    def list_model_groups(self, model_id: str) -> list[dict]:
        from fastapi import HTTPException

        if not self._find_slug_by_id(model_id):
            raise HTTPException(404, "Model not found")

        catalog = self._read_feature_catalog()
        group_ids = [
            a["group_id"]
            for a in catalog["model_associations"]
            if a["model_id"] == model_id
        ]
        if not group_ids:
            return []

        defs = catalog["definitions"]
        return [
            self._resolve_group(g, defs)
            for g in catalog["groups"]
            if g["id"] in group_ids
        ]

    # ── Parameter Templates (Global Catalog) ──

    def _read_param_catalog(self) -> dict:
        data = YAMLFile.read(self.catalog_dir / "parameter_templates.yaml")
        if not data:
            return {"templates": []}
        data.setdefault("templates", [])
        return data

    def _write_param_catalog(self, data: dict) -> None:
        YAMLFile.write(self.catalog_dir / "parameter_templates.yaml", data)

    def create_parameter_template(self, data: dict) -> dict:
        catalog = self._read_param_catalog()
        templates = catalog["templates"]

        now = _now_str()
        template = {
            "id": _new_id(),
            "name": data["name"],
            "model_asset_id": data.get("model_asset_id"),
            "algorithm_type": data.get("algorithm_type"),
            "scenario_tags": data.get("scenario_tags"),
            "parameters": data["parameters"],
            "performance_notes": data.get("performance_notes"),
            "created_at": now,
            "updated_at": now,
        }
        templates.append(template)
        catalog["templates"] = templates
        self._write_param_catalog(catalog)
        return template

    def list_parameter_templates(
        self,
        *,
        model_asset_id: str | None = None,
        algorithm_type: str | None = None,
        q: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[dict]:
        catalog = self._read_param_catalog()
        templates = catalog["templates"]
        if model_asset_id:
            templates = [t for t in templates if t.get("model_asset_id") == model_asset_id]
        if algorithm_type:
            templates = [t for t in templates if t.get("algorithm_type") == algorithm_type]
        if q:
            q_lower = q.lower()
            templates = [t for t in templates if q_lower in t["name"].lower()]
        templates.sort(key=lambda t: t.get("updated_at", ""), reverse=True)
        return templates[skip : skip + limit]

    def get_parameter_template(self, template_id: str) -> dict:
        from fastapi import HTTPException

        catalog = self._read_param_catalog()
        for t in catalog["templates"]:
            if t["id"] == template_id:
                return t
        raise HTTPException(404, "Parameter template not found")

    def update_parameter_template(self, template_id: str, updates: dict) -> dict:
        from fastapi import HTTPException

        catalog = self._read_param_catalog()
        for i, t in enumerate(catalog["templates"]):
            if t["id"] == template_id:
                for key, value in updates.items():
                    if value is not None:
                        t[key] = value
                t["updated_at"] = _now_str()
                catalog["templates"][i] = t
                self._write_param_catalog(catalog)
                return t
        raise HTTPException(404, "Parameter template not found")

    def delete_parameter_template(self, template_id: str) -> None:
        from fastapi import HTTPException

        catalog = self._read_param_catalog()
        original_len = len(catalog["templates"])
        catalog["templates"] = [t for t in catalog["templates"] if t["id"] != template_id]
        if len(catalog["templates"]) == original_len:
            raise HTTPException(404, "Parameter template not found")
        self._write_param_catalog(catalog)

    # ── Deployments ──

    def _read_deployments(self) -> list[dict]:
        data = YAMLFile.read(self.deployments_dir / "deployments.yaml")
        return data.get("deployments", []) if data else []

    def _write_deployments(self, deployments: list[dict]) -> None:
        YAMLFile.write(self.deployments_dir / "deployments.yaml", {"deployments": deployments})

    def create_deployment(self, data: dict) -> dict:
        from fastapi import HTTPException

        version_id = data["model_version_id"]
        info = self._find_version_globally(version_id)
        if not info:
            raise HTTPException(404, "Model version not found")
        model_id, slug, version_str, version_data = info

        now = _now_str()
        deployment = {
            "id": _new_id(),
            "name": data["name"],
            "model_version_id": version_id,
            "model_id": model_id,
            "model_slug": slug,
            "version_string": version_str,
            "file_format": version_data.get("file_format", "joblib"),
            "status": "pending",
            "endpoint_config": data.get("endpoint_config"),
            "error_message": None,
            "created_at": now,
            "updated_at": now,
        }

        deployments = self._read_deployments()
        deployments.append(deployment)
        self._write_deployments(deployments)
        return deployment

    def list_deployments(
        self,
        *,
        status: str | None = None,
        model_version_id: str | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> list[dict]:
        deployments = self._read_deployments()
        if status:
            status_val = status.value if hasattr(status, "value") else status
            deployments = [d for d in deployments if d["status"] == status_val]
        if model_version_id:
            deployments = [d for d in deployments if d["model_version_id"] == model_version_id]
        deployments.sort(key=lambda d: d.get("created_at", ""), reverse=True)
        return deployments[skip : skip + limit]

    def get_deployment(self, deployment_id: str) -> dict:
        from fastapi import HTTPException

        for d in self._read_deployments():
            if d["id"] == deployment_id:
                return d
        raise HTTPException(404, "Deployment not found")

    def _update_deployment(self, deployment_id: str, updates: dict) -> dict:
        from fastapi import HTTPException

        deployments = self._read_deployments()
        for i, d in enumerate(deployments):
            if d["id"] == deployment_id:
                for key, value in updates.items():
                    d[key] = value
                d["updated_at"] = _now_str()
                deployments[i] = d
                self._write_deployments(deployments)
                return d
        raise HTTPException(404, "Deployment not found")

    def start_deployment(self, deployment_id: str, inference_manager: Any) -> dict:
        from fastapi import HTTPException

        deployment = self.get_deployment(deployment_id)
        if deployment["status"] == "running":
            return deployment

        slug = deployment["model_slug"]
        version_str = deployment["version_string"]
        vdir = self._version_dir(slug, version_str)
        version_data = YAMLFile.read(vdir / "version.yaml")
        file_path_rel = version_data.get("file_path")
        if not file_path_rel:
            raise HTTPException(400, "Model version has no file")

        file_path = vdir / file_path_rel
        if not file_path.exists():
            raise HTTPException(400, "Model file not found on storage")

        try:
            inference_manager.deploy(deployment_id, file_path, deployment["file_format"])
            return self._update_deployment(
                deployment_id, {"status": "running", "error_message": None}
            )
        except Exception as e:
            return self._update_deployment(
                deployment_id, {"status": "failed", "error_message": str(e)}
            )

    def stop_deployment(self, deployment_id: str, inference_manager: Any) -> dict:
        self.get_deployment(deployment_id)
        inference_manager.undeploy(deployment_id)
        return self._update_deployment(deployment_id, {"status": "stopped"})

    def delete_deployment(self, deployment_id: str, inference_manager: Any) -> None:
        from fastapi import HTTPException

        self.get_deployment(deployment_id)
        inference_manager.undeploy(deployment_id)

        deployments = self._read_deployments()
        original_len = len(deployments)
        deployments = [d for d in deployments if d["id"] != deployment_id]
        if len(deployments) == original_len:
            raise HTTPException(404, "Deployment not found")
        self._write_deployments(deployments)

        # Clean up log file
        log_path = self.logs_dir / f"{deployment_id}.jsonl"
        if log_path.exists():
            log_path.unlink()

    def predict(self, deployment_id: str, input_data: Any, inference_manager: Any) -> tuple:
        import time

        from fastapi import HTTPException

        deployment = self.get_deployment(deployment_id)
        if deployment["status"] != "running":
            raise HTTPException(
                400, f"Deployment is not running (status: {deployment['status']})"
            )

        start = time.perf_counter()
        try:
            result = inference_manager.predict(deployment_id, input_data)
        except KeyError:
            raise HTTPException(400, "Model not loaded in memory")
        except Exception as e:
            raise HTTPException(500, f"Prediction failed: {e}")
        latency_ms = (time.perf_counter() - start) * 1000

        return result, latency_ms

    # ── Prediction Logs ──

    def _log_path(self, deployment_id: str) -> Path:
        return self.logs_dir / f"{deployment_id}.jsonl"

    def log_prediction(
        self,
        deployment_id: str,
        input_data: Any,
        output_data: Any,
        latency_ms: float,
        error: str | None = None,
    ) -> dict:
        record = {
            "id": _new_id(),
            "deployment_id": deployment_id,
            "input_data": input_data if isinstance(input_data, dict) else {"data": input_data},
            "output_data": output_data if isinstance(output_data, dict) else {"value": output_data},
            "actual_value": None,
            "latency_ms": latency_ms,
            "error": error,
            "created_at": _now_str(),
            "actual_submitted_at": None,
        }
        JSONLFile.append(self._log_path(deployment_id), record)
        return record

    def list_predictions(
        self,
        deployment_id: str,
        *,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[dict]:
        self.get_deployment(deployment_id)
        records = JSONLFile.read_all(self._log_path(deployment_id))

        if start_time:
            records = [r for r in records if r["created_at"] >= start_time.isoformat()]
        if end_time:
            records = [r for r in records if r["created_at"] <= end_time.isoformat()]

        records.sort(key=lambda r: r["created_at"], reverse=True)
        return records[skip : skip + limit]

    def submit_actuals(self, deployment_id: str, actuals: list[dict]) -> tuple[int, list[str]]:
        self.get_deployment(deployment_id)
        log_path = self._log_path(deployment_id)
        records = JSONLFile.read_all(log_path)

        record_map = {r["id"]: r for r in records}
        updated = 0
        not_found = []
        now = _now_str()

        for item in actuals:
            pid = item["prediction_id"]
            if pid in record_map:
                actual = item["actual_value"]
                record_map[pid]["actual_value"] = (
                    actual if isinstance(actual, dict) else {"value": actual}
                )
                record_map[pid]["actual_submitted_at"] = now
                updated += 1
            else:
                not_found.append(pid)

        if updated > 0:
            JSONLFile.write_all(log_path, records)

        return updated, not_found

    def compute_metrics(
        self,
        deployment_id: str,
        *,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> dict:
        self.get_deployment(deployment_id)
        records = JSONLFile.read_all(self._log_path(deployment_id))

        if start_time:
            records = [r for r in records if r["created_at"] >= start_time.isoformat()]
        if end_time:
            records = [r for r in records if r["created_at"] <= end_time.isoformat()]

        logs_with_actuals = [r for r in records if r.get("actual_value") is not None]
        if not logs_with_actuals:
            return {"count": 0}

        predicted = []
        actual = []
        for log in logs_with_actuals:
            p = self._extract_value(log["output_data"])
            a = self._extract_value(log["actual_value"])
            if p is not None and a is not None:
                predicted.append(p)
                actual.append(a)

        if not predicted:
            return {"count": 0}

        n = len(predicted)
        mae = sum(abs(a - p) for a, p in zip(actual, predicted)) / n
        rmse = math.sqrt(sum((a - p) ** 2 for a, p in zip(actual, predicted)) / n)

        mape_values = [abs((a - p) / a) for a, p in zip(actual, predicted) if a != 0]
        mape = (sum(mape_values) / len(mape_values) * 100) if mape_values else None

        return {
            "count": n,
            "mae": round(mae, 4),
            "rmse": round(rmse, 4),
            "mape": round(mape, 4) if mape is not None else None,
            "period_start": start_time,
            "period_end": end_time,
        }

    def compute_stats(
        self,
        deployment_id: str,
        *,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> dict:
        self.get_deployment(deployment_id)
        records = JSONLFile.read_all(self._log_path(deployment_id))

        if start_time:
            records = [r for r in records if r["created_at"] >= start_time.isoformat()]
        if end_time:
            records = [r for r in records if r["created_at"] <= end_time.isoformat()]

        if not records:
            return {
                "total_predictions": 0,
                "error_count": 0,
                "error_rate": 0.0,
                "avg_latency_ms": 0.0,
                "p95_latency_ms": 0.0,
                "period_start": start_time,
                "period_end": end_time,
            }

        total = len(records)
        error_count = sum(1 for r in records if r.get("error"))
        latencies = sorted(r["latency_ms"] for r in records)
        p95_idx = min(int(total * 0.95), total - 1)

        return {
            "total_predictions": total,
            "error_count": error_count,
            "error_rate": round(error_count / total, 4),
            "avg_latency_ms": round(sum(latencies) / total, 3),
            "p95_latency_ms": round(latencies[p95_idx], 3),
            "period_start": start_time,
            "period_end": end_time,
        }

    @staticmethod
    def _extract_value(data: Any) -> float | None:
        if isinstance(data, dict):
            if "value" in data:
                v = data["value"]
                if isinstance(v, list):
                    return float(v[0]) if v else None
                return float(v)
            for v in data.values():
                if isinstance(v, (int, float)):
                    return float(v)
        if isinstance(data, (int, float)):
            return float(data)
        return None


# ── Dependency injection ──

_store: ModelStore | None = None


def get_store() -> ModelStore:
    global _store
    if _store is None:
        from modelforge.config import settings

        _store = ModelStore(settings.MODEL_STORE_PATH)
    return _store
