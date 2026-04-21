# Chronos Forecasting Demo

端到端 demo：镜像 HF 上的 Chronos T5 Tiny 到 ModelForge，配好 handler 和测试数据，演示 **Evaluate** 功能。

## 0. 先决条件（部署机）

```bash
ssh chun@192.168.30.134
cd /home/chun/modelforge
.venv/bin/pip install chronos-forecasting torch --index-url https://download.pytorch.org/whl/cpu
# 部署机没 GPU 就用 CPU wheel，大约 200MB；有 GPU 用默认 index
sudo systemctl --user restart modelforge.service
```

> 如果之前没装过 runtime-timeseries，顺手装一下：
> `.venv/bin/pip install -e ".[runtime-timeseries]"`

## 1. Mac 本地：镜像模型

```bash
# 先到 ModelForge 建个 token（或复用现有 token）
export MODELFORGE_TOKEN=<your-token>
export MODELFORGE_URL=http://192.168.30.134:6000   # 或省略，脚本默认值

pip install huggingface_hub    # 仅 mirror 脚本需要
python examples/chronos-forecasting-demo/mirror.py
```

脚本做的事：
1. `snapshot_download amazon/chronos-t5-tiny` 到 `/tmp/mf-chronos-mirror-cache`
2. 叠加 `overlay/` 里的 `README.md`、`handler.py`、`.gitattributes`
3. `ModelHub.upload_folder` → 在 ModelForge 上建 repo `amazon/chronos-t5-tiny` + git push（LFS 权重直传）

## 2. 生成测试数据

```bash
python examples/chronos-forecasting-demo/make_dataset.py
# wrote 336 rows -> .../synthetic_load.csv
```

拿到 `synthetic_load.csv`（14 天 hourly，两列 `timestamp,load`）。

## 3. 浏览器里跑评估

1. 打开 http://192.168.30.134:6000/amazon/chronos-t5-tiny
2. 点 **Evaluate** tab
3. 拖入 `synthetic_load.csv`
4. **Run evaluation**
5. 几十秒后看到指标表：MAPE/RMSE/MAE/sMAPE，primary = MAPE 高亮
6. 点 "View updated performance →" 回 Card tab，顶部出现聚合条

## handler 逻辑

`overlay/handler.py` 是最小实现：

- 加载 Chronos pipeline（CPU/CUDA 自动）
- `predict(df)`：取最后 24 行当 hold-out，前面历史做 context，`num_samples=20` 取 median
- 返回 `DataFrame(timestamp, prediction)`，evaluator 按 timestamp 跟 df 做 inner join 算指标

## 排错

| 症状 | 原因 |
|---|---|
| evaluation status=error, error 里有 `ModuleNotFoundError: chronos` | 部署机 venv 没装 chronos-forecasting |
| evaluation status=error, error 里有 `import pandas` | 部署机没装 runtime-timeseries extras |
| POST /evaluate 返回 400 "README.md ..." | model_card frontmatter 格式错误（常见于 overlay 被改坏） |
| MAPE 偏高（0.2+） | Chronos zero-shot，对这个合成曲线够用但不完美；多点数据会改善 |
