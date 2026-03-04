"""
负荷预测模型全网共享 —— 端到端工作流演示
Load Forecast Model Cross-Region Sharing - End-to-End Workflow

Simulates the full lifecycle:
1. 华东省公司 trains and registers a load forecast model
2. Configures features and saves parameter template
3. 西北省公司 discovers, deploys, and runs predictions
4. Actuals are submitted and accuracy is tracked
"""

import json
import os
import sys
import time

import numpy as np
import requests

# Bypass proxy for localhost
os.environ.setdefault("no_proxy", "localhost,127.0.0.1")

BASE_URL = os.environ.get("MODELFORGE_URL", "http://localhost:8000") + "/api/v1"


def check_server():
    try:
        base = os.environ.get("MODELFORGE_URL", "http://localhost:8000")
        resp = requests.get(f"{base}/health", timeout=3)
        if resp.status_code == 200:
            print(f"  Server is running: {resp.json()}")
            return True
    except requests.ConnectionError:
        pass
    print("  ERROR: Server is not running. Start it with: make dev")
    return False


def step1_train_model():
    """Step 1: 华东省公司训练负荷预测模型"""
    print("\n" + "=" * 60)
    print("Step 1: 华东省公司训练负荷预测模型")
    print("=" * 60)

    from train_model import train

    metrics = train()
    return metrics


def step2_register_model(metrics: dict) -> dict:
    """Step 2: 在 ModelForge 注册模型资产"""
    print("\n" + "=" * 60)
    print("Step 2: 注册模型资产到 ModelForge")
    print("=" * 60)

    resp = requests.post(f"{BASE_URL}/models", json={
        "name": "华东短期负荷预测模型-GBR-v1",
        "description": (
            "基于梯度提升回归(GradientBoosting)的短期电力负荷预测模型。"
            "使用温度、湿度、时间特征预测未来24小时负荷。"
            "在华东地区2024年全年数据上训练，适用于温带气候区域。"
        ),
        "task_type": "load_forecast",
        "algorithm_type": "GradientBoosting",
        "framework": "sklearn",
        "owner_org": "华东省公司",
        "tags": ["load_forecast", "short_term", "gradient_boosting", "tabular"],
        "applicable_scenarios": {
            "region": ["华东", "华中", "华南"],
            "season": ["all"],
            "forecast_horizon": "24h",
            "data_frequency": "hourly",
        },
        "algorithm_description": (
            "使用 sklearn GradientBoostingRegressor 集成学习算法。\n"
            "算法假设: 负荷与温度呈非线性关系（U型曲线），存在明显日周期和周周期。\n"
            "已知局限: 对极端天气事件（台风、暴雪）预测能力有限，"
            "对节假日调休场景需要额外处理。\n"
            "适用条件: 需要至少6个月历史数据，数据采集频率为小时级。"
        ),
        "input_schema": {
            "features": ["temperature", "humidity", "hour", "day_of_week", "is_weekend", "month"],
            "types": {
                "temperature": "float (celsius)",
                "humidity": "float (percent)",
                "hour": "int (0-23)",
                "day_of_week": "int (0=Mon, 6=Sun)",
                "is_weekend": "int (0 or 1)",
                "month": "int (1-12)",
            },
        },
        "output_schema": {
            "load_mw": "float (megawatts)",
        },
    })
    resp.raise_for_status()
    asset = resp.json()
    print(f"  Model registered: id={asset['id']}, name={asset['name']}")
    return asset


def step3_upload_version(asset_id: str, metrics: dict) -> dict:
    """Step 3: 上传模型版本文件"""
    print("\n" + "=" * 60)
    print("Step 3: 上传模型版本文件")
    print("=" * 60)

    with open("load_forecast_model.joblib", "rb") as f:
        resp = requests.post(
            f"{BASE_URL}/models/{asset_id}/versions",
            data={
                "version": "1.0.0",
                "file_format": "joblib",
                "metrics": json.dumps(metrics),
                "description": "Initial training on 2024 华东 full-year data",
            },
            files={"file": ("load_forecast_model.joblib", f)},
        )
    resp.raise_for_status()
    version = resp.json()
    print(f"  Version uploaded: {version['version']}, size={version['file_size_bytes']} bytes")
    print(f"  Metrics: MAE={metrics['mae']:.2f}, MAPE={metrics['mape']:.2f}%")

    # Transition: draft -> registered -> shared
    requests.patch(
        f"{BASE_URL}/models/{asset_id}/status",
        json={"target_status": "registered"},
    ).raise_for_status()
    requests.patch(
        f"{BASE_URL}/models/{asset_id}/status",
        json={"target_status": "shared"},
    ).raise_for_status()
    print("  Model status: shared (全网可见)")

    return version


