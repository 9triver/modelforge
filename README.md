# ModelForge

电力行业人工智能模型全网共享中心 — 面向模型全生命周期的轻量级 MLOps 平台。

## 核心理念

ModelForge 围绕一个核心问题构建：**如何让电力行业的 AI 模型从开发到生产形成闭环，并在跨区域间安全共享？**

设计原则：

- **模型即资产** — 每个模型是一项可追溯、可复用、可共享的数字资产，而非散落的文件
- **版本即快照** — 每个版本完整记录训练输入（数据、特征、参数、代码）和输出（权重、指标），确保可复现
- **零数据库依赖** — 全部元数据存储在 YAML 文件中，模型目录即状态，可直接 rsync / git 管理
- **渐进式工作流** — 从手动上传到流水线训练，从单机部署到跨区共享，按需启用功能层

## 架构概览

```text
┌──────────────────────────────────────────────────────────┐
│                    Web UI (SPA)                           │
│              Vanilla JS + Tailwind CSS                    │
└────────────────────────┬─────────────────────────────────┘
                         │ HTTP
┌────────────────────────▼─────────────────────────────────┐
│                   FastAPI Server                          │
│  ┌──────────┐ ┌──────────┐ ┌───────────┐ ┌───────────┐  │
│  │ Registry │ │ Pipeline │ │ Deploy &  │ │ Evaluation│  │
│  │   API    │ │  Runner  │ │ Inference │ │ & Diagnos │  │
│  └────┬─────┘ └────┬─────┘ └─────┬─────┘ └─────┬─────┘  │
│       └─────────────┼─────────────┼─────────────┘        │
│                     ▼             ▼                       │
│  ┌─────────────── Core Layer ──────────────────────┐     │
│  │  Protocols     Types       DI Container          │     │
│  │ (MetadataStore, ArtifactStore, TrainingBackend)   │     │
│  └──────────────────┬──────────────────────────────┘     │
│                     ▼                                     │
│  ┌─────────────── Adapters ────────────────────────┐     │
│  │  YAMLMetadataStore   LocalArtifactStore          │     │
│  │  InferenceManager    LocalSubprocessBackend      │     │
│  └──────────────────┬──────────────────────────────┘     │
└─────────────────────┼────────────────────────────────────┘
                      ▼
              model_store/  (文件系统)
```

**技术栈：** Python 3.11+ · FastAPI · Pydantic v2 · YAML 存储 · 无数据库

### 分层设计

| 层 | 路径 | 职责 |
| --- | --- | --- |
| **Core** | `src/modelforge/core/` | Protocol 接口定义、领域类型（Pydantic）、DI 容器 |
| **Adapters** | `src/modelforge/adapters/` | 具体实现（文件系统存储、模型推理引擎、子进程训练） |
| **API** | `src/modelforge/api/` | FastAPI 路由，依赖 Core Protocol，不依赖具体 Adapter |
| **Services** | `src/modelforge/services/` | 业务逻辑（试评估、诊断分析） |
| **Web** | `src/modelforge/web/` | SPA 前端（vanilla JS + Tailwind CSS） |

## 核心领域实体

所有领域实体定义在 `src/modelforge/core/types.py`，以 Pydantic v2 BaseModel 为基类，作为全平台的规范数据结构。

### 实体关系

```text
FeatureDefinition ──┐
                    ├──→ FeatureGroup (按场景组合特征)
FeatureDefinition ──┘
                                                    ┌──→ Deployment ──→ PredictionLog
ModelAsset ──→ ModelVersion ──→ PipelineRun         │
    │               │          (训练执行记录)         │
    │               └──────────────────────────────┘
    │
    └──→ ParameterTemplate (推荐超参数)
```

### ModelAsset（模型资产）

