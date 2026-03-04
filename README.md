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

```
┌──────────────────────────────────────────────────────────┐
│                    Web UI (SPA)                           │
│              Vanilla JS + Tailwind CSS                    │
└────────────────────────┬─────────────────────────────────┘
                         │ HTTP
┌────────────────────────▼─────────────────────────────────┐
│                   FastAPI Server                          │
│  ┌──────────┐ ┌──────────┐ ┌───────────┐ ┌───────────┐  │
│  │ Registry │ │ Pipeline │ │ Deploy &  │ │ Monitoring│  │
│  │   API    │ │  Runner  │ │ Inference │ │    API    │  │
│  └────┬─────┘ └────┬─────┘ └─────┬─────┘ └─────┬─────┘  │
│       └─────────────┼─────────────┼─────────────┘        │
│                     ▼             ▼                       │
│              ┌─────────────┐ ┌──────────────┐            │
│              │ ModelStore  │ │  Inference   │            │
│              │ (YAML+FS)  │ │   Manager    │            │
│              └──────┬──────┘ └──────────────┘            │
└─────────────────────┼────────────────────────────────────┘
                      ▼
              model_store/  (文件系统)
```

**技术栈：** Python 3.11+ · FastAPI · Pydantic v2 · YAML 存储 · 无数据库

## 模型资产管理

### 模型（ModelAsset）

模型是管理的顶层实体，代表一个具体的 AI 能力（如"华东短期负荷预测"）。

```
模型属性:
├── 基本信息    name, description, owner_org
├── 类型标签    task_type (负荷预测/异常检测/...), algorithm_type, framework
├── 业务元数据  applicable_scenarios, tags
├── 接口定义    input_schema, output_schema
└── 生命周期    status (草稿 → 已注册 → 已共享 → 已归档)
```

**模型状态流转：**

```
草稿(draft) ──→ 已注册(registered) ──→ 已共享(shared) ──→ 已归档(archived)
                        │                                        ▲
                        └────────────────────────────────────────┘
```

- **草稿** — 刚创建，信息可能不完整
- **已注册** — 信息完备，可在本单位内使用
- **已共享** — 发布到全网共享目录，其他省公司可见
- **已归档** — 停用，仅保留历史记录

### 版本（ModelVersion）

每个模型可以有多个版本。版本是不可变快照，完整记录一次训练的全部输入和输出。

```
model_store/models/{slug}/versions/v1.0.0/
├── version.yaml          # 版本元数据（ID、阶段、指标、创建时间）
├── datasets/             # 训练数据集
│   └── train.csv
├── features/             # 特征工程定义
│   └── features.yaml
├── code/                 # 训练代码
│   └── train.py
├── params/               # 超参数配置
│   └── training_params.yaml
├── weights/              # 模型权重（训练产出）
│   └── model.joblib
└── metrics.json          # 评估指标（训练产出）
```

**版本阶段流转：**

```
草稿(draft) ──→ 开发(development) ──→ 预发布(staging) ──→ 生产(production)
    │                  │                    │                     │
    └──────────────────┴────────────────────┴─────────────────────┘
                              ↓ (均可归档)
                        已归档(archived)
```

- **草稿** — 从基础版本复制而来，用户正在准备训练数据和配置，尚未训练
- **开发** — 已完成训练，权重和指标已生成，正在验证中
- **预发布** — 通过验证，在预发布环境中测试
- **生产** — 正式上线，可部署为推理服务
- **已归档** — 停用

### 训练流水线（Pipeline）

流水线定义了模型的训练过程，分为三个阶段：

```
① 数据准备               ② 训练配置               ③ 模型产出
┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
│ datasets/       │ ───→ │ code/           │ ───→ │ weights/        │
│ features/       │      │ params/         │      │ metrics.json    │
└─────────────────┘      └─────────────────┘      └─────────────────┘
   输入：训练数据             输入：训练脚本            输出：模型权重
         特征定义                   超参数                    评估指标
```

流水线通过 `pipeline.yaml` 定义：

```yaml
data_prep:
  dataset: train.csv
  feature_config: features.yaml

training:
  script: train.py
  params: training_params.yaml

output:
  format: joblib
  metrics: [mae, rmse, mape]
```

**两种训练模式：**

| 模式 | 流程 | 适用场景 |
|------|------|----------|
| 直接运行 | 复制基础版本 → 执行训练 → 自动创建新版本 | 快速迭代，无需修改输入文件 |
| 草稿准备 | 创建草稿 → 上传/编辑文件 → 手动触发训练 | 需要更换数据集或调整参数 |

### 部署与推理

版本可以部署为在线推理服务：

```
部署状态:  pending ──→ running ──→ stopped
                          │
                          └──→ failed
```

支持的模型格式：
- **joblib / pickle** — scikit-learn 模型
- **ONNX** — 跨框架通用格式

部署后通过 REST API 进行预测：

```bash
# 通过部署名称调用
curl -X POST http://localhost:8000/api/v1/predict/load-forecast-prod \
  -H "Content-Type: application/json" \
  -d '{"input_data": [[1, 2], [3, 4]]}'
```

## 快速开始

```bash
# 安装
pip install -e ".[dev,serving]"

# 启动
uvicorn modelforge.main:app --reload

# 访问 Web UI
open http://localhost:8000

# API 文档
open http://localhost:8000/docs
```

**环境变量：**

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `MODELFORGE_MODEL_STORE_PATH` | `./model_store` | 模型存储根目录 |
| `MODELFORGE_MAX_UPLOAD_SIZE_MB` | `500` | 上传文件大小限制 |

## API 概览

| 模块 | 路径前缀 | 功能 |
|------|----------|------|
| 模型注册 | `/api/v1/models` | 模型 CRUD、状态流转 |
| 版本管理 | `/api/v1/models/{id}/versions` | 上传版本、创建草稿、阶段流转 |
| 文件管理 | `/api/v1/models/{id}/versions/{vid}/artifacts` | 上传/编辑/删除训练文件 |
| 流水线 | `/api/v1/models/{id}/pipeline` | 定义和执行训练流水线 |
| 部署 | `/api/v1/deployments` | 部署管理、启停控制 |
| 推理 | `/api/v1/predict/{name}` | 通过部署名称调用预测 |
| 监控 | `/api/v1/monitoring` | 预测日志、精度回溯 |

## 存储结构

```
model_store/
├── index.yaml                    # 模型快速索引
├── models/
│   └── {slug}/                   # 模型目录（中文名自动转拼音）
│       ├── model.yaml            # 模型元数据
│       ├── pipeline.yaml         # 训练流水线定义
│       ├── runs/                 # 训练运行记录
│       │   └── {run_id}.yaml
│       └── versions/
│           ├── v1.0.0/           # 版本快照
│           ├── v1.1.0/
│           └── ...
├── deployments/
│   └── deployments.yaml          # 部署列表
└── logs/
    └── {deployment_id}.jsonl     # 预测日志（逐行 JSON）
```

## 测试

```bash
# 运行全部测试
.venv/bin/python -m pytest tests/ -x -q

# 当前测试数：72
```

## 许可证

MIT
