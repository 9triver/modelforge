"""生成合成负荷 CSV 数据集并上传到 ModelForge。

生成 30 天 hourly 负荷数据（720 行），作为 dataset 仓库托管。
之后在 model 的 Evaluate / Calibrate tab 可以直接引用，不用每次上传。

用法：
  # 仅生成 CSV
  python examples/dataset-demo/make_csv_dataset.py

  # 生成并上传到 ModelForge
  python examples/dataset-demo/make_csv_dataset.py --upload chun/synthetic-load-30d

  # 自定义参数
  python examples/dataset-demo/make_csv_dataset.py --days 7 --seed 7 -o short.csv
"""
from __future__ import annotations

import argparse
import math
import random
from datetime import datetime, timedelta
from pathlib import Path


def generate(days: int, seed: int) -> list[tuple[str, float]]:
    random.seed(seed)
    hours = days * 24
    start = datetime(2024, 1, 1, 0, 0, 0)
    rows: list[tuple[str, float]] = []
    for t in range(hours):
        daily = 20 * math.cos(2 * math.pi * (t % 24) / 24 - math.pi)
        weekly = 10 * math.sin(2 * math.pi * t / 168)
        trend = 0.01 * t
        noise = random.gauss(0, 2.5)
        load = 80 + daily + weekly + trend + noise
        ts = (start + timedelta(hours=t)).strftime("%Y-%m-%d %H:%M:%S")
        rows.append((ts, round(load, 3)))
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30, help="天数（默认 30）")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("-o", "--output", default="synthetic_load_30d.csv")
    ap.add_argument(
        "--upload", metavar="REPO",
        help="上传到 ModelForge（如 chun/synthetic-load-30d）",
    )
    ap.add_argument("--endpoint", default=None, help="ModelForge URL")
    ap.add_argument("--token", default=None, help="ModelForge Token")
    args = ap.parse_args()

    rows = generate(args.days, args.seed)
    out = Path(args.output)
    with out.open("w") as f:
        f.write("timestamp,load\n")
        for ts, v in rows:
            f.write(f"{ts},{v}\n")
    print(f"wrote {len(rows)} rows -> {out.resolve()}")

    if args.upload:
        import os
        import shutil
        import sys
        import tempfile

        here = Path(__file__).parent
        repo_root = here.parent.parent
        sys.path.insert(0, str(repo_root / "src"))
        from modelforge.client import ModelHub

        ep = args.endpoint or os.environ.get("MODELFORGE_URL", "http://192.168.30.134:8000")
        tk = args.token or os.environ.get("MODELFORGE_TOKEN")
        if not tk:
            sys.exit("请设置 MODELFORGE_TOKEN 环境变量")

        staging = Path(tempfile.mkdtemp(prefix="mf_ds_csv_"))
        try:
            readme = (
                "---\n"
                "repo_type: dataset\n"
                "license: mit\n"
                "data_format: csv\n"
                "task_categories:\n"
                "  - time-series-forecasting\n"
                "tags:\n"
                "  - synthetic\n"
                "  - load-forecasting\n"
                f"size_category: \"{len(rows)}\"\n"
                "---\n"
                f"# {args.upload}\n\n"
                f"合成负荷数据（{args.days} 天 hourly，{len(rows)} 行）。\n"
                "用于 Evaluate / Calibrate 测试。\n"
            )
            (staging / "README.md").write_text(readme, encoding="utf-8")
            shutil.copy2(out, staging / out.name)

            hub = ModelHub(ep, token=tk)
            sha = hub.upload_folder(
                args.upload, staging,
                f"Upload synthetic load dataset ({args.days}d, {len(rows)} rows)",
            )
            print(f"uploaded -> {ep}/{args.upload} ({sha[:8]})")
        finally:
            shutil.rmtree(staging, ignore_errors=True)


if __name__ == "__main__":
    main()
