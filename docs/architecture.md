# ModelForge 架构与开发备忘

## 项目概述

电力行业人工智能模型全网共享中心（AI Model Sharing Center for Power Industry）
MLOps 平台，管理模型全生命周期并支持跨区域共享。

## 技术栈

- Python 3.12 + FastAPI
- 文件系统 + YAML 存储（无数据库）
- 本地文件系统存储模型：`model_store/`
- Pydantic v2（schemas）、pydantic-settings（配置）
- 前端：原生 JS SPA + Tailwind CSS (CDN) + Tabulator (CSV 预览) + highlight.js (代码高亮)

## 架构

- 单体应用，模块清晰分离
- 存储层：`FileSystemStore` 读写 YAML + 文件
- 存储结构：`model_store/models/{slug}/versions/v{version}/`，子目录：weights/, datasets/, code/, features/, params/
- InferenceManager：进程内模型服务，遵循 ModelRunner 协议

## 关键路径

| 路径 | 说明 |
|------|------|
| `src/modelforge/` | 主包 |
| `src/modelforge/store.py` | FileSystemStore（list_models, read_model, list_version_artifacts 等） |
| `src/modelforge/api/registry.py` | FastAPI 路由：模型、版本、文件 |
| `src/modelforge/runner.py` | Pipeline 执行引擎 |
| `src/modelforge/web/app.js` | SPA 前端逻辑 |
| `src/modelforge/web/index.html` | HTML 入口 |
| `src/modelforge/main.py` | FastAPI 应用入口 |
| `tests/` | pytest 测试（72 个） |

## UI 结构

- 单页应用，无顶部导航标签（已简化）
- 模型列表 → 模型详情（面包屑导航）
- 模型详情子标签：概览、版本管理、部署与预测、运行监控
- 版本卡片：可折叠，含 Pipeline 阶段视图（data_prep → training → output）

## 版本 Pipeline 视图

- 3 个水平阶段卡片带箭头：① 数据准备 → ② 训练配置 → ③ 模型产出
- 阶段 1（data_prep）：加载 datasets/ + features/ 文件
- 阶段 2（training）：加载 code/ + params/ 文件
- 阶段 3（output）：从 version 对象渲染（权重信息 + 指标），不需 API 调用
- 懒加载，使用 `artifactTabCache`

## 开发环境备注

- 系统配置了代理，本地请求需 `no_proxy=localhost,127.0.0.1`
- 虚拟环境：`.venv/`，运行测试：`.venv/bin/python -m pytest tests/ -x -q`
- 缓存清除：`app.js?v=N`（在 index.html 中），修改后递增 N
- JS 语法检查：`node -c src/modelforge/web/app.js`
