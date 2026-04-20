# ModelForge

自建模型仓库服务，对标 Hugging Face Hub 的最小可用版本。Git + LFS 存储，无需依赖 GitLab / Gitea。

## 功能

- **Git Smart HTTP**：原生 `git push / git clone`，任意 Git 客户端均可使用
- **Git-LFS**：大文件（权重、数据集）自动分片存储，版本可追溯
- **Model Card 校验**：push 时服务端 hook 自动验证 README.md 的 YAML frontmatter（HF 规范兼容）
- **Web UI**：浏览器查看模型列表、元数据、性能指标、文件清单、渲染后的 README
- **Python SDK**：三行代码上传/下载模型包
- **CLI**：`modelforge serve / user / token / repo` 命令行管理

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
├── config.py               配置（data_dir / host / port / git 路径）
├── db.py                   SQLite 持久层（users / tokens / repos）
├── auth.py                 Bearer Token + Basic Auth 认证
├── storage.py              裸仓库创建、pre-receive hook 安装
├── lfs_store.py            LFS 物件读写（SHA256 校验）
├── repo_reader.py          从裸仓库读文件（供 Web UI 使用）
├── schema.py               Model Card frontmatter 解析与校验
├── server.py               FastAPI 应用工厂
├── web.py                  Web UI 路由（/ 列表，/{repo} 详情）
├── client.py               Python SDK（list_repos / snapshot_download / upload_folder）
├── cli.py                  Typer CLI
├── api/
│   ├── repos.py            仓库 CRUD API
│   ├── git_routes.py       Git Smart HTTP（git-http-backend 代理）
│   └── lfs_routes.py       Git-LFS Batch API
├── hooks/
│   └── pre_receive.py      push 时 Model Card 校验
└── templates/
    ├── base.html
    ├── index.html
    └── repo.html
```

## 依赖

- Python ≥ 3.10
- Git（系统级，含 `git-http-backend`）
- `git-lfs`（客户端推送大文件时需要）

```
fastapi  uvicorn  pydantic  pydantic-settings
typer  rich  pyyaml  httpx  jinja2  markdown-it-py
```
