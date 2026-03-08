"""YAML-file backed implementation of MetadataStore protocol.

All model/version/deployment/catalog metadata is stored in YAML files
on the local filesystem.  This adapter owns *metadata only* — binary
artifacts are handled by ArtifactStore.
"""

from __future__ import annotations

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

from modelforge.adapters.filesystem.yaml_io import JSONLFile, YAMLFile
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


class YAMLMetadataStore:
    """YAML-file backed metadata storage.

    Directory layout::

        <base_path>/
          models/<slug>/
            model.yaml
            pipeline.yaml
            versions/<vN>/version.yaml
            runs/<run_id>.yaml
          deployments/deployments.yaml
          logs/<deployment_id>.jsonl
          catalog/features.yaml
          catalog/parameter_templates.yaml
          index.yaml
    """

    def __init__(self, base_path: Path) -> None:
        self.base_path = Path(base_path)
        self._index_lock = threading.RLock()
        self._index: list[dict] = []

        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.deployments_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.catalog_dir.mkdir(parents=True, exist_ok=True)

        self._rebuild_index()

    # ── Directory properties ──

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

    def _runs_dir(self, slug: str) -> Path:
        return self._model_dir(slug) / "runs"

    def get_model_slug(self, model_id: str) -> str | None:
        return self._find_slug_by_id(model_id)

    def _find_slug_by_id(self, model_id: str) -> str | None:
        with self._index_lock:
            for entry in self._index:
                if entry["id"] == model_id:
                    return entry["slug"]
        return None

    def _find_version_in_model(self, slug: str, version_id: str) -> tuple[str, dict] | None:
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

    def find_version_globally(self, version_id: str) -> tuple[str, str, str, dict] | None:
        with self._index_lock:
            entries = list(self._index)
        for entry in entries:
            result = self._find_version_in_model(entry["slug"], version_id)
            if result:
                return entry["id"], entry["slug"], result[0], result[1]
        return None

    # ── Model CRUD ──

    def create_model(self, data: dict) -> dict:
        from fastapi import HTTPException

        name = data["name"]
        slug = slugify(name)

        with self._index_lock:
            for entry in self._index:
                if entry["name"] == name:
                    raise HTTPException(409, f"Model with name '{name}' already exists")

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
        search: str | None = None,
        scenario: str | None = None,
        region: str | None = None,
        season: str | None = None,
        equipment_type: str | None = None,
        voltage_level: str | None = None,
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

        # Text search
        q_term = q or search
        if q_term:
            q_lower = q_term.lower()
            results = [
                m
                for m in results
                if q_lower in (m.get("name") or "").lower()
                or q_lower in (m.get("description") or "").lower()
            ]

        # Scenario filters
        if region:
            results = [
                m for m in results
                if region in (m.get("applicable_scenarios") or {}).get("region", [])
            ]
        if season:
            results = [
                m for m in results
                if season in (m.get("applicable_scenarios") or {}).get("season", [])
                or "all" in (m.get("applicable_scenarios") or {}).get("season", [])
            ]
        if equipment_type:
            results = [
                m for m in results
                if equipment_type in (m.get("applicable_scenarios") or {}).get("equipment_type", [])
            ]
        if voltage_level:
            results = [
                m for m in results
                if voltage_level in (m.get("applicable_scenarios") or {}).get("voltage_level", [])
            ]

        results.sort(key=lambda m: m.get("updated_at", ""), reverse=True)
        return results[skip: skip + limit]

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

    def transition_status(self, model_id: str, target_status: str) -> dict:
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

    # ── Pipeline ──

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

    # ── Pipeline Runs ──

    def create_run(self, model_id: str, data: dict) -> dict:
        from fastapi import HTTPException

        slug = self._find_slug_by_id(model_id)
        if not slug:
            raise HTTPException(404, "Model not found")

        runs_dir = self._runs_dir(slug)
        runs_dir.mkdir(parents=True, exist_ok=True)

        now = _now_str()
        run = {
            "id": _new_id(),
            "model_id": model_id,
            "status": "pending",
            "base_version": data.get("base_version"),
            "target_version": data.get("target_version"),
            "pipeline_snapshot": data.get("pipeline_snapshot"),
            "overrides": data.get("overrides"),
            "log": "",
            "metrics": None,
            "result_version_id": None,
            "result_version": None,
            "error": None,
            "started_at": now,
            "finished_at": None,
        }
        YAMLFile.write(runs_dir / f"{run['id']}.yaml", run)
        return run

    def get_run(self, model_id: str, run_id: str) -> dict:
        from fastapi import HTTPException

        slug = self._find_slug_by_id(model_id)
        if not slug:
            raise HTTPException(404, "Model not found")

        path = self._runs_dir(slug) / f"{run_id}.yaml"
        if not path.exists():
            raise HTTPException(404, "Pipeline run not found")
        return YAMLFile.read(path)

    def list_runs(self, model_id: str) -> list[dict]:
        from fastapi import HTTPException

        slug = self._find_slug_by_id(model_id)
        if not slug:
            raise HTTPException(404, "Model not found")

        runs_dir = self._runs_dir(slug)
        if not runs_dir.exists():
            return []

        runs = []
        for f in runs_dir.iterdir():
            if f.suffix == ".yaml":
                run = YAMLFile.read(f)
                run.pop("log", None)
                run.pop("pipeline_snapshot", None)
                runs.append(run)
        runs.sort(key=lambda r: r.get("started_at", ""), reverse=True)
        return runs

    def update_run(self, model_id: str, run_id: str, updates: dict) -> dict:
        from fastapi import HTTPException

        slug = self._find_slug_by_id(model_id)
        if not slug:
            raise HTTPException(404, "Model not found")

        path = self._runs_dir(slug) / f"{run_id}.yaml"
        if not path.exists():
            raise HTTPException(404, "Pipeline run not found")

        data = YAMLFile.read(path)
        data.update(updates)
        YAMLFile.write(path, data)
        return data

    # ── Version CRUD ──

    def get_version_id_by_str(self, slug: str, version_str: str) -> str | None:
        vdir = self._version_dir(slug, version_str)
        vyaml = vdir / "version.yaml"
        if vyaml.exists():
            data = YAMLFile.read(vyaml)
            return data.get("id")
        return None

    def create_version(self, model_id: str, data: dict) -> dict:
        """Create a version record (metadata only, file upload handled by caller)."""
        from fastapi import HTTPException

        slug = self._find_slug_by_id(model_id)
        if not slug:
            raise HTTPException(404, "Model not found")

        version_str = data["version"]
        vdir = self._version_dir(slug, version_str)
        if vdir.exists():
            raise HTTPException(409, f"Version '{version_str}' already exists for this model")

        vdir.mkdir(parents=True)
        for sub in ("weights", "datasets", "code", "features", "params"):
            (vdir / sub).mkdir(exist_ok=True)

        now = _now_str()
        version_data = {
            "id": _new_id(),
            "version": version_str,
            "description": data.get("description"),
            "file_format": data.get("file_format", "joblib"),
            "file_path": data.get("file_path"),
            "file_size_bytes": data.get("file_size_bytes", 0),
            "metrics": data.get("metrics"),
            "stage": data.get("stage", "development"),
            "parent_version_id": data.get("parent_version_id"),
            "source_model_id": data.get("source_model_id"),
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

    def create_version_from_run(
        self,
        model_id: str,
        slug: str,
        version_str: str,
        vdir: Path,
        *,
        metrics: dict | None = None,
        file_format: str = "joblib",
        file_size: int = 0,
        weights_rel: str | None = None,
        parent_version_id: str | None = None,
        source_model_id: str | None = None,
    ) -> dict:
        now = _now_str()
        clean_version = version_str.lstrip("v") if version_str else version_str
        version_data = {
            "id": _new_id(),
            "version": clean_version,
            "description": "Auto-generated by pipeline run",
            "file_format": file_format,
            "file_path": weights_rel or f"weights/model.{file_format}",
            "file_size_bytes": file_size,
            "metrics": metrics,
            "stage": "development",
            "parent_version_id": parent_version_id,
            "source_model_id": source_model_id,
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

    def next_version(self, slug: str, base_version: str) -> str:
        versions_dir = self._model_dir(slug) / "versions"
        existing: set[str] = set()
        if versions_dir.exists():
            existing = {d.name for d in versions_dir.iterdir() if d.is_dir()}

        base = base_version.lstrip("v")
        parts = base.split(".")

        if len(parts) == 3:
            major = int(parts[0])
            minor = int(parts[1])
            patch = int(parts[2])
            candidate = f"v{major}.{minor + 1}.{patch}"
            while candidate in existing:
                minor += 1
                candidate = f"v{major}.{minor + 1}.{patch}"
            return candidate
        else:
            n = 1
            candidate = f"v{base}.{n}"
            while candidate in existing:
                n += 1
                candidate = f"v{base}.{n}"
            return candidate

    def create_draft_version(
        self,
        model_id: str,
        base_version: str,
        description: str | None = None,
    ) -> dict:
        from fastapi import HTTPException

        slug = self._find_slug_by_id(model_id)
        if not slug:
            raise HTTPException(404, "Model not found")

        base_vdir = self._version_dir(slug, base_version).resolve()
        if not base_vdir.exists():
            raise HTTPException(404, f"Base version '{base_version}' not found")

        base_vyaml = base_vdir / "version.yaml"
        if not base_vyaml.exists():
            raise HTTPException(404, f"Base version '{base_version}' has no metadata")
        base_data = YAMLFile.read(base_vyaml)
        base_version_id = base_data.get("id")

        next_ver = self.next_version(slug, base_version)
        new_vdir = self._version_dir(slug, next_ver)

        if new_vdir.exists():
            raise HTTPException(409, f"Version '{next_ver}' already exists")

        shutil.copytree(base_vdir, new_vdir)

        weights_dir = new_vdir / "weights"
        if weights_dir.exists():
            shutil.rmtree(weights_dir)
        weights_dir.mkdir(exist_ok=True)

        old_vyaml = new_vdir / "version.yaml"
        if old_vyaml.exists():
            old_vyaml.unlink()

        for sub in ("datasets", "code", "features", "params"):
            (new_vdir / sub).mkdir(exist_ok=True)

        now = _now_str()
        clean_version = next_ver.lstrip("v")
        version_data = {
            "id": _new_id(),
            "version": clean_version,
            "description": description or f"Draft based on {base_version}",
            "file_format": base_data.get("file_format", "joblib"),
            "file_path": None,
            "file_size_bytes": None,
            "metrics": None,
            "stage": "draft",
            "parent_version_id": base_version_id,
            "created_at": now,
            "updated_at": now,
        }
        YAMLFile.write(new_vdir / "version.yaml", version_data)

        model_data = YAMLFile.read(self._model_yaml_path(slug))
        model_data["updated_at"] = now
        YAMLFile.write(self._model_yaml_path(slug), model_data)
        self._update_index_entry(model_data)

        version_data["asset_id"] = model_id
        return version_data

    def finalize_draft_version(
        self,
        model_id: str,
        slug: str,
        version_str: str,
        vdir: Path,
        *,
        metrics: dict | None = None,
        file_format: str = "joblib",
        file_size: int = 0,
        weights_rel: str | None = None,
    ) -> dict:
        vyaml = vdir / "version.yaml"
        if not vyaml.exists():
            raise FileNotFoundError(f"version.yaml not found in {vdir}")

        data = YAMLFile.read(vyaml)
        now = _now_str()

        data["stage"] = "development"
        data["file_path"] = weights_rel or f"weights/model.{file_format}"
        data["file_size_bytes"] = file_size
        data["file_format"] = file_format
        data["metrics"] = metrics
        data["updated_at"] = now

        YAMLFile.write(vyaml, data)

        model_data = YAMLFile.read(self._model_yaml_path(slug))
        model_data["updated_at"] = now
        YAMLFile.write(self._model_yaml_path(slug), model_data)
        self._update_index_entry(model_data)

        data["asset_id"] = model_id
        return data

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

    def update_version(self, model_id: str, version_id: str, updates: dict) -> dict:
        from fastapi import HTTPException

        slug = self._find_slug_by_id(model_id)
        if not slug:
            raise HTTPException(404, "Model not found")
        result = self._find_version_in_model(slug, version_id)
        if not result:
            raise HTTPException(404, "Version not found")

        version_str, data = result
        for key, value in updates.items():
            if value is not None:
                data[key] = value
        data["updated_at"] = _now_str()
        YAMLFile.write(self._version_dir(slug, version_str) / "version.yaml", data)

        data["asset_id"] = model_id
        return data

    def transition_stage(self, model_id: str, version_id: str, target_stage: str) -> dict:
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
            if data.get("stage") == "draft":
                raise HTTPException(400, "Cannot download from a draft version (not yet trained)")
            raise HTTPException(404, "No file associated with this version")
        path = self._version_dir(slug, version_str) / data["file_path"]
        if not path.exists():
            raise HTTPException(404, "Model file not found on storage")
        return path

    # ── Version Artifacts ──

    _ARTIFACT_CATEGORIES = {"datasets", "code", "features", "params"}
    _MAX_ARTIFACT_SIZE = 50 * 1024 * 1024
    _TEXT_EXTENSIONS = {".py", ".yaml", ".yml", ".txt", ".json", ".md", ".cfg", ".ini", ".toml"}

    def _resolve_version_dir(self, model_id: str, version_id: str) -> tuple[str, str, Path]:
        from fastapi import HTTPException

        slug = self._find_slug_by_id(model_id)
        if not slug:
            raise HTTPException(404, "Model not found")
        result = self._find_version_in_model(slug, version_id)
        if not result:
            raise HTTPException(404, "Version not found")
        version_str, _ = result
        return slug, version_str, self._version_dir(slug, version_str)

    def list_version_artifacts(self, model_id: str, version_id: str, category: str) -> list[dict]:
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
                    "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                })
        return files

    def read_version_artifact(self, model_id: str, version_id: str, category: str, filename: str) -> str:
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

    def preview_dataset(self, model_id: str, version_id: str, filename: str, offset: int = 0, limit: int = 100) -> dict:
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
        page = df.iloc[offset: offset + limit]

        return {
            "columns": list(df.columns),
            "dtypes": {col: str(dt) for col, dt in df.dtypes.items()},
            "rows": page.values.tolist(),
            "total_rows": total_rows,
            "offset": offset,
            "limit": limit,
        }

    def _validate_artifact_filename(self, filename: str) -> None:
        from fastapi import HTTPException

        if not filename or ".." in filename or "/" in filename or "\\" in filename:
            raise HTTPException(400, "Invalid filename")
        if filename.startswith(".") or not filename.strip():
            raise HTTPException(400, "Invalid filename")
        if len(filename) > 255:
            raise HTTPException(400, "Filename too long")

    def upload_version_artifact(self, model_id: str, version_id: str, category: str, file: Any) -> dict:
        from fastapi import HTTPException

        if category not in self._ARTIFACT_CATEGORIES:
            raise HTTPException(400, f"Invalid category: {category}")

        filename = getattr(file, "filename", None)
        if not filename:
            raise HTTPException(400, "No filename provided")
        self._validate_artifact_filename(filename)

        _, _, vdir = self._resolve_version_dir(model_id, version_id)
        cat_dir = vdir / category
        cat_dir.mkdir(exist_ok=True)

        dest = cat_dir / filename
        size = 0
        with open(dest, "wb") as f:
            while chunk := file.file.read(8192):
                size += len(chunk)
                if size > self._MAX_ARTIFACT_SIZE:
                    f.close()
                    dest.unlink(missing_ok=True)
                    raise HTTPException(
                        413, f"File too large (max {self._MAX_ARTIFACT_SIZE // 1024 // 1024} MB)"
                    )
                f.write(chunk)

        stat = dest.stat()
        return {
            "name": filename,
            "size": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        }

    def save_version_artifact_text(self, model_id: str, version_id: str, category: str, filename: str, content: str) -> dict:
        from fastapi import HTTPException

        if category not in self._ARTIFACT_CATEGORIES:
            raise HTTPException(400, f"Invalid category: {category}")
        self._validate_artifact_filename(filename)

        ext = Path(filename).suffix.lower()
        if ext not in self._TEXT_EXTENSIONS:
            raise HTTPException(400, f"Cannot edit binary file type: {ext}")

        _, _, vdir = self._resolve_version_dir(model_id, version_id)
        cat_dir = vdir / category
        cat_dir.mkdir(exist_ok=True)
        dest = cat_dir / filename
        dest.write_text(content, encoding="utf-8")

        stat = dest.stat()
        return {
            "name": filename,
            "size": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        }

    def delete_version_artifact(self, model_id: str, version_id: str, category: str, filename: str) -> None:
        from fastapi import HTTPException

        if category not in self._ARTIFACT_CATEGORIES:
            raise HTTPException(400, f"Invalid category: {category}")
        self._validate_artifact_filename(filename)

        _, _, vdir = self._resolve_version_dir(model_id, version_id)
        path = vdir / category / filename
        if not path.is_file():
            raise HTTPException(404, f"File not found: {category}/{filename}")
        path.unlink()

    # ── Fork ──

    def fork_model(
        self,
        source_model_id: str,
        source_version_id: str,
        new_name: str,
        new_owner_org: str,
        description: str | None = None,
    ) -> dict:
        from fastapi import HTTPException

        src_slug = self._find_slug_by_id(source_model_id)
        if not src_slug:
            raise HTTPException(404, "Source model not found")
        src_model = YAMLFile.read(self._model_yaml_path(src_slug))

        result = self._find_version_in_model(src_slug, source_version_id)
        if not result:
            raise HTTPException(404, "Source version not found")
        src_version_str, src_version_data = result

        new_model = self.create_model({
            "name": new_name,
            "description": description or f"Forked from {src_model['name']} {src_version_str}",
            "task_type": src_model["task_type"],
            "algorithm_type": src_model["algorithm_type"],
            "framework": src_model["framework"],
            "owner_org": new_owner_org,
            "tags": src_model.get("tags"),
        })
        new_slug = new_model["slug"]

        src_vdir = self._version_dir(src_slug, src_version_str)
        dst_vdir = self._version_dir(new_slug, src_version_str)
        shutil.copytree(src_vdir, dst_vdir)

        now = _now_str()
        new_version_data = dict(src_version_data)
        new_version_data["id"] = _new_id()
        new_version_data["parent_version_id"] = source_version_id
        new_version_data["source_model_id"] = source_model_id
        new_version_data["description"] = f"Forked from {src_model['name']} {src_version_str}"
        new_version_data["stage"] = "development"
        new_version_data["created_at"] = now
        new_version_data["updated_at"] = now
        YAMLFile.write(dst_vdir / "version.yaml", new_version_data)

        src_pipeline = self._model_dir(src_slug) / "pipeline.yaml"
        if src_pipeline.exists():
            dst_pipeline = self._model_dir(new_slug) / "pipeline.yaml"
            shutil.copy2(src_pipeline, dst_pipeline)

        self._update_index_entry(YAMLFile.read(self._model_yaml_path(new_slug)))

        new_model["forked_version_id"] = new_version_data["id"]
        return new_model

    # ── Export / Import ──

    def export_model(
        self,
        model_id: str,
        version_ids: list[str] | None = None,
        include_runs: bool = False,
        include_datasets: bool = True,
    ) -> Path:
        import tempfile
        import zipfile

        from fastapi import HTTPException

        slug = self._find_slug_by_id(model_id)
        if not slug:
            raise HTTPException(404, "Model not found")

        model_dir = self._model_dir(slug)
        model_data = YAMLFile.read(self._model_yaml_path(slug))

        versions_dir = model_dir / "versions"
        version_dirs: list[tuple[str, Path]] = []
        if versions_dir.exists():
            for vdir in sorted(versions_dir.iterdir()):
                if not vdir.is_dir():
                    continue
                vyaml = vdir / "version.yaml"
                if not vyaml.exists():
                    continue
                vdata = YAMLFile.read(vyaml)
                if version_ids is None or vdata.get("id") in version_ids:
                    version_dirs.append((vdir.name, vdir))

        if not version_dirs:
            raise HTTPException(400, "No versions to export")

        tmp = tempfile.NamedTemporaryFile(
            suffix=".zip", prefix=f"modelforge-export-{slug}-", delete=False
        )
        tmp.close()
        zip_path = Path(tmp.name)

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(self._model_yaml_path(slug), "model.yaml")

            pipeline = model_dir / "pipeline.yaml"
            if pipeline.exists():
                zf.write(pipeline, "pipeline.yaml")

            for vname, vdir in version_dirs:
                for fpath in vdir.rglob("*"):
                    if not fpath.is_file():
                        continue
                    rel = fpath.relative_to(vdir)
                    if not include_datasets and rel.parts[0] == "datasets":
                        continue
                    zf.write(fpath, f"versions/{vname}/{rel}")

            if include_runs:
                runs_dir = model_dir / "runs"
                if runs_dir.exists():
                    for fpath in runs_dir.rglob("*"):
                        if fpath.is_file():
                            rel = fpath.relative_to(model_dir)
                            zf.write(fpath, str(rel))

            manifest = {
                "format_version": "1.0",
                "exported_at": _now_str(),
                "source_model_id": model_id,
                "source_model_name": model_data["name"],
                "versions_included": [vn for vn, _ in version_dirs],
            }
            zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

        return zip_path

    def preview_import(self, zip_path: Path) -> dict:
        import zipfile

        from fastapi import HTTPException

        if not zipfile.is_zipfile(zip_path):
            raise HTTPException(400, "Invalid ZIP file")

        with zipfile.ZipFile(zip_path, "r") as zf:
            if "manifest.json" not in zf.namelist():
                raise HTTPException(400, "Missing manifest.json in archive")
            manifest = json.loads(zf.read("manifest.json"))

            if "model.yaml" not in zf.namelist():
                raise HTTPException(400, "Missing model.yaml in archive")
            model_data = yaml.safe_load(zf.read("model.yaml"))

            versions = []
            for vname in manifest.get("versions_included", []):
                vyaml_path = f"versions/{vname}/version.yaml"
                if vyaml_path in zf.namelist():
                    vdata = yaml.safe_load(zf.read(vyaml_path))
                    versions.append({
                        "version": vdata.get("version", vname),
                        "id": vdata.get("id"),
                        "stage": vdata.get("stage"),
                        "description": vdata.get("description"),
                    })

            has_pipeline = "pipeline.yaml" in zf.namelist()

            model_name = model_data.get("name", "unknown")
            name_collision = False
            with self._index_lock:
                for entry in self._index:
                    if entry["name"] == model_name:
                        name_collision = True
                        break

            suggested_name = model_name
            if name_collision:
                suggested_name = model_name + " (导入)"

            return {
                "model_name": model_name,
                "source_model_id": manifest.get("source_model_id", ""),
                "algorithm_type": model_data.get("algorithm_type"),
                "framework": model_data.get("framework"),
                "versions": versions,
                "has_pipeline": has_pipeline,
                "name_collision": name_collision,
                "suggested_name": suggested_name,
            }

    def import_model(self, zip_path: Path, new_name: str | None = None) -> dict:
        import zipfile

        from fastapi import HTTPException

        if not zipfile.is_zipfile(zip_path):
            raise HTTPException(400, "Invalid ZIP file")

        with zipfile.ZipFile(zip_path, "r") as zf:
            if "manifest.json" not in zf.namelist():
                raise HTTPException(400, "Missing manifest.json in archive")
            manifest = json.loads(zf.read("manifest.json"))

            if "model.yaml" not in zf.namelist():
                raise HTTPException(400, "Missing model.yaml in archive")
            model_data = yaml.safe_load(zf.read("model.yaml"))

            model_name = new_name or model_data.get("name", "Imported Model")
            new_model = self.create_model({
                "name": model_name,
                "description": model_data.get("description"),
                "task_type": model_data.get("task_type", "other"),
                "algorithm_type": model_data.get("algorithm_type", "unknown"),
                "framework": model_data.get("framework", "unknown"),
                "owner_org": model_data.get("owner_org", "导入"),
                "tags": model_data.get("tags"),
                "applicable_scenarios": model_data.get("applicable_scenarios"),
                "algorithm_description": model_data.get("algorithm_description"),
            })
            new_slug = new_model["slug"]
            new_model_id = new_model["id"]

            model_yaml_path = self._model_yaml_path(new_slug)
            updated_model = YAMLFile.read(model_yaml_path)
            updated_model["imported_from"] = {
                "source_model_id": manifest.get("source_model_id"),
                "source_model_name": manifest.get("source_model_name"),
                "exported_at": manifest.get("exported_at"),
            }
            YAMLFile.write(model_yaml_path, updated_model)

            now = _now_str()
            for vname in manifest.get("versions_included", []):
                vdir = self._model_dir(new_slug) / "versions" / vname
                vdir.mkdir(parents=True, exist_ok=True)

                prefix = f"versions/{vname}/"
                for zinfo in zf.infolist():
                    if zinfo.filename.startswith(prefix) and not zinfo.is_dir():
                        rel = zinfo.filename[len(prefix):]
                        target = vdir / rel
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(zf.read(zinfo.filename))

                vyaml = vdir / "version.yaml"
                if vyaml.exists():
                    vdata = YAMLFile.read(vyaml)
                    vdata["id"] = _new_id()
                    vdata["imported_from_version_id"] = vdata.get("id")
                    vdata["created_at"] = now
                    vdata["updated_at"] = now
                    YAMLFile.write(vyaml, vdata)

            if "pipeline.yaml" in zf.namelist():
                pipeline_target = self._model_dir(new_slug) / "pipeline.yaml"
                pipeline_target.write_bytes(zf.read("pipeline.yaml"))

            runs_prefix = "runs/"
            for zinfo in zf.infolist():
                if zinfo.filename.startswith(runs_prefix) and not zinfo.is_dir():
                    target = self._model_dir(new_slug) / zinfo.filename
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(zf.read(zinfo.filename))

            self._update_index_entry(YAMLFile.read(self._model_yaml_path(new_slug)))

            return {**new_model, "imported_from": updated_model["imported_from"]}

    # ── Deployments ──

    def _read_deployments(self) -> list[dict]:
        data = YAMLFile.read(self.deployments_dir / "deployments.yaml")
        return data.get("deployments", []) if data else []

    def _write_deployments(self, deployments: list[dict]) -> None:
        YAMLFile.write(self.deployments_dir / "deployments.yaml", {"deployments": deployments})

    def create_deployment(self, data: dict) -> dict:
        from fastapi import HTTPException

        version_id = data["model_version_id"]
        info = self.find_version_globally(version_id)
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
        return deployments[skip: skip + limit]

    def get_deployment(self, deployment_id: str) -> dict:
        from fastapi import HTTPException

        for d in self._read_deployments():
            if d["id"] == deployment_id:
                return d
        raise HTTPException(404, "Deployment not found")

    def get_deployment_by_name(self, name: str) -> dict:
        from fastapi import HTTPException

        for d in self._read_deployments():
            if d["name"] == name:
                return d
        raise HTTPException(404, f"Deployment '{name}' not found")

    def update_deployment(self, deployment_id: str, updates: dict) -> dict:
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

    def delete_deployment(self, deployment_id: str) -> None:
        from fastapi import HTTPException

        deployments = self._read_deployments()
        original_len = len(deployments)
        deployments = [d for d in deployments if d["id"] != deployment_id]
        if len(deployments) == original_len:
            raise HTTPException(404, "Deployment not found")
        self._write_deployments(deployments)

        log_path = self.logs_dir / f"{deployment_id}.jsonl"
        if log_path.exists():
            log_path.unlink()

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
            return self.update_deployment(deployment_id, {"status": "running", "error_message": None})
        except Exception as e:
            return self.update_deployment(deployment_id, {"status": "failed", "error_message": str(e)})

    def stop_deployment(self, deployment_id: str, inference_manager: Any) -> dict:
        self.get_deployment(deployment_id)
        inference_manager.undeploy(deployment_id)
        return self.update_deployment(deployment_id, {"status": "stopped"})

    def delete_deployment_with_inference(self, deployment_id: str, inference_manager: Any) -> None:
        self.get_deployment(deployment_id)
        inference_manager.undeploy(deployment_id)
        self.delete_deployment(deployment_id)

    def predict(self, deployment_id: str, input_data: Any, inference_manager: Any) -> tuple:
        import time

        from fastapi import HTTPException

        deployment = self.get_deployment(deployment_id)
        if deployment["status"] != "running":
            raise HTTPException(400, f"Deployment is not running (status: {deployment['status']})")

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

    def log_prediction(self, deployment_id: str, input_data: Any, output_data: Any, latency_ms: float, error: str | None = None) -> dict:
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
        return records[skip: skip + limit]

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
                record_map[pid]["actual_value"] = actual if isinstance(actual, dict) else {"value": actual}
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
        deployment = self.get_deployment(deployment_id)
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

        # Determine task type from model metadata
        task_type = None
        model_id = deployment.get("model_id")
        if model_id:
            try:
                model = self.get_model(model_id)
                task_type = model.get("task_type")
            except Exception:
                pass

        n = len(predicted)
        is_classification = task_type in (
            "classification", "image_classification",
            "object_detection", "digit_recognition",
        )

        if is_classification:
            return self._classification_metrics(
                predicted, actual, n, start_time, end_time,
            )
        return self._regression_metrics(
            predicted, actual, n, start_time, end_time,
        )

    @staticmethod
    def _regression_metrics(predicted, actual, n, start_time, end_time) -> dict:
        mae = sum(abs(a - p) for a, p in zip(actual, predicted)) / n
        rmse = math.sqrt(sum((a - p) ** 2 for a, p in zip(actual, predicted)) / n)

        mape_values = [abs((a - p) / a) for a, p in zip(actual, predicted) if a != 0]
        mape = (sum(mape_values) / len(mape_values) * 100) if mape_values else None

        return {
            "count": n,
            "task_type": "regression",
            "mae": round(mae, 4),
            "rmse": round(rmse, 4),
            "mape": round(mape, 4) if mape is not None else None,
            "period_start": start_time,
            "period_end": end_time,
        }

    @staticmethod
    def _classification_metrics(predicted, actual, n, start_time, end_time) -> dict:
        # Round to int for class labels
        pred_labels = [int(round(p)) for p in predicted]
        true_labels = [int(round(a)) for a in actual]

        correct = sum(1 for p, a in zip(pred_labels, true_labels) if p == a)
        accuracy = correct / n

        # Per-class precision / recall / F1
        all_labels = sorted(set(pred_labels + true_labels))
        per_class = {}
        for label in all_labels:
            tp = sum(1 for p, a in zip(pred_labels, true_labels) if p == label and a == label)
            fp = sum(1 for p, a in zip(pred_labels, true_labels) if p == label and a != label)
            fn = sum(1 for p, a in zip(pred_labels, true_labels) if p != label and a == label)
            precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
            per_class[str(label)] = {
                "precision": round(precision, 4),
                "recall": round(recall, 4),
                "f1": round(f1, 4),
                "support": tp + fn,
            }

        # Macro-average F1
        macro_f1 = sum(c["f1"] for c in per_class.values()) / len(per_class) if per_class else 0.0

        return {
            "count": n,
            "task_type": "classification",
            "accuracy": round(accuracy, 4),
            "macro_f1": round(macro_f1, 4),
            "per_class": per_class,
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

    # ── Feature Catalog ──

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
        return defs[skip: skip + limit]

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

    # ── Feature Groups ──

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

    def list_feature_groups(self, *, q: str | None = None, scenario: str | None = None, skip: int = 0, limit: int = 50) -> list[dict]:
        catalog = self._read_feature_catalog()
        groups = catalog["groups"]
        defs = catalog["definitions"]
        if q:
            q_lower = q.lower()
            groups = [g for g in groups if q_lower in g["name"].lower()]
        groups.sort(key=lambda g: g["name"])
        return [self._resolve_group(g, defs) for g in groups[skip: skip + limit]]

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

    # ── Parameter Templates ──

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
        return templates[skip: skip + limit]

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

    def compare_parameters(self, request: Any) -> dict:
        from fastapi import HTTPException

        def _resolve(ptype, pid):
            if ptype == "template":
                catalog = self._read_param_catalog()
                for t in catalog["templates"]:
                    if t["id"] == pid:
                        return t["name"], t.get("parameters", {})
                raise HTTPException(404, f"Template {pid} not found")
            raise HTTPException(400, f"Unsupported type: {ptype}")

        left_label, left_params = _resolve(request.left_type, request.left_id)
        right_label, right_params = _resolve(request.right_type, request.right_id)

        all_keys = sorted(set(list(left_params.keys()) + list(right_params.keys())))
        diff = []
        left_only = []
        right_only = []
        for k in all_keys:
            in_left = k in left_params
            in_right = k in right_params
            if in_left and in_right:
                diff.append({
                    "key": k,
                    "left_value": left_params[k],
                    "right_value": right_params[k],
                    "changed": left_params[k] != right_params[k],
                })
            elif in_left:
                left_only.append(k)
            else:
                right_only.append(k)

        return {
            "left_label": left_label,
            "right_label": right_label,
            "diff": diff,
            "left_only": left_only,
            "right_only": right_only,
        }
