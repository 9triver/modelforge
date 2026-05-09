"""token-classification（NER / 序列标注）数据 loader。

支持 JSONL / CoNLL。约定格式：
  JSONL: 每行 {"tokens": ["word1", "word2", ...], "labels": ["O", "B-PER", ...]}
  CoNLL: 空行分句，每行 "word\tlabel"

返回 (texts, token_labels)。
  texts: list[str] — 原始句子（tokens join）
  token_labels: list[list[dict]] — 每句的 ground truth span
    [{"word": "...", "entity": "...", "start": int, "end": int}]
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


class DatasetError(ValueError):
    pass


def load_token_dataset(
    path: str | Path,
) -> tuple[list[str], list[list[dict]]]:
    """读 JSONL/CoNLL，返回 (texts, ground_truth_spans)。"""
    raise NotImplementedError("TODO: token classification dataset loader")