管理的顶层实体，代表一个具体的 AI 能力（如"华东短期负荷预测"）。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | str | UUID 主键 |
| `name` / `slug` | str | 显示名 / URL 友好标识（中文自动转拼音） |
| `task_type` | str | 任务类型（负荷预测、数字识别、异常检测…） |
| `algorithm_type` | str | 算法类型（GBRT、CNN、Transformer…） |
| `framework` | str | 框架（pytorch、sklearn、onnx…） |
| `owner_org` | str | 所属组织 |
| `status` | AssetStatus | 生命周期状态 |
| `applicable_scenarios` | dict | 适用场景（地区、季节、设备类型…） |
| `input_schema` / `output_schema` | dict | 模型输入输出接口定义 |
| `tags` | list[str] | 搜索标签 |

**模型状态流转：**

```text
草稿(draft) ──→ 已注册(registered) ──→ 已共享(shared) ──→ 已归档(archived)
                        │                                        ▲
                        └────────────────────────────────────────┘
```

### ModelVersion（模型版本）

每个模型可以有多个版本。版本是不可变快照，完整记录一次训练的全部输入和输出。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | str | UUID 主键 |
| `asset_id` | str | 所属 ModelAsset ID |
| `version` | str | 语义化版本号（1.0.0, 1.1.0…） |
| `file_format` | str | 权重格式（joblib, torchscript, onnx…） |
| `file_size_bytes` | int | 权重文件大小 |
| `metrics` | dict | 评估指标（accuracy, mae, rmse…） |
| `stage` | VersionStage | 阶段（draft → development → staging → production → archived） |
| `parent_version_id` | str | 来源版本 ID（retrain 或 fork） |
| `source_model_id` | str | 非空表示 fork，指向来源 ModelAsset |
| `artifacts` | dict[str, ArtifactLocation] | 制品清单（5 个类别的存储位置和元数据） |

**版本目录结构 — 5 类制品（Artifacts）：**

```text
model_store/models/{slug}/versions/v1.0.0/
├── version.yaml          # 版本元数据（ID、阶段、指标、制品清单）
├── weights/              # 模型权重（训练产出）
│   └── model.pt
├── datasets/             # 训练数据集
│   ├── train.csv
│   └── MNIST/raw/        # 或二进制格式数据
├── code/                 # 训练代码
│   └── train.py
├── features/             # 特征 / 输入规格定义
│   └── features.yaml
└── params/               # 超参数配置
    └── training_params.yaml
```

**ArtifactLocation** — 每个制品类别的存储描述符：

| 字段 | 说明 |
| --- | --- |
| `backend` | 存储后端（`local`, `s3`, `oss`, `git`, `dvc`…） |
| `uri` | 后端特定资源定位符（本地为相对路径） |
| `size_bytes` | 制品总大小 |
| `checksum` | 完整性校验（如 `sha256:abc123`） |
| `metadata` | 扩展元数据（文件数量、格式信息等） |

版本创建时自动扫描目录生成制品清单（`_scan_artifacts()`），也可通过 `refresh_artifacts()` 手动刷新。

**版本阶段流转：**

```text
草稿(draft) ──→ 开发(development) ──→ 预发布(staging) ──→ 生产(production)
    │                  │                    │                     │
    └──────────────────┴────────────────────┴─────────────────────┘
                              ↓ (均可归档)
                        已归档(archived)
```

### FeatureDefinition（特征定义）与 FeatureGroup（特征组）

全局特征目录，适用于结构化（表格）数据的模型。

| 实体 | 用途 |
| --- | --- |
| **FeatureDefinition** | 单个特征的规范描述：名称、数据类型、单位、取值范围、计算逻辑 |
| **FeatureGroup** | 将多个特征按场景分组（如"华东夏季负荷特征组"），关联 scenario_tags |

> **注意：** 对于图像等非结构化输入的模型（如 MNIST CNN），输入规格通过版本制品中的 `features/features.yaml` 描述（channels、width、height、normalize），不需要全局 FeatureDefinition。

### ParameterTemplate（参数模板）

推荐超参数配置，可关联到特定模型和场景：

