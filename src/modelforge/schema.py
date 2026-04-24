"""Model Card 元数据 Schema（Hugging Face 规范兼容）。

每个仓库必须有 README.md，文件开头是 YAML frontmatter：

    ---
    license: mit
    library_name: lightgbm
    tags:
      - time-series-forecasting
    pipeline_tag: tabular-regression
    ---

    # Model Title
    Markdown body...

本模块负责：
1. 解析 YAML frontmatter
2. Pydantic 校验必填字段
3. 给出清晰的错误信息（用于服务端 hook 拒绝时显示给用户）
"""
from __future__ import annotations

from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError


class ModelCardMetadata(BaseModel):
    """Model Card YAML frontmatter 的结构化表达。

    字段命名与 HF 保持一致；额外字段允许（extra="allow"）。
    """

    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
        protected_namespaces=(),
    )

    # ===== 必填字段 =====
    license: str = Field(
        ...,
        description="SPDX 许可证标识，如 'mit'、'apache-2.0'",
        min_length=1,
    )
    library_name: str = Field(
        ...,
        description="客户端库名，如 'lightgbm'、'transformers'",
        min_length=1,
    )

    # ===== 推荐字段 =====
    tags: list[str] = Field(
        default_factory=list,
        description="模型标签，用于搜索和分类（HF 推荐但非强制）",
    )
    pipeline_tag: str | None = Field(
        None,
        description="任务类型，如 'text-classification'、'tabular-regression'",
    )
    language: str | list[str] | None = None
    datasets: list[str] | None = None
    metrics: list[str] | None = None
    base_model: str | None = None

    # model-index 是 HF 的结构化性能指标（YAML 键带连字符）
    model_index: list[dict] | None = Field(default=None, alias="model-index")


class DatasetCardMetadata(BaseModel):
    """Dataset Card YAML frontmatter。

    跟 ModelCardMetadata 共用 license，但不要求 library_name。
    """

    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
        protected_namespaces=(),
    )

    repo_type: Literal["dataset"]
    license: str = Field(
        ...,
        description="SPDX 许可证标识",
        min_length=1,
    )
    task_categories: list[str] = Field(default_factory=list)
    size_category: str | None = None
    data_format: str | None = Field(
        None,
        description="数据格式：csv | parquet | image_folder | coco_json",
    )
    tags: list[str] = Field(default_factory=list)


class ModelCardError(Exception):
    """README.md 解析或校验失败。message 设计为能直接展示给用户。"""


def parse_frontmatter(content: str) -> tuple[dict, str]:
    """从 README.md 中拆分 YAML frontmatter 和 Markdown body。

    返回 (metadata_dict, body_str)。
    没有 frontmatter 时抛 ModelCardError。
    """
    text = content.lstrip("\ufeff").lstrip()  # 去掉可能的 BOM + 开头空白
    if not text.startswith("---"):
        raise ModelCardError(
            "README.md 必须以 YAML frontmatter 开头（第一行是 '---'）。\n"
            "示例：\n"
            "---\n"
            "license: mit\n"
            "library_name: lightgbm\n"
            "tags:\n"
            "  - time-series\n"
            "---\n"
        )

    lines = text.split("\n")
    # 第一行是 '---'，找下一个 '---' 作为结束
    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break

    if end_idx is None:
        raise ModelCardError("README.md 的 YAML frontmatter 缺少结束的 '---'")

    yaml_block = "\n".join(lines[1:end_idx])
    try:
        data = yaml.safe_load(yaml_block) or {}
    except yaml.YAMLError as e:
        raise ModelCardError(f"README.md 的 YAML frontmatter 解析失败：{e}")

    if not isinstance(data, dict):
        raise ModelCardError(
            "README.md 的 YAML frontmatter 应是键值对（dict），"
            f"实际是 {type(data).__name__}"
        )

    body = "\n".join(lines[end_idx + 1:]).lstrip()
    return data, body


def validate_model_card(content: str) -> ModelCardMetadata | DatasetCardMetadata:
    """解析并校验 README.md。失败抛 ModelCardError 带友好信息。

    按 repo_type 分发：dataset 走 DatasetCardMetadata，其余走 ModelCardMetadata。
    """
    metadata_dict, _body = parse_frontmatter(content)
    repo_type = metadata_dict.get("repo_type", "model")

    cls = DatasetCardMetadata if repo_type == "dataset" else ModelCardMetadata
    try:
        return cls(**metadata_dict)
    except ValidationError as e:
        lines = ["README.md 的 YAML frontmatter 校验失败："]
        for err in e.errors():
            loc = ".".join(str(x) for x in err["loc"])
            msg = err["msg"]
            lines.append(f"  - 字段 '{loc}': {msg}")
        raise ModelCardError("\n".join(lines))
