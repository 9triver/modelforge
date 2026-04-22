# ModelForge

自建模型仓库 + 评估 + 校准平台，对标 Hugging Face Hub 的最小可用版本。Git + LFS 存储，无需依赖 GitLab / Gitea。

## 功能

- **Git Smart HTTP**：原生 `git push / git clone`，任意 Git 客户端均可使用
- **Git-LFS**：大文件（权重、数据集）自动分片存储，版本可追溯
- **Model Card 校验**：push 时服务端 hook 自动验证 README.md 的 YAML frontmatter（HF 规范兼容）
- **Web UI**：浏览器查看模型列表、元数据、性能指标、文件清单（含下载）、渲染后的 README
- **Evaluation-as-a-Service**：上传数据 → 平台跑模型 → 返回标准指标（MAPE/accuracy/mAP 等）
- **多方法校准**：评估不达标 → 预览 linear_bias / segmented / stacking 三种校准效果 → 选最好的 fork 新仓库
- **Python SDK**：`modelforge.load("ns/name")` 一行加载模型；`hub.upload_folder()` 上传
- **CLI**：`modelforge serve / run / user / token / repo` 命令行管理

## 支持的 Task

| Task | Handler | 评估指标 | 校准 |
|---|---|---|---|
| `time-series-forecasting` | ForecastingHandler | MAPE/RMSE/MAE/sMAPE | ✅ linear_bias / segmented / stacking |
| `image-classification` | ImageClassificationHandler | accuracy/precision/recall/F1 | 🔜 linear probe |
| `object-detection` | ObjectDetectionHandler | mAP/mAP_50/mAP_75/mAR | 🔜 fine-tune 检测头 |

## 快速开始

```bash
pip install -e .
```

### 启动服务

```bash
modelforge serve                          # 默认 0.0.0.0:8000，数据目录 ~/.local/share/modelforge
modelforge serve --port 8080 --data /data/modelforge
```

### 用户与 Token

```bash
modelforge user create alice
# ✓ 用户已创建: alice
# Token（只显示这一次）: mf_xxxxxxxxxxxxxxxxxxxxxxx

modelforge user list
modelforge token create alice             # 补发 token
```

### 仓库管理

```bash
modelforge repo create my-model alice    # 创建仓库
modelforge repo list
modelforge repo delete my-model
```

### 推送模型（原生 Git）

```bash
cd my-model-dir
git init && git add .
git commit -m "v1.0 initial"
git remote add origin http://alice:mf_xxx@localhost:8000/my-model.git
git push -u origin main
```

### Python SDK

```python
from modelforge.client import ModelHub

hub = ModelHub("http://localhost:8000", token="mf_xxx")

# 列出所有仓库
repos = hub.list_repos()

# 上传本地目录（含 README.md Model Card）
sha = hub.upload_folder("my-model", "./my-model-dir/", "v1.1 tuned", tag="v1.1")

# 下载到本地缓存
local_dir = hub.snapshot_download("my-model", revision="v1.1")
```

### 一行加载模型

```python
import modelforge

handler = modelforge.load("amazon/chronos-t5-tiny")
pred_df = handler.predict(df)  # 直接调用，返回 DataFrame
```

### CLI 推理

```bash
modelforge run amazon/chronos-t5-tiny --input data.csv --output pred.csv
modelforge run nateraw/vit-base-cats-vs-dogs --input images/ --output results.json
modelforge run ultralytics/yolov8n --input photos/ --output detections.json
```

## Model Card 规范

每个仓库根目录必须有 `README.md`，以 YAML frontmatter 开头：

```markdown
---
license: apache-2.0
library_name: lightgbm
tags:
  - time-series-forecasting
pipeline_tag: tabular-regression
model-index:
  - name: my-model
    results:
      - task:
          type: tabular-regression
          name: Load Forecasting
        dataset:
          name: City Load Data 2024-2025
          type: proprietary
        metrics:
          - type: mape
            name: CV MAPE (%)
            value: 3.8
---

# My Model

...正文 Markdown...
```

frontmatter 必填字段：`license`、`library_name`、`tags`（至少一个）。push 时服务端自动校验，不合规则拒绝并返回详细错误信息。

## 架构

