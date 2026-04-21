---
license: apache-2.0
library_name: chronos-forecasting
pipeline_tag: time-series-forecasting
base_model: amazon/chronos-t5-tiny
tags:
  - time-series-forecasting
  - chronos
  - foundation-model
forecasting:
  input_freq: 1h
  horizon: 24
  lookback: 168
  target: load
  features:
    required: [timestamp, load]
---

# Chronos T5 Tiny — ModelForge mirror

Mirror of [amazon/chronos-t5-tiny](https://huggingface.co/amazon/chronos-t5-tiny) packaged with a ModelForge `Handler` so the platform can run end-to-end evaluations.

- **Task**: `time-series-forecasting`
- **Default horizon**: 24 步（1 小时粒度数据上即未来一天）
- **Lookback**: 168 步（1 周历史）

## 评估数据格式

CSV / Parquet，必含两列：

| 列 | 含义 |
|---|---|
| `timestamp` | 任意可解析的时间戳，按时间升序 |
| `load` | 浮点目标值 |

平台会按时间顺序，把最后 `horizon` 步当做"未来"做 hold-out：handler 用前面所有数据预测最后 24 个时间点，然后跟真实值比对算 MAPE/RMSE/MAE/sMAPE。

## 依赖

部署机 venv 需要：

```
chronos-forecasting>=1.4
torch>=2.0
```

## 来源

- 原始权重：https://huggingface.co/amazon/chronos-t5-tiny
- 论文：[Chronos: Learning the Language of Time Series](https://arxiv.org/abs/2403.07815)
