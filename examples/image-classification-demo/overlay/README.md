---
license: apache-2.0
library_name: transformers
pipeline_tag: image-classification
base_model: google/vit-base-patch16-224
tags:
  - image-classification
  - vit
  - cats-vs-dogs
---

# ViT Base — Cats vs Dogs (ModelForge mirror)

Mirror of [nateraw/vit-base-cats-vs-dogs](https://huggingface.co/nateraw/vit-base-cats-vs-dogs)，
fine-tuned on Cats vs Dogs，输出两类标签：`cat` / `dog`。

## 评估数据格式

ZIP，**ImageFolder** 风格：

```
data.zip
└── data/
    ├── cat/
    │   ├── 0.jpg
    │   ├── 1.jpg
    │   └── ...
    └── dog/
        ├── 0.jpg
        └── ...
```

子目录名 = 真实标签；ModelForge evaluator 把每张图喂给 handler，取 top-1 跟子目录名比对，算 accuracy / precision_macro / recall_macro / f1_macro。

## 依赖

部署机 venv：

```
transformers>=4.40
torch
Pillow
```

## 来源

- 原始权重：https://huggingface.co/nateraw/vit-base-cats-vs-dogs
- Backbone：[google/vit-base-patch16-224](https://huggingface.co/google/vit-base-patch16-224)
