"""time-series-forecasting 标准评估数据 loader。

支持 CSV / Parquet。约定格式：
  - 必含 'timestamp' 列（可被 pd.to_datetime 解析）
  - 必含 model_card 声明的 target 列
  - 可含 features（required + optional）

返回排序好的 DataFrame。

依赖 pandas（来自 runtime-timeseries extras）。
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd


class DatasetError(ValueError):
    """数据格式错误，message 面向终端用户。"""


def load_forecasting_csv(
    path: str | Path,
    *,
    target_col: str,
    required_features: list[str] | None = None,
    timestamp_col: str = "timestamp",
) -> "pd.DataFrame":
    """读 CSV/Parquet，校验必需列，按 timestamp 排序返回。"""
    import pandas as pd

    p = Path(path)
    if not p.is_file():
        raise DatasetError(f"数据文件不存在：{p}")

    suffix = p.suffix.lower()
    if suffix in {".csv", ".tsv"}:
        sep = "\t" if suffix == ".tsv" else ","
        df = pd.read_csv(p, sep=sep)
    elif suffix in {".parquet", ".pq"}:
        df = pd.read_parquet(p)
    else:
        raise DatasetError(f"不支持的文件格式：{suffix}（支持 .csv/.tsv/.parquet）")

    if timestamp_col not in df.columns:
        raise DatasetError(f"缺少时间列 '{timestamp_col}'，实际列：{list(df.columns)}")
    if target_col not in df.columns:
        raise DatasetError(f"缺少目标列 '{target_col}'，实际列：{list(df.columns)}")

    missing = [c for c in (required_features or []) if c not in df.columns]
    if missing:
        raise DatasetError(f"缺少必需特征列：{missing}")

    try:
        df[timestamp_col] = pd.to_datetime(df[timestamp_col])
    except (ValueError, TypeError) as e:
        raise DatasetError(f"'{timestamp_col}' 列无法解析为时间：{e}")

    df = df.sort_values(timestamp_col).reset_index(drop=True)
    return df
