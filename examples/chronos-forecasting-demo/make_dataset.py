"""生成合成小时级负荷曲线 CSV，用来测 ModelForge 的 evaluate 功能。

结构：
  - daily  季节性：cos(2π·t/24)
  - weekly 季节性：sin(2π·t/168)
  - trend  轻微上升
  - noise  高斯噪声

输出：
  ./synthetic_load.csv  (timestamp, load)  默认 14 天 * 24 小时 = 336 行

用法：
  python examples/chronos-forecasting-demo/make_dataset.py
  python examples/chronos-forecasting-demo/make_dataset.py --hours 720 --seed 7 -o big.csv
"""
from __future__ import annotations

import argparse
import math
import random
from datetime import datetime, timedelta
from pathlib import Path


def generate(hours: int, seed: int) -> list[tuple[str, float]]:
    random.seed(seed)
    start = datetime(2024, 1, 1, 0, 0, 0)
    rows: list[tuple[str, float]] = []
    for t in range(hours):
        daily = 20 * math.cos(2 * math.pi * (t % 24) / 24 - math.pi)       # 低谷夜间
        weekly = 10 * math.sin(2 * math.pi * t / 168)
        trend = 0.01 * t
        noise = random.gauss(0, 2.5)
        load = 80 + daily + weekly + trend + noise
        ts = (start + timedelta(hours=t)).strftime("%Y-%m-%d %H:%M:%S")
        rows.append((ts, round(load, 3)))
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=336, help="总小时数（默认 14 天）")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("-o", "--output", default="synthetic_load.csv")
    args = ap.parse_args()

    rows = generate(args.hours, args.seed)
    out = Path(args.output)
    with out.open("w") as f:
        f.write("timestamp,load\n")
        for ts, v in rows:
            f.write(f"{ts},{v}\n")
    print(f"wrote {len(rows)} rows -> {out.resolve()}")


if __name__ == "__main__":
    main()
