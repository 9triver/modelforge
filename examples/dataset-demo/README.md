# Dataset Demo

演示 ModelForge 的数据集托管功能：上传数据集仓库，浏览器预览，评估时直接引用。

## 三种数据集

| 脚本 | 格式 | 用途 | 对应 model task |
|---|---|---|---|
| `make_csv_dataset.py` | CSV（timestamp + load） | Evaluate / Calibrate | time-series-forecasting |
| `make_image_dataset.py` | ImageFolder（class/xxx.jpg） | Evaluate / Transfer | image-classification |
| `make_coco_dataset.py` | COCO JSON（images/ + annotations.json） | Evaluate | object-detection |

## 快速开始

### 1. 生成并上传 CSV 数据集

```bash
export MODELFORGE_TOKEN=<your-token>

# 生成 30 天 hourly 负荷数据 + 上传
python examples/dataset-demo/make_csv_dataset.py --upload chun/synthetic-load-30d
```

### 2. 生成并上传 ImageFolder 数据集

```bash
# 生成 CIFAR-10 三类子集 + 上传
python examples/dataset-demo/make_image_dataset.py --upload chun/cifar10-3class

# 自定义类别
python examples/dataset-demo/make_image_dataset.py --classes cat,dog --per-class 30 --upload chun/catdog-dataset
```

### 3. 生成并上传 COCO 数据集

```bash
# 生成合成 COCO 数据集（10 张图 + 随机 bbox）+ 上传
python examples/dataset-demo/make_coco_dataset.py --upload chun/synthetic-coco

# 自定义
python examples/dataset-demo/make_coco_dataset.py --n-images 20 --n-categories 5 --upload chun/coco-5class
```

### 4. 浏览器验证

1. 打开首页，左侧 Type 选 "dataset" → 看到紫色 Dataset 卡片
2. 点进 CSV 数据集 → Preview tab → 看到前 100 行表格
3. 点进 ImageFolder 数据集 → Preview tab → 看到缩略图网格
4. 点进 COCO 数据集 → Preview tab → 看到类别统计 + 带 bbox 的缩略图
5. 打开 model 页面 → Evaluate tab → 下拉框选已有数据集 → Run evaluation

### 5. 也可以用 CLI

```bash
# 先生成，再用 CLI 上传
python examples/dataset-demo/make_csv_dataset.py -o load.csv
modelforge dataset upload chun/my-load-data ./load.csv --task time-series-forecasting

# 列出所有数据集
modelforge dataset list
```

## 仅生成（不上传）

```bash
# CSV
python examples/dataset-demo/make_csv_dataset.py --days 7 -o short.csv

# ImageFolder
python examples/dataset-demo/make_image_dataset.py --classes airplane,ship --per-class 10 -o my_images

# COCO
python examples/dataset-demo/make_coco_dataset.py --n-images 5 -o my_coco
```
