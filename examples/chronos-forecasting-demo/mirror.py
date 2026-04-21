"""Mirror amazon/chronos-t5-tiny from HuggingFace to local ModelForge.

Workflow:
  1. snapshot_download HF 原仓库到 /tmp
  2. 叠加 examples/chronos-forecasting-demo/overlay/ 里的 handler.py、README.md、.gitattributes
  3. ModelHub.upload_folder 推到 ModelForge（自动建 repo + LFS + push）

Env:
  MODELFORGE_URL   默认 http://192.168.30.134:8000
  MODELFORGE_TOKEN 必填（到目标 ModelForge 建 token；内网部署 token 可临时 disabled 但 create_repo 仍需 user）

用法：
  MODELFORGE_TOKEN=xxx python examples/chronos-forecasting-demo/mirror.py
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).parent
OVERLAY = HERE / "overlay"

HF_REPO = "amazon/chronos-t5-tiny"
TARGET_REPO = "amazon/chronos-t5-tiny"   # namespace/name on ModelForge
DEFAULT_URL = "http://192.168.30.134:8000"


def main() -> None:
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        sys.exit(
            "缺少 huggingface_hub，执行：pip install huggingface_hub"
        )

    # 把 modelforge SDK 加到 sys.path（假定脚本从仓库根目录或相对路径跑）
    repo_root = HERE.parent.parent   # vendor/modelforge/
    sys.path.insert(0, str(repo_root / "src"))
    from modelforge.client import ModelHub   # type: ignore

    url = os.environ.get("MODELFORGE_URL", DEFAULT_URL)
    token = os.environ.get("MODELFORGE_TOKEN")
    if not token:
        sys.exit("请先设置 MODELFORGE_TOKEN 环境变量")

    cache = Path("/tmp/mf-chronos-mirror-cache")
    cache.mkdir(parents=True, exist_ok=True)
    print(f"[1/3] 下载 {HF_REPO} 到 {cache}")
    hf_dir = Path(snapshot_download(
        repo_id=HF_REPO,
        cache_dir=cache,
        local_dir=cache / "hf",
    ))
    print(f"  done: {hf_dir}")

    # 合成发布目录：HF 原文件 + overlay
    stage = Path("/tmp/mf-chronos-stage")
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
        folder=stage,
        repo=TARGET_REPO,
        commit_message="mirror: amazon/chronos-t5-tiny + evaluator handler",
    )
    print(f"OK → {url}/{TARGET_REPO}")


if __name__ == "__main__":
    main()
