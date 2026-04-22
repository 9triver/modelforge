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

- [x] `modelforge.runtime/` 子包：TaskHandler 基类 + 两个 pilot task（forecasting / image-classification）
- [x] `runtime/datasets/`：CSV/Parquet loader、ImageFolder loader、ZIP 解压防 zip-slip
- [x] `runtime/metrics/`：forecasting（MAPE/RMSE/MAE/sMAPE）+ classification（accuracy/macro P/R/F1）
- [x] `runtime/evaluator.py`：in-process backend，handler 动态 import + 基类校验 + 异常兜底
- [x] 后端 `api/evaluations.py`：POST upload → BackgroundTasks 跑 → 返回 evaluation_id
- [x] EvaluationStore（SQLite `evaluations` 表）：只存 `(repo_id, revision, metrics, duration, ts)`，不关联用户/不留输入数据
- [x] 前端：RepoPage 加 Evaluate tab（拖文件 → 状态轮询 → 指标表，primary metric 高亮）
- [x] 前端：Card tab 顶部 PerformanceBadge（匿名聚合 count/median/p25/p75，count==0 时隐藏）
- [x] LFS 指针实化：`repo_reader.materialize_lfs()` 把 checkout 出来的指针替换成 lfs_store 里的真文件
- [x] 端到端 demo 跑通：`examples/chronos-forecasting-demo/` 镜像 HF amazon/chronos-t5-tiny +
      合成数据生成脚本；浏览器里能点出 MAPE，Performance badge 能聚合
- [ ] Docker 镜像 `modelforge-runtime:base|timeseries|vision`，CI 构建推到内网 registry
- [x] Evaluator Docker sandbox backend：`--network none` + 只读挂载 + 资源限额 + 超时
      **代码完成**（`backend.py` + `docker_backend.py` + `sandbox_entry.py` + Dockerfile），
      timeseries 镜像已验证可用；vision 镜像因国内网络环境构建困难，暂缓。
      默认 `eval_backend=inprocess`，切 `docker` 需构建镜像。
- [x] image-classification 端到端 demo（forecasting 已验证，vision 还欠 demo）

### Phase 2 验收

- [x] 上传 hourly 合成负荷 CSV（336 行），几秒内拿到 MAPE（Chronos T5 tiny on GPU）
- [x] model card 上能看到该模型的历史 primary metric 中位数（PerformanceBadge）
- [x] 评估完，宿主机 workdir 干净（tempdir + `shutil.rmtree(workdir, ignore_errors=True)`）
- [x] 上传图像 ZIP，拿到 accuracy（ViT cats-vs-dogs demo 已验证）
- [ ] 评估期间宿主机网络 / 文件系统不可被 handler 访问（当前 in-process，**未隔离**；
      Docker backend 代码已就绪，timeseries 镜像可用，待 vision 镜像和切换决策）

### Task 扩展（已完成）

| task | handler | metrics | demo |
|---|---|---|---|
| `time-series-forecasting` | ForecastingHandler | MAPE/RMSE/MAE/sMAPE | amazon/chronos-t5-tiny ✅ |
| `image-classification` | ImageClassificationHandler | accuracy/P/R/F1 macro | nateraw/vit-base-cats-vs-dogs ✅ |
| `object-detection` | ObjectDetectionHandler | mAP/mAP_50/mAP_75/mAR (pycocotools) | ultralytics/yolov8n ✅ |

---

## Phase 3 — 直接复用（SDK + 一键接入）

**目标**：评估达标 → 一行代码把模型嵌进自己的项目。

- Python SDK：`modelforge.load("ns/name", revision="v1.2")` → 返回可调用的 handler 实例
- 自动按 `pipeline_tag` 加载对应 TaskHandler 子类
- 缓存层（类似 `~/.cache/huggingface`），LFS 文件按需下载、校验 sha256
- CLI：`modelforge run ns/name --input data.csv --output pred.csv`
- 前端 model card 上一键复制 SDK 调用 snippet

### Phase 3 交付物

- [x] `modelforge.load()` 顶层 API：下载 + 缓存 + 返回可调用 handler
- [x] CLI `modelforge run`：按 task 分发 I/O（forecasting CSV / classification ImageFolder / detection JSON）
- [x] 前端 "Use this model" 代码片段（Python + CLI，按 task 渲染）
- [x] Files tab 单文件下载（普通文件 git show / LFS 文件流式返回）
- [x] 模型页面删除按钮（确认后删除，内网简化无需 token）

