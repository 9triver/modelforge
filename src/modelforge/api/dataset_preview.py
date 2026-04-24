"""Dataset 预览 API：CSV 前 N 行 + ImageFolder 缩略图。

GET /api/v1/repos/{ns}/{name}/preview-csv?path=data.csv&limit=100
GET /api/v1/repos/{ns}/{name}/preview-images?limit=20
"""
from __future__ import annotations

import base64
import csv
import io
import subprocess
from collections import defaultdict

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from .. import repo_reader, storage

router = APIRouter(prefix="/api/v1", tags=["dataset-preview"])

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff"}


class CsvPreviewResponse(BaseModel):
    columns: list[str]
    rows: list[list[str]]
    total_rows: int


@router.get(
    "/repos/{namespace}/{name}/preview-csv",
    response_model=CsvPreviewResponse,
)
def preview_csv(
    namespace: str,
    name: str,
    path: str = Query(..., description="CSV 文件路径"),
    revision: str = Query("main"),
    limit: int = Query(100, ge=1, le=1000),
):
    content = repo_reader.read_file(namespace, name, revision, path)
    if content is None:
        raise HTTPException(404, f"文件 '{path}' 不存在")

    reader = csv.reader(io.StringIO(content))
    rows_all = list(reader)
    if not rows_all:
        return CsvPreviewResponse(columns=[], rows=[], total_rows=0)

    columns = rows_all[0]
    data_rows = rows_all[1:]
    return CsvPreviewResponse(
        columns=columns,
        rows=data_rows[:limit],
        total_rows=len(data_rows),
    )


class ImageSample(BaseModel):
    path: str
    thumbnail_b64: str


class ImageClass(BaseModel):
    name: str
    count: int
    samples: list[ImageSample]


class ImagePreviewResponse(BaseModel):
    classes: list[ImageClass]


def _read_blob_bytes(namespace: str, name: str, revision: str, path: str) -> bytes | None:
    bare = storage.repo_path(namespace, name)
    try:
        result = subprocess.run(
            ["git", f"--git-dir={bare}", "show", f"{revision}:{path}"],
            capture_output=True,
        )
        return result.stdout if result.returncode == 0 else None
    except Exception:
        return None


def _make_thumbnail(data: bytes, size: int = 128) -> str | None:
    try:
        from PIL import Image as PILImage
        img = PILImage.open(io.BytesIO(data))
        img.thumbnail((size, size))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=75)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return None


@router.get(
    "/repos/{namespace}/{name}/preview-images",
    response_model=ImagePreviewResponse,
)
def preview_images(
    namespace: str,
    name: str,
    revision: str = Query("main"),
    limit: int = Query(20, ge=1, le=50),
):
    files = repo_reader.list_files(namespace, name, revision)
    by_class: dict[str, list[str]] = defaultdict(list)
    for f in files:
        parts = f.path.split("/")
        if len(parts) < 2:
            continue
        ext = "." + parts[-1].rsplit(".", 1)[-1].lower() if "." in parts[-1] else ""
        if ext not in IMAGE_EXTS:
            continue
        class_name = parts[-2]
        by_class[class_name].append(f.path)

    if not by_class:
        raise HTTPException(404, "未找到 ImageFolder 结构的图片文件")

    per_class = max(1, limit // len(by_class))
    classes: list[ImageClass] = []
    for cls_name in sorted(by_class):
        paths = by_class[cls_name]
        samples: list[ImageSample] = []
        for p in paths[:per_class]:
            blob = _read_blob_bytes(namespace, name, revision, p)
            if blob is None:
                continue
            thumb = _make_thumbnail(blob)
            if thumb:
                samples.append(ImageSample(path=p, thumbnail_b64=thumb))
        classes.append(ImageClass(name=cls_name, count=len(paths), samples=samples))

    return ImagePreviewResponse(classes=classes)
