---
license: agpl-3.0
library_name: ultralytics
pipeline_tag: object-detection
tags:
  - object-detection
  - yolo
  - yolov8
  - coco
---

# YOLOv8n — ModelForge mirror

Mirror of [ultralytics/yolov8n](https://docs.ultralytics.com/models/yolov8/)，COCO 80 类目标检测。

## 评估数据格式

ZIP，含 COCO 格式标注：

```
data.zip
└── data/
    ├── images/
    │   ├── 000001.jpg
    │   └── ...
    └── annotations.json
```

`annotations.json` 遵循 [COCO 标准](https://cocodataset.org/#format-data)。

## 指标

- mAP = mAP@IoU=0.50:0.95（COCO 主指标）
- mAP_50 / mAP_75 / mAR

## 依赖

部署机 venv：

```
ultralytics>=8.0
pycocotools>=2.0
torch
```

## 来源

- 权重：https://github.com/ultralytics/assets/releases
- 论文：[YOLOv8](https://docs.ultralytics.com/)