| 字段 | 说明 |
| --- | --- |
| `model_asset_id` | 关联的模型（可选） |
| `algorithm_type` | 适用的算法类型 |
| `scenario_tags` | 适用场景标签 |
| `parameters` | 推荐参数键值对 |
| `performance_notes` | 性能说明和调优建议 |

### Deployment（部署）与 PredictionLog（预测日志）

| 实体 | 用途 |
| --- | --- |
| **Deployment** | 将 ModelVersion 部署为在线推理服务（状态：pending → running → stopped / failed） |
| **PredictionLog** | 逐条记录预测请求/响应/延迟/真值回填，用于精度监控 |

### PipelineRun（流水线运行）

训练执行记录，追踪从触发到完成的全过程：

| 字段 | 说明 |
| --- | --- |
| `status` | pending → running → success / failed / cancelled |
| `base_version` | 基础版本号 |
| `pipeline_snapshot` | 执行时的流水线配置快照 |
| `overrides` | 参数覆写 |
| `log` | 实时训练日志 |
| `result_version_id` | 训练成功后自动创建的新版本 ID |

## 版本管理 UI

版本卡片展开后显示 5 个制品分类 Tab，每个 Tab 提供专属的浏览和管理体验：

```text
┌──────────────────────────────────────────────────────┐
│  v1.0.0  [development]  98.80%  1.2 MB  torchscript │  ← 版本摘要
├──────────────────────────────────────────────────────┤
│  [权重]  [数据集]  [代码]  [特征]  [参数]             │  ← 5 个 Tab
├──────────────────────────────────────────────────────┤
│                                                      │
│  (当前 Tab 内容)                                     │
│                                                      │
└──────────────────────────────────────────────────────┘
```

| Tab | 内容 |
| --- | --- |
| **权重** | 文件信息卡（格式/大小）+ 下载按钮 + 评估指标网格 + 重训练/试评估按钮 + 适配引导横幅 |
| **数据集** | 文件列表 + CSV 表格预览（Tabulator）+ IDX-ubyte 图像缩略图网格预览 + 上传/删除 |
| **代码** | 文件列表 + 语法高亮查看（highlight.js）+ 在线编辑/上传/删除 |
| **特征** | 文件列表 + YAML 查看/编辑/上传/删除 |
| **参数** | 文件列表 + YAML 查看/编辑 + 推荐模板按钮/上传/删除 |

### 图像数据集预览

对于 MNIST 等二进制图像数据集（IDX-ubyte 格式），数据集 Tab 自动渲染缩略图网格：

- 解析 IDX3 二进制格式，通过 Pillow 转为 PNG
- 6 列缩略图网格（56px），显示标签
- 支持"加载更多"分页浏览

## 训练流水线（Pipeline）

流水线通过 `pipeline.yaml` 定义训练过程：

```yaml
name: Load Forecast Training Pipeline
stages:
  - name: data_prep
    description: Load and preprocess data
    type: automatic
  - name: training
    description: Train model
    type: automatic
    script: code/train.py
    params_file: params/training_params.yaml
  - name: output
    description: Evaluate and save
    type: automatic
default_params:
  epochs: 3
  batch_size: 64
```

**两种训练模式：**

| 模式     | 流程                                       | 适用场景                       |
| -------- | ------------------------------------------ | ------------------------------ |
| 直接运行 | 复制基础版本 → 执行训练 → 自动创建新版本   | 快速迭代，无需修改输入文件     |
| 草稿准备 | 创建草稿 → 上传/编辑文件 → 手动触发训练    | 需要更换数据集或调整参数       |

## 部署与推理

版本可以部署为在线推理服务。支持的模型格式：

| 格式 | Runner | 说明 |
| --- | --- | --- |
| joblib / pickle | SklearnRunner | scikit-learn 模型 |
| ONNX | OnnxRunner | 跨框架通用格式 |
| PyTorch (.pt) | PyTorchRunner | 需提供模型类 |
| TorchScript | TorchScriptRunner | 可移植，无需类定义 |
| TF SavedModel | TFSavedModelRunner | TensorFlow 格式 |

