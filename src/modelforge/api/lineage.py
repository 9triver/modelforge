"""Lineage / provenance API routes.

Assembles provenance information from existing metadata rather than
maintaining a separate lineage store.  A version's full lineage is
derived from:

- ``version.yaml``: parent_version_id, source_model_id
- ``run.yaml``: base_version → target_version, pipeline_snapshot, overrides
- Version directory: datasets/, code/, features/, params/ artifacts
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from modelforge.store import ModelStore, get_store

router = APIRouter(prefix="/lineage", tags=["lineage"])


def _version_provenance(store: ModelStore, model_id: str, version_id: str) -> dict:
    """Build provenance record for a single version."""
    version = store.get_version(model_id, version_id)

    prov: dict = {
        "version_id": version["id"],
        "version": version.get("version"),
        "model_id": model_id,
        "stage": version.get("stage"),
        "parent_version_id": version.get("parent_version_id"),
        "source_model_id": version.get("source_model_id"),
        "created_at": version.get("created_at"),
        "metrics": version.get("metrics"),
        "artifacts": {},
        "training_run": None,
    }

    # Collect artifact listings per category
    for category in ("datasets", "code", "features", "params"):
        try:
            files = store.list_version_artifacts(
                model_id, version_id, category,
            )
            prov["artifacts"][category] = [
                f["name"] for f in files
            ]
        except Exception:
            prov["artifacts"][category] = []

    # Find the training run that produced this version
    try:
        runs = store.list_runs(model_id)
        v_str = version.get("version", "")
        for run in runs:
            rv = run.get("result_version_id")
            rt = run.get("result_version", "")
            if rv == version_id or rt == v_str:
                prov["training_run"] = {
                    "run_id": run["id"],
                    "status": run.get("status"),
                    "base_version": run.get("base_version"),
                    "overrides": run.get("overrides"),
                    "started_at": run.get("started_at"),
                    "finished_at": run.get("finished_at"),
                }
                break
    except Exception:
        pass

    return prov


@router.get("/versions/{model_id}/{version_id}")
def get_version_provenance(
    model_id: str,
    version_id: str,
    store: ModelStore = Depends(get_store),
):
    """Get full provenance for a single version."""
    return _version_provenance(store, model_id, version_id)


@router.get("/upstream/{model_id}/{version_id}")
def get_upstream(
    model_id: str,
    version_id: str,
    depth: int = Query(default=10, le=50),
    store: ModelStore = Depends(get_store),
):
    """Walk the parent chain upward to build the full lineage.

    Returns a list of provenance records from the target version
    back to the root, following parent_version_id links.
    """
    chain: list[dict] = []
    current_model_id = model_id
    current_version_id = version_id
    visited: set[str] = set()

    for _ in range(depth):
        if current_version_id in visited:
            break
        visited.add(current_version_id)

        try:
            prov = _version_provenance(
                store, current_model_id, current_version_id,
            )
        except Exception:
            break

        chain.append(prov)

        # Follow parent link
        parent_vid = prov.get("parent_version_id")
        if not parent_vid:
            break

        # Parent may be in a different model (fork/import)
        source_mid = prov.get("source_model_id")
        if source_mid and source_mid != current_model_id:
            current_model_id = source_mid

        current_version_id = parent_vid

    return {"version_id": version_id, "chain": chain}


@router.get("/diff/{model_id}")
def diff_versions(
    model_id: str,
    version_a: str = Query(...),
    version_b: str = Query(...),
    store: ModelStore = Depends(get_store),
):
    """Compare provenance of two versions within the same model.

    Shows artifact differences, metric changes, and parameter overrides.
    """
    prov_a = _version_provenance(store, model_id, version_a)
    prov_b = _version_provenance(store, model_id, version_b)

    # Artifact diff
    artifact_diff = {}
    all_cats = set(
        list(prov_a["artifacts"].keys())
        + list(prov_b["artifacts"].keys())
    )
    for cat in all_cats:
        files_a = set(prov_a["artifacts"].get(cat, []))
        files_b = set(prov_b["artifacts"].get(cat, []))
        artifact_diff[cat] = {
            "added": sorted(files_b - files_a),
            "removed": sorted(files_a - files_b),
            "unchanged": sorted(files_a & files_b),
        }

    # Metric diff
    metrics_a = prov_a.get("metrics") or {}
    metrics_b = prov_b.get("metrics") or {}
    all_metric_keys = sorted(
        set(list(metrics_a.keys()) + list(metrics_b.keys()))
    )
    metric_diff = []
    for k in all_metric_keys:
        va = metrics_a.get(k)
        vb = metrics_b.get(k)
        metric_diff.append({
            "metric": k,
            "version_a": va,
            "version_b": vb,
            "delta": (
                round(vb - va, 6)
                if isinstance(va, (int, float))
                and isinstance(vb, (int, float))
                else None
            ),
        })

    # Training run diff (overrides)
    run_a = prov_a.get("training_run") or {}
    run_b = prov_b.get("training_run") or {}

    return {
        "version_a": {
            "version_id": prov_a["version_id"],
            "version": prov_a["version"],
        },
        "version_b": {
            "version_id": prov_b["version_id"],
            "version": prov_b["version"],
        },
        "artifact_diff": artifact_diff,
        "metric_diff": metric_diff,
        "overrides_a": run_a.get("overrides"),
        "overrides_b": run_b.get("overrides"),
    }