```
                          ┌─────────────────────────────────────────────────────────┐
                          │                    FastAPI Server                       │
                          │                    (server.py)                          │
                          │                                                         │
  ┌──────────┐            │  ┌──────────────────────────────────────────────────┐   │
  │ Browser  │───GET /───▶│  │  Web UI (web.py)                                │   │
  │          │◀──HTML─────│  │  / 模型列表（搜索/过滤）  /{repo} 详情页        │   │
  └──────────┘            │  │       │                        │                 │   │
                          │  │       ▼                        ▼                 │   │
                          │  │  db.search_repos()      repo_reader.py          │   │
                          │  │                         ├ read_file()            │   │
                          │  │                         ├ list_files()           │   │
                          │  │                         └ has_any_commits()      │   │
                          │  └──────────────────────────────────────────────────┘   │
                          │                                                         │
  ┌──────────┐            │  ┌──────────────────────────────────────────────────┐   │
  │ Python   │──search()─▶│  │  REST API (api/repos.py)                        │   │
  │ SDK      │◀──JSON─────│  │  POST /api/v1/repos          创建仓库           │   │
  │(client.py│            │  │  GET  /api/v1/repos           列表               │   │
  │          │            │  │  GET  /api/v1/repos/search    搜索               │   │
  └──────────┘            │  │  DELETE /api/v1/repos/{name}  删除               │   │
       │                  │  └──────────────────────────────────────────────────┘   │
       │                  │                                                         │
       │                  │  ┌──────────────────────────────────────────────────┐   │
       │ git push/clone   │  │  Git Smart HTTP (api/git_routes.py)             │   │
  ┌────┴─────┐            │  │                                                  │   │
  │ Git      │──HTTP──────│  │  GET  /{repo}.git/info/refs                     │   │
  │ Client   │◀───────────│  │  POST /{repo}.git/git-upload-pack   (clone)     │   │
  │          │            │  │  POST /{repo}.git/git-receive-pack  (push)      │   │
  └────┬─────┘            │  │       │                                          │   │
       │                  │  │       ▼                                          │   │
       │                  │  │  ┌──────────────────────┐                        │   │
       │                  │  │  │  git-http-backend     │  系统 CGI 程序        │   │
       │                  │  │  │  (subprocess)         │                        │   │
       │                  │  │  └──────────┬───────────┘                        │   │
       │                  │  └─────────────│────────────────────────────────────┘   │
       │                  │                │                                         │
       │                  │                ▼  push 时触发                            │
       │                  │  ┌──────────────────────────────────────────────────┐   │
       │                  │  │  Pre-Receive Hook (hooks/pre_receive.py)         │   │
       │                  │  │                                                  │   │
       │                  │  │  stdin: <old-sha> <new-sha> <ref>               │   │
       │                  │  │       │                                          │   │
       │                  │  │       ▼                                          │   │
       │                  │  │  git show {sha}:README.md                        │   │
       │                  │  │       │                                          │   │
       │                  │  │       ▼                                          │   │
       │                  │  │  schema.validate_model_card()                    │   │
       │                  │  │       │                                          │   │
       │                  │  │       ├── 失败 → exit 1（push 被拒绝）          │   │
       │                  │  │       │                                          │   │
       │                  │  │       └── 成功 → db.upsert_repo_card()          │   │
       │                  │  │                  （frontmatter 入库供搜索）      │   │
       │                  │  └──────────────────────────────────────────────────┘   │
       │                  │                                                         │
       │ git lfs          │  ┌──────────────────────────────────────────────────┐   │
       │ push/pull        │  │  LFS Batch API (api/lfs_routes.py)              │   │
       └──────────────────│  │                                                  │   │
                          │  │  POST /{repo}.git/info/lfs/objects/batch         │   │
                          │  │  PUT  /{repo}.git/lfs/objects/{oid}   (upload)   │   │
                          │  │  GET  /{repo}.git/lfs/objects/{oid}   (download) │   │
                          │  │  POST /{repo}.git/lfs/verify                     │   │
                          │  └──────────────────────────────────────────────────┘   │
                          │                                                         │
                          │  ┌────────────┐  ┌──────────┐  ┌───────────────────┐   │
                          │  │  auth.py    │  │ config.py│  │ storage.py        │   │
                          │  │ Token 认证  │  │ 全局配置 │  │ 裸仓库管理+Hook  │   │
                          │  └────────────┘  └──────────┘  └───────────────────┘   │
                          └─────────────────────────┬───────────────────────────────┘
                                                    │
                          ┌─────────────────────────▼───────────────────────────────┐
                          │                    数据层                                │
                          │                                                         │
                          │  modelforge.db          repos/              lfs/        │
                          │  ┌──────────────┐       ┌──────────────┐   ┌────────┐  │
                          │  │ users        │       │ model.git/   │   │ ab/    │  │
                          │  │ tokens       │       │  ├ objects/   │   │  cd/   │  │
                          │  │ repos        │       │  ├ refs/      │   │   {oid}│  │
                          │  │ repo_cards   │       │  └ hooks/     │   │        │  │
                          │  │  (搜索索引)  │       │    pre-receive│   │        │  │
                          │  └──────────────┘       └──────────────┘   └────────┘  │
                          │     SQLite                裸 Git 仓库       LFS 物件池  │
                          └─────────────────────────────────────────────────────────┘
```