---

## Phase 4 — 校准 / 迁移

**目标**：评估不达标时，让用户在平台上做校准 / 迁移，产出新版本 fork 到新仓库。

### 4a. 时序预测校准（已完成 ✅）

三种方法，用户上传目标区域数据 → 同时预览三种方法的 before/after 对比 → 选最好的 fork：

| 方法 | 原理 | 参数 |
|---|---|---|
| `linear_bias` | 全局 `y = a*pred + b` | `{a, b}` |
| `segmented` | 按小时分 4 段（0-5/6-11/12-17/18-23），每段独立 (a, b) | `{segments: {0: {a,b}, ...}}` |
| `stacking` | GradientBoostingRegressor 拟合残差（特征：pred + hour + dayofweek + month） | `{model_b64: base64(pickle)}` |

交互流程：
1. Evaluate tab → 看到 MAPE 不达标 → "指标不理想？试试校准 →"
2. Calibrate tab → 上传 CSV → "Preview all methods"
3. 三行对比表（Before/After MAPE/RMSE/MAE）→ radio 选最佳
4. 填 fork namespace/name → "Save as new model" → fork 仓库
5. fork 仓库自包含（base_model/ + wrapper handler + calibration.json）

交付物：
- [x] `runtime/calibration.py`：三种方法 + `calibrate_by_method()` 分发 + 每种方法独立 handler template
- [x] `api/calibrations.py`：两阶段 API（preview 不建仓库 / save 才 fork）
- [x] `db.py`：calibrations 表 + CRUD
- [x] 前端 CalibrateTab：多方法对比表 + 两阶段 UX
- [x] 评估 → 校准衔接（EvaluationStatus 底部引导链接）
- [x] `pyproject.toml`：`runtime-calibration` optional deps（scikit-learn）

### 4b. CV 迁移（未来）

| task | 推荐方法 | 原理 | 数据量 | 计算量 | 优先级 |
|---|---|---|---|---|---|
| image-classification | **Linear Probe** | 冻结 backbone，提取特征向量，训练新线性分类头（sklearn） | 每类 5-10 张 | CPU 秒级 | 高 |
| image-classification | Fine-tune 最后几层 | 冻结 backbone 前 N 层，训练后几层 + 分类头 | 每类 50+ 张 | GPU 分钟级 | 中 |
| image-classification | Adapter / Prompt tuning | 插入小参数模块，冻结主体 | 每类 10-50 张 | GPU 轻量 | 低（依赖模型架构） |
| object-detection | Fine-tune 检测头 | 冻结 backbone，训练检测头（anchor/NMS/bbox reg） | 100+ 标注图 | GPU 十分钟级 | 低（标注成本高） |

**为什么 CV 迁移比时序难**：
- 时序输出是一维连续值，`y = a*pred + b` 就能修正系统性偏移
- CV 输出是离散类别或坐标+类别，必须回到特征空间做调整
- 最小 MVP（linear probe）也需要碰模型内部（提取中间层特征）

**Linear Probe 实现思路**（如果要做）：
```
用户上传少量标注图（ImageFolder 格式）
  → 平台冻结模型 backbone，提取特征向量
  → sklearn LogisticRegression 训练新分类头（秒级，CPU）
  → 替换原模型分类头
  → 返回 before/after accuracy 对比
  → 满意 → fork（base_model/ + 新分类头权重 + wrapper handler）
```

> 此部分在时序校准收集到真实 use case 反馈后再启动。

---

## 跨阶段事项

### 安全
- Phase 2 必须做对：Docker `--network none`、只读挂载、资源限额、超时杀进程、tmpfs 销毁
- 不要图省事用 subprocess + resource limit 凑合

### Task 扩展节奏
- Phase 2 锁定 forecasting + image-classification 两个 → 已扩展到 object-detection
- 后续按 use case 加：`tabular-classification`、`tabular-regression`、`text-classification`、`token-classification`、`image-segmentation`
- 每加一个 task = 数据 loader + metrics + handler 基类 + runtime 镜像（如有新依赖）+ 前端展示

### 不做的事
- 不做 Inference API（按需 ad-hoc 推理，不做常驻推理服务）
- 不做 Spaces / Datasets / Discussions
- 不做完整权限体系（内网半信任环境，靠沙箱兜底）
