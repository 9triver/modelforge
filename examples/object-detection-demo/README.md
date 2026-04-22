# Object Detection Demo — YOLOv8n

端到端 demo：镜像 YOLOv8n 到 ModelForge，配好 handler 和测试数据，演示 **Evaluate** 功能（object-detection task）。

## 0. 先决条件（部署机）

```bash
ssh chun@192.168.30.134
cd /home/chun/modelforge
.venv/bin/pip install ultralytics pycocotools
.venv/bin/pip install -e ".[runtime-detection]"
systemctl --user restart modelforge.service
```

## 1. Mac 本地：镜像模型

```bash
export MODELFORGE_TOKEN=<your-token>
export MODELFORGE_URL=http://192.168.30.134:8000

pip install ultralytics
python examples/object-detection-demo/mirror.py
```

脚本做的事：
1. `YOLO("yolov8n.pt")` 自动下载权重到本地（~6MB）
2. 叠加 `overlay/` 里的 `README.md`、`handler.py`、`.gitattributes`
3. `ModelHub.upload_folder` → 推到 ModelForge（yolov8n.pt 走 LFS）

## 2. 生成测试数据

```bash
python examples/object-detection-demo/make_dataset.py
# wrote 10 images + annotations.json -> .../coco_test.zip
```

生成合成 COCO 数据（随机 bbox + 纯色图）。能跑通 evaluator 链路，mAP 接近 0（YOLO 在纯色图上检测不到东西）。

如果想看有意义的 mAP，用真实 COCO val 图片替换 images/ 目录。

## 3. 浏览器里跑评估

1. 打开 http://192.168.30.134:8000/ultralytics/yolov8n
2. 点 **Evaluate** tab
3. 拖入 `coco_test.zip`
4. **Run evaluation**
5. 看到指标表：mAP / mAP_50 / mAP_75 / mAR，primary = mAP 高亮

## handler 逻辑

`overlay/handler.py`：

- `ultralytics.YOLO` 加载 yolov8n.pt
- 逐张推理，`box.xyxy` → COCO `[x, y, w, h]` 格式
- 按 score 降序排列

## 排错

| 症状 | 原因 |
|---|---|
| `ModuleNotFoundError: ultralytics` | 部署机 venv 没装 ultralytics |
| `ModuleNotFoundError: pycocotools` | 没装 pycocotools（`pip install -e ".[runtime-detection]"`） |
| mAP 接近 0 | 合成纯色图，YOLO 检测不到东西 → 用真实图片重跑 |
| mAP 0.3+ | 正常，YOLOv8n 在 COCO 上 mAP 约 0.37 |
