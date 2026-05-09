"""text-classification 数据 loader。

支持 CSV / JSONL。约定格式：
  CSV:   text_col + label_col
  JSONL: 每行 {"text": "...", "label": "..."}

返回 (texts, labels)。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


class DatasetError(ValueError):
    pass


def load_text_dataset(
    path: str | Path,
    *,
    text_col: str = "text",
    label_col: str = "label",
) -> tuple[list[str], list[Any]]:
    """读 CSV/JSONL，返回 (texts, labels)。"""
    raise NotImplementedError("TODO: text classification dataset loader")
