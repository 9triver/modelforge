# ModelForge 开发进度

## 已完成

### Phase 1 — Git Smart HTTP 服务端
- 裸 Git 仓库存储（`git init --bare`）
- `git-http-backend` CGI 代理（clone / fetch / push）
- SQLite 元数据层（users / tokens / repos）
- Bearer Token + Basic Auth 认证
- Typer CLI（`modelforge serve / user / token / repo`）

### Phase 2 — Git-LFS Batch API
- LFS Batch API（`POST /{repo}.git/info/lfs/objects/batch`）
- LFS 物件上传（PUT）、下载（GET）、验证（POST verify）
- SHA256 两级目录分片存储（`lfs/ab/cd/{oid}`）

### Python SDK
- `ModelHub.list_repos()` — 列出所有仓库
- `ModelHub.snapshot_download()` — 克隆仓库到本地缓存（含 LFS pull）
- `ModelHub.upload_folder()` — 本地目录一键推送（含 Model Card 预校验 + 可选 tag）
  - LFS 自动追踪：扫描大文件（>10MB）和已知后缀（.safetensors/.bin/.ckpt/.pkl/...），自动 `git lfs track`
  - 复用已有 `.gitattributes`：如果源目录已有（如从 HF 下载的），直接使用
  - 进度输出：文件数/总大小、LFS 追踪模式、push 进度
- `ModelHub.search()` — 按 Model Card 字段组合搜索
- `ModelHub.mirror_from_hf()` — 从 Hugging Face Hub 镜像模型到 ModelForge（一行代码）

### Phase 3b — Web UI（HF 风格）
- 首页：左侧 faceted filter sidebar（Library / Task / Tag / Max MAPE）+ 模型卡片列表
- 详情页：Tab 切换（Model Card | Files）
- 详情页右侧 sidebar：`git clone` 命令、Python SDK 代码片段、Model Info
- Files tab：branch / tag 下拉切换器，文件列表含 LFS 标记和大小
- Tags 可点击跳转首页筛选
- Markdown 渲染（markdown-it-py）+ HF model-index 性能指标表

### Model Card 规范 + 校验
- `schema.py`：HF 兼容 YAML frontmatter 解析 + Pydantic 校验（必填：license / library_name / tags）
- `hooks/pre_receive.py`：push 时服务端自动校验 README.md，不合规则拒绝
- 校验通过后自动提取 frontmatter 关键字段写入 `repo_cards` 表（供搜索 API 使用）

### 搜索/过滤
- DB：`repo_cards` 表（library_name / pipeline_tag / license / tags_json / best_metric_name / best_metric_value）
- REST API：`GET /api/v1/repos/search?library=lightgbm&metric=mape&max_metric=4.0&tag=...`
- SDK：`hub.search(library=..., metric=..., max_metric=..., tag=...)`
- Web UI：首页 faceted filter 联动

### 流式传输（防大文件 OOM）
- Git push/clone：`request.stream()` → `asyncio subprocess stdin/stdout` → `StreamingResponse`
- LFS upload：流式写入临时文件 + 边写边算 SHA256，校验通过后原子 rename
- LFS download：256KB 分块读取 → `StreamingResponse`

### Dogfooding
- 13 个江苏地市负荷预测模型全部推送到本地 ModelForge 实例
- 仓库名使用拼音（nanjing / suzhou / ...），中文保留在 Model Card tags 中
- HF 风格 README.md（YAML frontmatter + model-index 性能指标）
- `generate_model_cards.py` 批量生成 + `publish_to_modelforge.py` 批量推送

## 未做

| 方向 | 说明 | 优先级 |
|------|------|--------|
| 测试 | pytest 覆盖核心路径（schema / db / search / LFS / Git 协议） | 高 |
| 权限细化 | 按仓库设权限（目前有 token 就能 push 任何仓库） | 中 |
| HTTPS | TLS 终止（反向代理或内置） | 中 |
| CI / 自动发布 | 重训 → 生成 Card → 打 tag → push 完整管道 | 中 |
| 搜索增强 | 全文搜索 README body、按 metric 排序 | 低 |
| 多用户协作 | 组织 / 团队 / 仓库可见性控制 | 低 |
