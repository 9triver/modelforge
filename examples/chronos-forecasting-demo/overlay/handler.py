"""Chronos T5 handler for ModelForge time-series-forecasting evaluator.

Evaluation contract:
  predict(df) -> DataFrame with ['timestamp', 'prediction'] columns covering
                 the last `horizon` rows of df (hold-out tail).

I/O strategy:
  - df 整张表传进来（含 target 'load'）。
  - 取最后 24 步作为 hold-out（forecast horizon），用前面的历史喂模型。
  - Chronos 是 zero-shot foundation model，不需要 fit；直接 predict。
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import torch

from modelforge.runtime.tasks import ForecastingHandler

HORIZON = 24


class Handler(ForecastingHandler):
    def __init__(self, model_dir: str):
        super().__init__(model_dir)
        from chronos import ChronosPipeline

        device = "cuda" if torch.cuda.is_available() else "cpu"
        dtype = torch.bfloat16 if device == "cuda" else torch.float32
        self.pipeline = ChronosPipeline.from_pretrained(
            Path(model_dir),
            device_map=device,
            torch_dtype=dtype,
        )

    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        if len(df) <= HORIZON:
            raise ValueError(
                f"数据不足以做 {HORIZON} 步 hold-out（共 {len(df)} 行）"
            )

        history = df["load"].iloc[:-HORIZON].astype(float).tolist()
        context = torch.tensor(history)

        # forecast: tensor of shape (num_series=1, num_samples, horizon)
        forecast = self.pipeline.predict(
            context=context,
            prediction_length=HORIZON,
            num_samples=20,
        )
        median = forecast[0].median(dim=0).values.cpu().numpy()

        tail = df.iloc[-HORIZON:][["timestamp"]].copy()
        tail["prediction"] = median
        return tail.reset_index(drop=True)