def step4_register_features(asset_id: str) -> dict:
    """Step 4: 注册特征定义和特征组"""
    print("\n" + "=" * 60)
    print("Step 4: 注册特征定义和特征组")
    print("=" * 60)

    features_config = [
        {"name": "temperature", "data_type": "float", "unit": "celsius",
         "description": "环境温度（摄氏度）", "value_range": {"min": -40, "max": 50}},
        {"name": "humidity", "data_type": "float", "unit": "percent",
         "description": "相对湿度（百分比）", "value_range": {"min": 0, "max": 100}},
        {"name": "hour", "data_type": "int", "unit": None,
         "description": "一天中的小时 (0-23)", "value_range": {"min": 0, "max": 23}},
        {"name": "day_of_week", "data_type": "int", "unit": None,
         "description": "星期几 (0=周一, 6=周日)", "value_range": {"min": 0, "max": 6}},
        {"name": "is_weekend", "data_type": "int", "unit": None,
         "description": "是否周末 (0=工作日, 1=周末)", "value_range": {"min": 0, "max": 1}},
        {"name": "month", "data_type": "int", "unit": None,
         "description": "月份 (1-12)", "value_range": {"min": 1, "max": 12}},
    ]

    feature_ids = []
    for fc in features_config:
        resp = requests.post(f"{BASE_URL}/features/definitions", json=fc)
        resp.raise_for_status()
        feature_ids.append(resp.json()["id"])
        print(f"  Feature registered: {fc['name']}")

    group_resp = requests.post(f"{BASE_URL}/features/groups", json={
        "name": "华东负荷预测标准特征集",
        "description": "华东地区短期负荷预测标准特征集，包含气象和时间特征",
        "scenario_tags": {"region": "华东", "task": "load_forecast"},
        "feature_ids": feature_ids,
    })
    group_resp.raise_for_status()
    group = group_resp.json()
    print(f"  Feature group created: {group['name']} ({len(group['features'])} features)")

    # Associate with model
    requests.post(f"{BASE_URL}/models/{asset_id}/feature-groups/{group['id']}").raise_for_status()
    print(f"  Feature group associated with model")

    return group


def step5_save_parameters(asset_id: str) -> dict:
    """Step 5: 保存推荐参数模板"""
    print("\n" + "=" * 60)
    print("Step 5: 保存推荐参数模板")
    print("=" * 60)

    resp = requests.post(f"{BASE_URL}/parameter-templates", json={
        "name": "GBR负荷预测-华东推荐参数",
        "model_asset_id": asset_id,
        "algorithm_type": "GradientBoosting",
        "scenario_tags": {"region": "华东", "forecast_horizon": "24h", "climate": "temperate"},
        "parameters": {
            "n_estimators": 200,
            "max_depth": 6,
            "learning_rate": 0.1,
            "random_state": 42,
        },
        "performance_notes": (
            "在华东2024年全年数据上训练，MAPE约2-3%。\n"
            "建议: 西北地区可能需要增加 n_estimators 到 300，"
            "因为气温变化更剧烈。"
        ),
    })
    resp.raise_for_status()
    template = resp.json()
    print(f"  Parameter template saved: {template['name']}")
    print(f"  Params: {template['parameters']}")

    return template


def step6_discover_model() -> dict:
    """Step 6: 西北省公司搜索发现负荷预测模型"""
    print("\n" + "=" * 60)
    print("Step 6: 西北省公司搜索发现模型")
    print("=" * 60)

    resp = requests.get(f"{BASE_URL}/models", params={
        "task_type": "load_forecast",
        "status": "shared",
    })
    resp.raise_for_status()
    models = resp.json()
    print(f"  Found {len(models)} shared load forecast model(s):")
    for m in models:
        print(f"    - {m['name']} (by {m['owner_org']}, algorithm: {m['algorithm_type']})")

    model = models[0]

    # View details
    detail = requests.get(f"{BASE_URL}/models/{model['id']}").json()
    print(f"\n  Model details:")
    print(f"    Algorithm: {detail['algorithm_type']}")
    print(f"    Scenarios: {detail['applicable_scenarios']}")

    # View features
    groups = requests.get(f"{BASE_URL}/models/{model['id']}/feature-groups").json()
    if groups:
        print(f"    Features: {[f['name'] for f in groups[0]['features']]}")

    # View parameter templates
    templates = requests.get(
        f"{BASE_URL}/parameter-templates",
        params={"model_asset_id": model["id"]},
    ).json()
    if templates:
        print(f"    Recommended params: {templates[0]['parameters']}")
        print(f"    Notes: {templates[0]['performance_notes']}")

    return model


