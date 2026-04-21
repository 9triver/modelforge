# ModelForge Roadmap

ModelForge 的目标不止"自托管 HuggingFace"——长期目标是 **模型可复用闭环**：
托管 → 评估 → 决策（直接用 / 不达标）→ 校准 / 迁移 → 重新发布。

本文档按阶段拆分实施路径，每阶段独立可交付、可验收。

---

## Phase 1 — 模型托管（已完成 ✅）

**目标**：可以推/拉模型，能在浏览器里看 model card 和文件树。

- Git smart HTTP + LFS（4GB 级模型已验证）
- REST API：`/api/v1/repos`、`/api/v1/facets`、`/api/v1/repos/{ns}/{name}/preview`
- 前端 SPA（Vite + React + Tailwind），SPA fallback
- CI/CD：push `v2/server` → self-hosted runner 自动部署到内网机器
- model card frontmatter schema：`pipeline_tag`, `library_name`, `license`, `tags` 等

---

## Phase 2 — 评估即服务（Evaluation-as-a-Service）

**目标**：用户带自己的数据来，平台跑模型，返回标准指标，让用户判断"能不能直接用"。

### 设计原则

- **对齐 HuggingFace**：`pipeline_tag` 驱动，每个 task 有标准 I/O、标准数据格式、标准指标
- **沙箱执行**：用户 handler 是任意 Python，必须 Docker 隔离 + `--network none` + 资源限额
- **不留痕**：用户上传的数据和预测结果只在 tmpfs，job 结束销毁；只聚合**匿名**指标到 model card
- **第一阶段不加认证**：靠沙箱兜底，节奏优先

### Pilot tasks（Phase 2 只做这两个）

| task | 数据格式 | 默认 metrics | runtime image |
|---|---|---|---|
| `time-series-forecasting` | CSV/Parquet（timestamp + features + target） | MAPE, RMSE, MAE, sMAPE | `modelforge-runtime:timeseries` |
| `image-classification` | ZIP（ImageFolder：`class_name/xxx.jpg`） | accuracy, precision, recall, F1 (macro) | `modelforge-runtime:vision` (GPU) |

### 关键抽象

**模型契约**（仓库里只放 handler，不写评估逻辑）：

```python
# modelforge_runtime/tasks/base.py
class TaskHandler:
    task: ClassVar[str]
    def __init__(self, model_dir: str): ...
    def predict(self, inputs): ...

# modelforge_runtime/tasks/forecasting.py
class ForecastingHandler(TaskHandler):
    task = "time-series-forecasting"
    def predict(self, df: pd.DataFrame) -> pd.DataFrame: ...

# modelforge_runtime/tasks/image_classification.py
class ImageClassificationHandler(TaskHandler):
    task = "image-classification"
    def predict(self, images: list[PIL.Image]) -> list[list[dict]]: ...
```

**仓库布局**（发布者视角）：

```
my-model/
  model_card.yaml      # pipeline_tag + 任务声明
  handler.py           # class Handler(ForecastingHandler): ...
  requirements.txt     # 增量依赖
  weights/...          # LFS
```

**model_card.yaml 增强**：

```yaml
pipeline_tag: time-series-forecasting
runtime: timeseries
runtime_version: "0.1.0"
primary_metric: mape
forecasting:
  input_freq: 15min
  horizon: 96
  lookback: 672
  features:
    required: [timestamp, load]
    optional: [temperature, humidity]
  target: load
```

### API 设计

```
POST /api/v1/repos/{ns}/{name}/evaluate
  multipart: dataset
  query:    revision=main
  →         { evaluation_id }

GET /api/v1/evaluations/{id}
  → { status: queued|running|done|failed,
      metrics: { mape: 0.087, rmse: ... },
      primary: 0.087,
      duration_ms: 12345,
      error: null }

GET /api/v1/repos/{ns}/{name}/metrics
  → 聚合匿名指标：{ count: 17, primary_metric: "mape",
                  median: 0.09, p25: 0.07, p75: 0.12 }
```

### Runtime 容器