```bash
# 通过部署名称调用
curl -X POST http://localhost:8000/api/v1/predict/load-forecast-prod \
  -H "Content-Type: application/json" \
  -d '{"input_data": [[1, 2], [3, 4]]}'
```

## 跨区域模型适配

ModelForge 提供完整的跨区域模型适配能力，解决电力行业 AI 模型在不同地区间共享时面临的数据分布差异问题。

### 适配流程

```text
共享模型 ──→ 试评估 ──→ 诊断分析 ──→ Fork ──→ 本地适配 ──→ 重新训练 ──→ 部署
  │            │           │          │          │             │
  │            │           │          │          │             ▼
  │            ▼           ▼          ▼          ▼        新版本自动生成
  │         上传本地     SHAP      创建新模型   替换数据     含权重+指标
  │         标签CSV    特征重要性   复制全部     调整特征
  │                    PSI漂移     资产        修改参数
  │                    检测
  ▼
 兼容 → 直接部署
```

### 试评估与诊断

在复用共享模型前，上传本地带标签数据进行兼容性评估：

- **指标对比** — 计算本地数据上的 MAE/RMSE/MAPE，与原始训练指标逐项对比
- **兼容性判定** — 自动给出三级判定：
  - `compatible` — 指标偏差 ≤10%，可直接部署
  - `moderate_degradation` — 指标偏差 10%-30%，建议适配
  - `severe_degradation` — 指标偏差 >30%，需要重新训练

当检测到退化时，自动运行诊断分析：

- **SHAP 特征重要性** — 识别模型决策的关键特征，指导特征工程调整方向
- **PSI/KS 分布漂移** — 逐特征检测训练数据与本地数据的分布差异，量化漂移程度
- **自动化建议** — 根据诊断结果生成分级建议（critical / warning / info）

### Fork 与适配引导

试评估发现不兼容后，一键 Fork 创建本地适配模型：

1. **Fork** — 从共享模型版本创建新模型，复制全部资产（数据、特征、参数、代码、权重）
2. **适配指南** — 自动在 Fork 后的版本卡片上展示诊断摘要，引导用户：
   - ① 上传本地数据集
   - ② 调整特征定义（移除零方差特征、修正 value_range）
   - ③ 触发重新训练
3. **Dismiss** — 用户了解后可关闭引导 banner

### 重新训练（Retrain）

在版本卡片上直接触发训练，无需切换页面：

- **配置确认** — 显示当前 pipeline 配置，自动检测文件名不匹配并提供覆写下拉
- **热启动（Warm-Start）** — 勾选后基于当前模型权重继续训练（迁移学习），自动处理特征对齐：
  - 检测基础模型的特征集
  - 补零缺失特征
  - 按基础模型特征顺序重排列
- **实时进度** — 训练日志实时滚动，完成后显示指标网格，一键跳转到新版本

### 跨区域适配示例

`examples/cross_region_adaptation/` 提供华东→华北负荷预测的端到端适配示例：

```text
华东模型 (MAPE ~1.4%)
    │
    ├── 直接应用华北数据 → MAPE ~26%（严重退化）
    │
    ├── 诊断分析:
    │   ├── SHAP: heating_index 重要性大幅上升，air_conditioning_index 降至 0
    │   └── PSI: temperature, humidity, heating_index 显著漂移
    │
    ├── 适配策略:
    │   ├── 移除零方差特征 (air_conditioning_index, month)
    │   ├── 调整 value_range 按华北分布
    │   └── Warm-Start 迁移训练
    │
    └── 适配后 → MAPE ~1.3%（优于从零训练的 ~1.8%）
```

运行示例：

```bash
cd examples/cross_region_adaptation
pip install -r requirements.txt
python run_scenario.py          # 完整 8 步演示
python seed_store.py            # 预填充到 ModelForge 平台
```

## 快速开始