def step7_deploy_and_predict(model: dict) -> tuple[str, list]:
    """Step 7: 西北省公司部署模型并进行预测"""
    print("\n" + "=" * 60)
    print("Step 7: 西北省公司部署模型并预测")
    print("=" * 60)

    versions = requests.get(f"{BASE_URL}/models/{model['id']}/versions").json()
    version = versions[0]

    # Create deployment
    deploy_resp = requests.post(f"{BASE_URL}/deployments", json={
        "name": "西北-负荷预测-试运行",
        "model_version_id": version["id"],
    })
    deploy_resp.raise_for_status()
    deployment = deploy_resp.json()
    print(f"  Deployment created: {deployment['name']}")

    # Start
    start_resp = requests.post(f"{BASE_URL}/deployments/{deployment['id']}/start")
    start_resp.raise_for_status()
    print(f"  Deployment started: status={start_resp.json()['status']}")

    # Predict next 24 hours (simulate July summer day in northwest)
    print(f"\n  Predicting 24-hour load for 西北地区 summer day:")
    predictions = []
    np.random.seed(100)

    for h in range(24):
        temp = 25 + 12 * np.sin((h - 6) * np.pi / 12) + np.random.normal(0, 1)
        hum = 35 + np.random.normal(0, 3)
        is_wd = 0  # Tuesday
        inp = [[round(temp, 1), round(hum, 1), h, 1, is_wd, 7]]

        resp = requests.post(
            f"{BASE_URL}/deployments/{deployment['id']}/predict",
            json={"input_data": inp},
        )
        resp.raise_for_status()
        result = resp.json()
        predictions.append(result)

        output = result["output"]
        if isinstance(output, dict):
            load = output.get("value", output)
        else:
            load = output
        if isinstance(load, list):
            load = load[0]
        if h % 6 == 0:
            print(f"    {h:02d}:00  temp={inp[0][0]}°C  → load={load:.0f} MW"
                  f"  (latency={result['latency_ms']:.1f}ms)")

    print(f"\n  Total predictions: {len(predictions)}")
    return deployment["id"], predictions


def step8_submit_actuals(deployment_id: str, predictions: list):
    """Step 8: 回传真实值，查看精度指标"""
    print("\n" + "=" * 60)
    print("Step 8: 回传真实值，查看精度指标")
    print("=" * 60)

    # Simulate actual values (predictions + some noise)
    np.random.seed(200)
    actuals = []
    for pred in predictions:
        output = pred["output"]
        if isinstance(output, dict):
            pred_value = output.get("value", list(output.values())[0])
        else:
            pred_value = output
        if isinstance(pred_value, list):
            pred_value = pred_value[0]
        actual = pred_value + np.random.normal(0, 150)  # add noise
        actuals.append({
            "prediction_id": pred["prediction_id"],
            "actual_value": round(actual, 1),
        })

    resp = requests.post(
        f"{BASE_URL}/deployments/{deployment_id}/actuals",
        json={"actuals": actuals},
    )
    resp.raise_for_status()
    result = resp.json()
    print(f"  Actuals submitted: {result['updated']} records updated")

    # Get metrics
    metrics = requests.get(f"{BASE_URL}/deployments/{deployment_id}/metrics").json()
    print(f"\n  Accuracy Metrics:")
    print(f"    Count: {metrics['count']} predictions with actuals")
    print(f"    MAE:   {metrics['mae']:.2f} MW")
    print(f"    RMSE:  {metrics['rmse']:.2f} MW")
    if metrics.get("mape"):
        print(f"    MAPE:  {metrics['mape']:.2f}%")

    # Get stats
    stats = requests.get(f"{BASE_URL}/deployments/{deployment_id}/stats").json()
    print(f"\n  Runtime Stats:")
    print(f"    Total predictions: {stats['total_predictions']}")
    print(f"    Avg latency:  {stats['avg_latency_ms']:.2f} ms")
    print(f"    P95 latency:  {stats['p95_latency_ms']:.2f} ms")
    print(f"    Error rate:   {stats['error_rate']:.1%}")


def main():
    print("=" * 60)
    print("ModelForge 负荷预测模型全网共享 端到端演示")
    print("=" * 60)

    if not check_server():
        sys.exit(1)

    # 华东省公司: 训练 → 注册 → 配置
    metrics = step1_train_model()
    asset = step2_register_model(metrics)
    version = step3_upload_version(asset["id"], metrics)
    step4_register_features(asset["id"])
    step5_save_parameters(asset["id"])

    # 西北省公司: 发现 → 部署 → 预测 → 监控
    model = step6_discover_model()
    deployment_id, predictions = step7_deploy_and_predict(model)
    step8_submit_actuals(deployment_id, predictions)

    print("\n" + "=" * 60)
    print("全流程演示完成!")
    print("=" * 60)
    print(f"\n访问 http://localhost:8000/docs 查看完整 API 文档")


if __name__ == "__main__":
    main()
