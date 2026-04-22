# Image Classification Demo — ViT Cats vs Dogs

端到端 demo：镜像 HF 上的 ViT Cats-vs-Dogs 到 ModelForge，配好 handler 和测试数据，演示 **Evaluate** 功能（image-classification task）。

## 0. 先决条件（部署机）

```bash
ssh chun@192.168.30.134
cd /home/chun/modelforge
.venv/bin/pip install transformers
.venv/bin/pip install -e ".[runtime-vision]"
systemctl --user restart modelforge.service
```

> torch 和 Pillow 应该已经装过了。

## 1. Mac 本地：镜像模型

```bash
export MODELFORGE_TOKEN=<your-token>
export MODELFORGE_URL=http://192.168.30.134:8000

pip install huggingface_hub
python examples/image-classification-demo/mirror.py
```

## 2. 生成测试数据

```bash
pip install datasets Pillow    # 如果还没装
python examples/image-classification-demo/make_dataset.py
# wrote 20 images -> .../cats_vs_dogs_test.zip
```

如果 `datasets` 装不上或 HF 拉不到数据，脚本会自动退回到生成纯色占位图（能跑通链路但 accuracy 无意义）。

## 3. 浏览器里跑评估

1. 打开 http://192.168.30.134:8000/nateraw/vit-base-cats-vs-dogs
2. 点 **Evaluate** tab
3. 拖入 `cats_vs_dogs_test.zip`
4. **Run evaluation**
5. 几秒后看到指标表：accuracy / precision_macro / recall_macro / f1_macro，primary = accuracy 高亮
6. 点 "View updated performance →" 回 Card tab

## handler 逻辑

`overlay/handler.py`：

- `transformers.AutoImageProcessor + AutoModelForImageClassification` 加载
- 逐张推理（batch=1），取 top-5 softmax
- evaluator 取 top-1 label 跟 ImageFolder 子目录名比对

## 排错

| 症状 | 原因 |
|---|---|
| `ModuleNotFoundError: transformers` | 部署机 venv 没装 transformers |
| `ModuleNotFoundError: PIL` | 没装 Pillow（`pip install -e ".[runtime-vision]"`） |
| accuracy 接近 0.5 | 合成占位图（纯色），模型无法区分 → 用真实猫狗图重跑 |
| accuracy 接近 1.0 | 正常，ViT fine-tuned on cats-vs-dogs 在真实图上表现很好 |