- 维护一组基础镜像：`modelforge-runtime:base`、`:timeseries`、`:vision`
- 每个 evaluation job 起独立容器：
  - 挂载 `/model`（只读，仓库 checkout）+ `/data`（只读 tmpfs，用户数据）+ `/out`（写指标 JSON）
  - `--network none --memory 8g --cpus 4 --gpus all`（vision）
  - 超时 5 min（可在 model card 声明覆盖）
  - 跑完销毁，删除所有临时文件
- runner 实现：单机版用 in-process asyncio queue + worker pool；后续按需上 Redis/RQ

### Phase 2 交付物

- [ ] `modelforge_runtime/` 子包：TaskHandler 基类 + 两个 pilot task 实现
- [ ] `modelforge_runtime/datasets/`：标准数据 loader（CSV/Parquet、ImageFolder）
- [ ] `modelforge_runtime/metrics/`：标准指标实现
- [ ] Docker 镜像 `modelforge-runtime:base|timeseries|vision`，CI 构建推到内网 registry
- [ ] 后端 `api/evaluate.py`：上传 → 入队 → 容器执行 → 返回结果
- [ ] EvaluationStore（SQLite）：只存匿名 `(model_id, revision, metrics, duration, ts)`
- [ ] 前端：model card 加 "Evaluate" tab（拖文件 → 看进度 → 看指标）
- [ ] 前端：model card 加 "Performance" 区块（聚合指标）
- [ ] 端到端 demo：TimesFM forecasting + 一个 ResNet-style image-classifier

### Phase 2 验收

- 上传内网某条线路的 96 步负荷 CSV，10 s 内拿到 MAPE
- 上传一个图像 ZIP，1 min 内拿到 accuracy
- 评估期间宿主机网络 / 文件系统不可被 handler 访问
- model card 上能看到该模型的历史 MAPE 中位数
- 评估完，宿主机 `/tmp` 干净，没有用户数据残留

---

## Phase 3 — 直接复用（SDK + 一键接入）

**目标**：评估达标 → 一行代码把模型嵌进自己的项目。

- Python SDK：`modelforge.load("ns/name", revision="v1.2")` → 返回可调用的 handler 实例
- 自动按 `pipeline_tag` 加载对应 TaskHandler 子类
- 缓存层（类似 `~/.cache/huggingface`），LFS 文件按需下载、校验 sha256
- CLI：`modelforge run ns/name --input data.csv --output pred.csv`
- 前端 model card 上一键复制 SDK 调用 snippet

### Phase 3 交付物

- [ ] `modelforge` Python SDK（已有壳，补 `load()` / `Handler` 抽象）
- [ ] 本地缓存 + LFS 增量下载
- [ ] CLI 子命令 `modelforge run`
- [ ] model card "Use this model" 区块，按 task 给代码片段

---

## Phase 4 — 校准 / 迁移（占位，待 L2/L3 收集到 use case 后细化）

**目标**：评估不达标时，让用户在平台上做校准 / fine-tune / 迁移，产出新版本回写仓库。

候选机制（先列方向，不展开）：
- 残差校准（residual model 叠加）
- Bias correction
- Fine-tune（小样本，task 内置 trainer）
- Domain adaptation
- 评估 → 校准 → 再评估 的闭环 UI

待定问题：
- trainer 是不是也要 task 化（按 task 提供默认 trainer）
- 校准产出的新版本怎么命名（`v1.2-calibrated-{user_data_hash}`？还是 fork 出新仓库？）
- 计算资源调度（fine-tune 比 inference 重得多）

> 此阶段在 Phase 2/3 跑通、收集到真实 use case 后再细化。

---

## 跨阶段事项

### 安全
- Phase 2 必须做对：Docker `--network none`、只读挂载、资源限额、超时杀进程、tmpfs 销毁
- 不要图省事用 subprocess + resource limit 凑合

### Task 扩展节奏
- Phase 2 锁定 forecasting + image-classification 两个
- 后续按 use case 加：`tabular-classification`、`tabular-regression`、`object-detection`、`text-classification`、`token-classification`、`image-segmentation`
- 每加一个 task = 数据 loader + metrics + handler 基类 + runtime 镜像（如有新依赖）+ 前端展示

### 不做的事
- 不做 Inference API（按需 ad-hoc 推理，不做常驻推理服务）
- 不做 Spaces / Datasets / Discussions
- 不做完整权限体系（内网半信任环境，靠沙箱兜底）
