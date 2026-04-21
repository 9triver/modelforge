"""image-classification 标准评估数据 loader（ImageFolder 风格）。

数据目录结构：
  root/
    class_a/ img1.jpg img2.png ...
    class_b/ ...

iter_image_folder() 惰性产出 (PIL.Image, label)，适合大数据集流式评估。
load_image_folder() 一次性读入内存，小数据集方便。

支持从 ZIP 自动解压（runner 收到上传后调用 unpack_zip）。

依赖 Pillow（来自 runtime-vision extras）。
"""
from __future__ import annotations

import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PIL.Image import Image


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff", ".tif"}


class DatasetError(ValueError):
    """数据格式错误，message 面向终端用户。"""


def unpack_zip(zip_path: str | Path, extract_to: str | Path) -> Path:
    """解压 ZIP 到 extract_to，返回解压后的根目录（若 ZIP 内单层包一层目录，返回那层）。"""
    zip_p = Path(zip_path)
    dest = Path(extract_to)
    dest.mkdir(parents=True, exist_ok=True)

    if not zipfile.is_zipfile(zip_p):
        raise DatasetError(f"不是合法的 ZIP 文件：{zip_p}")

    with zipfile.ZipFile(zip_p) as zf:
        # 防 zip-slip：每个成员目标路径必须在 dest 内
        for m in zf.infolist():
            target = (dest / m.filename).resolve()
            if not str(target).startswith(str(dest.resolve())):
                raise DatasetError(f"ZIP 含非法路径（zip-slip）：{m.filename}")
        zf.extractall(dest)

    # 若解压后只有一个顶层目录，下钻一层
    entries = [p for p in dest.iterdir() if not p.name.startswith(".")]
    if len(entries) == 1 and entries[0].is_dir():
        return entries[0]
    return dest


def iter_image_folder(root: str | Path) -> Iterator[tuple["Image", str]]:
    """遍历 ImageFolder 结构，惰性产出 (PIL.Image, class_name)。"""
    from PIL import Image as PILImage

    root_p = Path(root)
    if not root_p.is_dir():
        raise DatasetError(f"数据根目录不存在：{root_p}")

    class_dirs = sorted(p for p in root_p.iterdir() if p.is_dir())
    if not class_dirs:
        raise DatasetError(f"{root_p} 下没有类别子目录（期望 ImageFolder 结构）")

    found = 0
    for cls_dir in class_dirs:
        for img_path in sorted(cls_dir.iterdir()):
            if img_path.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            try:
                img = PILImage.open(img_path).convert("RGB")
            except Exception as e:
                raise DatasetError(f"无法读取图片 {img_path}：{e}")
            found += 1
            yield img, cls_dir.name

    if found == 0:
        raise DatasetError(f"{root_p} 下没有找到任何图片")


def load_image_folder(root: str | Path) -> tuple[list["Image"], list[str]]:
    """一次性读入 ImageFolder，返回 (images, labels)。"""
    images: list[Image] = []  # noqa: F821 — TYPE_CHECKING 别名足够
    labels: list[str] = []
    for img, label in iter_image_folder(root):
        images.append(img)
        labels.append(label)
    return images, labels