```bash
# 安装
pip install -e ".[dev,serving]"

# 预填充示例数据（负荷预测 + MNIST 手写数字识别）
python examples/seed_all.py

# 启动
uvicorn modelforge.main:app --reload

# 访问 Web UI
open http://localhost:8000

# API 文档
open http://localhost:8000/docs
```

**环境变量：**

| 变量                           | 默认值          | 说明             |
| ------------------------------ | --------------- | ---------------- |
| `MODELFORGE_MODEL_STORE_PATH`  | `./model_store` | 模型存储根目录   |
| `MODELFORGE_MAX_UPLOAD_SIZE_MB`| `500`           | 上传文件大小限制 |

## 示例模型

| 示例 | 说明 | 路径 |
| --- | --- | --- |
| **负荷预测** | GBRT 时序回归，含特征工程、CSV 数据集、流水线 | `examples/load_forecast/` |
| **MNIST 手写数字识别** | CNN 图像分类，含 IDX-ubyte 数据集、TorchScript 权重 | `examples/mnist/` |
| **跨区域适配** | 华东→华北负荷预测适配全流程 | `examples/cross_region_adaptation/` |

```bash
# 统一初始化所有示例到 model_store
python examples/seed_all.py

# 或单独运行
python examples/load_forecast/seed_store.py
python examples/mnist/seed_store.py
```

## API 概览

| 模块     | 路径前缀                                             | 功能                                  |
| -------- | ---------------------------------------------------- | ------------------------------------- |
| 模型注册 | `/api/v1/models`                                     | 模型 CRUD、状态流转、Fork、索引刷新   |
| 版本管理 | `/api/v1/models/{id}/versions`                       | 上传版本、创建草稿、阶段流转          |
| 制品管理 | `/api/v1/models/{id}/versions/{vid}/artifacts`       | 上传/查看/编辑/删除训练文件           |
| 数据预览 | `/api/v1/models/{id}/versions/{vid}/datasets`        | CSV 表格预览、图像缩略图网格          |
| 流水线   | `/api/v1/models/{id}/pipeline`                       | 定义和执行训练流水线                  |
| 试评估   | `/api/v1/models/{id}/versions/{vid}/trial-evaluate`  | 上传 CSV 评估兼容性 + 诊断            |
| 导入导出 | `/api/v1/models/import`, `/{id}/export`              | ZIP 打包导入/导出模型                 |
| 特征目录 | `/api/v1/features`, `/api/v1/feature-groups`         | 特征定义和分组管理                    |
| 参数模板 | `/api/v1/parameter-templates`                        | 推荐超参数管理                        |
| 部署     | `/api/v1/deployments`                                | 部署管理、启停控制                    |
| 推理     | `/api/v1/predict/{name}`                             | 通过部署名称调用预测                  |
| 监控     | `/api/v1/deployments/{id}/stats`                     | 预测日志、精度回溯                    |

## 存储结构

```text
model_store/
├── index.yaml                    # 模型快速索引
├── models/
│   └── {slug}/                   # 模型目录（中文名自动转拼音）
│       ├── model.yaml            # 模型元数据
│       ├── pipeline.yaml         # 训练流水线定义
│       ├── runs/                 # 训练运行记录
│       │   └── {run_id}.yaml
│       └── versions/
│           ├── v1.0.0/           # 版本快照（含 5 类制品目录）
│           ├── v1.1.0/
│           └── ...
├── features/
│   ├── definitions/              # 全局特征定义
│   │   └── {id}.yaml
│   └── groups/                   # 特征分组
│       └── {id}.yaml
├── parameter_templates/          # 参数模板
│   └── {id}.yaml
├── deployments/
│   └── deployments.yaml          # 部署列表
└── logs/
    └── {deployment_id}.jsonl     # 预测日志（逐行 JSON）
```

## 测试

```bash
# 运行全部测试
.venv/bin/python -m pytest tests/ -x -q

# 当前测试数：107
```

## 许可证

MIT