### 关键数据流

| 场景 | 路径 |
|------|------|
| `git clone` | Git Client → `git_routes` → `git-http-backend` → 裸仓库 |
| `git push` | Git Client → `git_routes` → `auth` → `git-http-backend` → 裸仓库 → `pre-receive hook` → `schema` 校验 → `db` 入库 |
| `git lfs push` | Git Client → `lfs_routes` → `auth` → `lfs_store` 写入 LFS 物件池 |
| `hub.search()` | SDK → `repos.py /search` → `db.search_repos()` → `repo_cards` 表 |
| `hub.upload_folder()` | SDK → 本地校验 → `git clone` + 覆盖 + `git push`（触发上述 push 流程） |
| 浏览器访问 | Browser → `web.py` → `repo_reader`（`git show`）→ `schema.parse_frontmatter` → Jinja2 渲染 |

## 存储结构

```
{data_dir}/
├── modelforge.db           SQLite：用户 / Token / 仓库注册表
├── repos/
│   ├── my-model.git/       裸 Git 仓库（含 hooks/pre-receive）
│   └── ...
└── lfs/
    └── ab/cd/abcd...       LFS 物件（按 SHA256 两级目录分片）
```

模型文件的版本历史在裸 Git 仓库里，大文件内容在 LFS 物件池里，两者通过 LFS 指针文件关联。

## 项目结构

```
src/modelforge/
├── __init__.py             顶层 API（load()）
├── loader.py               modelforge.load() 实现
├── config.py               配置（data_dir / host / port / git 路径）
├── db.py                   SQLite 持久层（users / tokens / repos / evaluations / calibrations）
├── auth.py                 Bearer Token + Basic Auth 认证
├── storage.py              裸仓库创建、pre-receive hook 安装
├── lfs_store.py            LFS 物件读写（SHA256 校验）
├── repo_reader.py          从裸仓库读文件 + checkout + LFS 实化
├── schema.py               Model Card frontmatter 解析与校验
├── server.py               FastAPI 应用工厂
├── client.py               Python SDK（list_repos / snapshot_download / upload_folder）
├── cli.py                  Typer CLI（serve / run / user / token / repo）
├── api/
│   ├── repos.py            仓库 CRUD API
│   ├── preview.py          Web UI 预览 API（model card / files / refs / facets）
│   ├── evaluations.py      评估 API（upload → evaluate → metrics）
│   ├── calibrations.py     校准 API（preview → compare → save fork）
│   ├── download.py         单文件下载（普通 + LFS 流式）
│   ├── git_routes.py       Git Smart HTTP（git-http-backend 代理）
│   └── lfs_routes.py       Git-LFS Batch API
├── runtime/
│   ├── tasks/              TaskHandler 基类 + forecasting / image-classification / object-detection
│   ├── datasets/           标准数据 loader（CSV / ImageFolder / COCO JSON）
│   ├── metrics/            标准指标（MAPE / accuracy / mAP 等）
│   ├── evaluator.py        handler 动态加载 + 评估分发
│   └── calibration.py      三种校准方法 + handler template 生成 + fork 仓库组装
├── hooks/
│   └── pre_receive.py      push 时 Model Card 校验
└── static/                 Vite + React 前端构建产物

web/                        前端源码（Vite + React + Tailwind）
examples/                   demo 素材（chronos / vit-cats-dogs / yolov8n）
deploy/                     systemd service + CI/CD workflow
```

## 依赖

- Python ≥ 3.10
- Git（系统级，含 `git-http-backend`）
- `git-lfs`（客户端推送大文件时需要）

```
fastapi  uvicorn  pydantic  pydantic-settings
typer  rich  pyyaml  httpx  jinja2  markdown-it-py
```
