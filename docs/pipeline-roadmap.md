# Pipeline 演进路线图 (A → B → C)

## A: 可视化 Pipeline 视图 (已完成)

版本卡片展示 3 个水平 Pipeline 阶段，替代原有的平铺标签。
仅 UI 层变更，无后端修改。

## B: 结构化 Pipeline 定义

为每个模型添加 `pipeline.yaml`：

```yaml
# model_store/models/{slug}/pipeline.yaml
data_prep:
  dataset: load_2024.csv
  feature_script: feature_transform.py
  feature_config: features.yaml

training:
  script: train.py
  params: hyperparams.yaml
  requirements: requirements.txt

output:
  format: joblib
  metrics: [rmse, mae, mape]
```

需要变更：

- 新增 API：`GET/PUT /models/{id}/pipeline`
- 前端：Pipeline 编辑器（YAML 编辑或结构化表单）
- 将版本创建与 pipeline 定义关联

## C: 执行引擎

### 后端

- 任务队列：Celery / RQ / asyncio subprocess
- 执行流程：
  1. 创建隔离环境（venv / Docker）
  2. 安装依赖（`pip install -r requirements.txt`）
  3. 运行特征工程脚本
  4. 使用参数运行训练脚本
  5. 收集输出（模型文件 + metrics JSON）
  6. 自动在 model_store 中创建新版本
- 资源管理：CPU/内存/GPU 限制、超时控制

### 新增 API

- `POST /models/{id}/pipeline/run` — 触发执行
- `GET /models/{id}/pipeline/runs` — 执行历史
- `GET /models/{id}/pipeline/runs/{run_id}` — 运行详情
- `WS /models/{id}/pipeline/runs/{run_id}/logs` — 实时日志流

### 新增数据模型

```python
class PipelineRun:
    id: str
    model_id: str
    status: Literal["pending", "running", "success", "failed"]
    stages: list[StageRun]  # 每阶段状态
    result_version_id: str | None
    created_at: datetime
    finished_at: datetime | None
```

### 前端

- 模型详情页"运行训练"按钮
- 3 阶段进度条 + 实时日志面板（WebSocket）
- 执行历史列表
