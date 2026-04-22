"""Mirror YOLOv8n to local ModelForge.

YOLOv8n 权重不在 HF Hub 上（ultralytics 自己的 CDN），所以这里：
1. 用 ultralytics 下载 yolov8n.pt 到临时目录
2. 叠加 overlay（handler.py + README.md + .gitattributes）
3. ModelHub.upload_folder 推到 ModelForge
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).parent
OVERLAY = HERE / "overlay"

TARGET_REPO = "ultralytics/yolov8n"
DEFAULT_URL = "http://192.168.30.134:8000"


def main() -> None:
    try:
        from ultralytics import YOLO
    except ImportError:
        sys.exit("缺少 ultralytics，执行：pip install ultralytics")

    repo_root = HERE.parent.parent
    sys.path.insert(0, str(repo_root / "src"))
    from modelforge.client import ModelHub

    url = os.environ.get("MODELFORGE_URL", DEFAULT_URL)
    token = os.environ.get("MODELFORGE_TOKEN")
    if not token:
        sys.exit("请先设置 MODELFORGE_TOKEN 环境变量")

    stage = Path("/tmp/mf-yolo-stage")
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir()

    print("[1/3] 下载 YOLOv8n 权重")
    model = YOLO("yolov8n.pt")
    src_pt = Path(model.ckpt_path)
    shutil.copy2(src_pt, stage / "yolov8n.pt")
    print(f"  done: {src_pt} -> {stage / 'yolov8n.pt'}")

    print(f"[2/3] 叠加 overlay {OVERLAY} -> {stage}")
    for p in OVERLAY.rglob("*"):
        if p.is_file():
            rel = p.relative_to(OVERLAY)
            dst = stage / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dst)
            print(f"  + {rel}")

    print(f"[3/3] 上传到 {url}/{TARGET_REPO}")
    hub = ModelHub(url, token=token, cache_dir="/tmp/mf-publish-cache")
    hub.upload_folder(
        repo=TARGET_REPO,
        folder_path=stage,
        commit_message="mirror: ultralytics/yolov8n + evaluator handler",
    )
    print(f"OK → {url}/{TARGET_REPO}")


if __name__ == "__main__":
    main()
