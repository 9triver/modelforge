# 跨区域模型适配示例：华东→华北负荷预测

## 场景

华东省公司已有一个成熟的短期负荷预测模型（XGBoost），在华东地区表现优秀（MAPE ~1.4%）。华北省公司希望复用这个模型，但两个地区存在显著差异：

| 差异维度 | 华东 | 华北 |
|----------|------|------|
| 气候 | 亚热带，冬暖夏热 | 大陆性，冬季严寒 |
| 峰值季节 | 夏季（空调） | 冬季（供暖） |
| 关键特征 | 空调指数、湿度 | 供暖指数、温度 |
| 负荷范围 | 4000-8000 MW | 5000-9000 MW |

两个地区使用统一的 10 特征气象监测体系，但各特征的分布和重要性差异显著。

## 适配技术

本示例覆盖 5 类跨区域适配技术：

1. **特征工程适配** — SHAP 分析识别地区关键特征，场景化特征选择
2. **参数迁移调优** — Optuna 以华东参数为起点做 Warm-Start 搜索
3. **分布漂移检测** — PSI/KS 检验量化两地区数据分布差异
4. **模型微调** — XGBoost warm-start 从华东模型继续训练
5. **模型融合** — 加权平均 + 季节路由（冬季偏北方模型，夏季偏东方模型）

## 8 步演示

| Step | 操作 | 技术 | 预期 MAPE |
|------|------|------|-----------|
| 1 | 训练华东模型 | Baseline | ~1.4% |
| 2 | 直接应用于华北 | — | ~26% |
| 3 | SHAP 特征分析 | 特征重要性对比 | — |
| 4 | 漂移检测 | PSI/KS | — |
| 5 | 华北数据重训练 | 从零训练 | ~1.8% |
| 6 | 参数 Warm-Start | Optuna 调优 | ~1.5-1.7% |
| 7 | Fine-tune | 迁移学习 | ~1.3% |
| 8 | 模型融合 | 加权/季节路由 | ~1.1% |

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 运行完整场景（约2-3分钟）
python run_scenario.py

# 跳过 Optuna（更快）
python run_scenario.py --skip-optuna

# 预填充到 ModelForge 平台
python seed_store.py
```

## 文件说明

| 文件 | 说明 |
|------|------|
| `generate_data.py` | 生成华东/华北模拟负荷数据（各 8760 行） |
| `train.py` | XGBoost 训练脚本，支持 warm-start（兼容 ModelForge pipeline） |
| `feature_analysis.py` | SHAP 特征重要性对比分析 |
| `drift_detection.py` | PSI/KS 分布漂移检测 |
| `param_search.py` | Optuna 超参搜索（Warm-Start 策略） |
| `ensemble_predict.py` | 多模型融合（加权平均 + 季节路由） |
| `run_scenario.py` | 8 步端到端演示脚本 |
| `seed_store.py` | 预填充 model_store 供平台展示 |

## 与 ModelForge 平台集成

`train.py` 遵循 ModelForge pipeline runner 合约：

```bash
python code/train.py \
  --dataset datasets/train.csv \
  --features features/features.yaml \
  --params params/training_params.yaml \
  --output weights/model.joblib
```

`seed_store.py` 会在 model_store 中创建：
- **华东短期负荷预测-XGBoost** — 1 个版本 (v1.0.0, production)
- **华北负荷预测-XGBoost-迁移** — 4 个版本，展示适配进程
- 全局特征定义 10 个 + 特征组 2 个
- 参数模板 2 个（华东推荐 + 华北适配）
