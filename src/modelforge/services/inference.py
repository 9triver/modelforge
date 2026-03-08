"""Inference service (backward-compatible facade).

Re-exports from the new adapters.runners module so existing imports
like ``from modelforge.services.inference import inference_manager``
continue to work.
"""

from modelforge.adapters.runners import (
    InferenceManager,
    OnnxRunner,
    SklearnRunner,
    inference_manager,
)

# Keep the original Protocol import path working
from modelforge.core.protocols import ModelRunner

__all__ = [
    "ModelRunner",
    "SklearnRunner",
    "OnnxRunner",
    "InferenceManager",
    "inference_manager",
]
