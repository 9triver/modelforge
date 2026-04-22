"""Mirror nateraw/vit-base-cats-vs-dogs from HuggingFace to local ModelForge.

跟 chronos demo 同结构：snapshot_download → 叠 overlay → ModelHub.upload_folder。
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).parent
OVERLAY = HERE / "overlay"

HF_REPO = "nateraw/vit-base-cats-vs-dogs"
TARGET_REPO = "nateraw/vit-base-cats-vs-dogs"
DEFAULT_URL = "http://192.168.30.134:8000"


def main() -> None:
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        sys.exit("缺少 huggingface_hub，执行：pip install huggingface_hub")

    repo_root = HERE.parent.parent
    sys.path.insert(0, str(repo_root / "src"))
    from modelforge.client import ModelHub

    url = os.environ.get("MODELFORGE_URL", DEFAULT_URL)
    token = os.environ.get("MODELFORGE_TOKEN")
    if not token:
        sys.exit("请先设置 MODELFORGE_TOKEN 环境变量")

    cache = Path("/tmp/mf-vit-mirror-cache")
    cache.mkdir(parents=True, exist_ok=True)
    print(f"[1/3] 下载 {HF_REPO} 到 {cache}")
    hf_dir = Path(snapshot_download(
        repo_id=HF_REPO,
        cache_dir=cache,
        local_dir=cache / "hf",
    ))
    print(f"  done: {hf_dir}")

    stage = Path("/tmp/mf-vit-stage")
    if stage.exists():
        shutil.rmtree(stage)
    shutil.copytree(hf_dir, stage)

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
        commit_message="mirror: nateraw/vit-base-cats-vs-dogs + evaluator handler",
    )
    print(f"OK → {url}/{TARGET_REPO}")


if __name__ == "__main__":
    main()
