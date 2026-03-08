"""Pipeline execution engine (backward-compatible facade).

Delegates to ``LocalSubprocessBackend`` from the adapters layer while
preserving the exact same public API that existing API routes rely on.
"""

from __future__ import annotations

import threading

from modelforge.adapters.filesystem.training_backend import (
    LocalSubprocessBackend,
)


class PipelineRunner:
    """Backward-compatible wrapper around LocalSubprocessBackend."""

    def __init__(self, store):
        self._store = store
        self._backend = LocalSubprocessBackend(store)

    def start_run(
        self,
        model_id: str,
        base_version: str,
        overrides: dict | None = None,
        draft_version: str | None = None,
    ) -> dict:
        """Trigger a pipeline run. Returns the run record."""
        job = {
            "model_id": model_id,
            "base_version": base_version,
            "overrides": overrides,
            "draft_version": draft_version,
            "pipeline": None,  # backend will fetch from store
        }
        run_id = self._backend.submit(job)

        # Return the run record (same shape the old code returned)
        return self._store.get_run(model_id, run_id)


# Singleton
_runner: PipelineRunner | None = None
_runner_lock = threading.Lock()


def get_runner(store=None) -> PipelineRunner:
    global _runner
    with _runner_lock:
        if _runner is None:
            if store is None:
                from modelforge.store import get_store
                store = get_store()
            _runner = PipelineRunner(store)
        return _runner
