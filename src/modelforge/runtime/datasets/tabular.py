"""tabular-classification / tabular-regression 共用数据 loader。

支持 CSV / Parquet。约定格式：
  - 含 target 列
  - 含特征列（required + optional）

返回 (features_df, labels)。
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pandas as pd


class DatasetError(ValueError):
    pass


def load_tabular_csv(
    path: str | Path,
    *,
    target_col: str,
    required_features: list[str] | None = None,
) -> tuple["pd.DataFrame", list[Any]]:
    """读 CSV/Parquet，分离特征和标签。

    Returns:
        (features_df, labels) — features_df 不含 target 列
    """
    raise NotImplementedError("TODO: tabular dataset loader")
