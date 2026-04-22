"""容器沙箱 entrypoint。

docker run 时执行 ``python -m modelforge.runtime.sandbox_entry``：
  1. 读 /input/manifest.json（模式 + 路径 + metadata）
  2. 调 evaluate() 或 calibrate_by_method()
  3. 结果写 /output/result.json
"""
from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path


def main(
    manifest_path: str = "/input/manifest.json",
    output_path: str = "/output/result.json",
) -> None:
    manifest = json.loads(Path(manifest_path).read_text())
    mode = manifest.get("mode", "evaluate")

    from modelforge.schema import ModelCardMetadata

    metadata = ModelCardMetadata(**manifest["metadata"])

    if mode == "evaluate":
        from modelforge.runtime.evaluator import evaluate

        result = evaluate(
            manifest["model_dir"],
            manifest["dataset_path"],
            metadata,
        )
    elif mode == "calibrate":
        from modelforge.runtime.calibration import calibrate_by_method
        from modelforge.runtime.datasets import forecasting as fc_ds
        from modelforge.runtime.evaluator import load_handler

        target_col = manifest["target_col"]
        handler = load_handler(manifest["model_dir"], "time-series-forecasting")
        handler.warmup()
        df = fc_ds.load_forecasting_csv(
            manifest["dataset_path"], target_col=target_col,
        )
        result = calibrate_by_method(
            manifest["calibrate_method"], handler, df, target_col,
        )
    else:
        print(f"unknown mode: {mode}", file=sys.stderr)
        sys.exit(1)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(dataclasses.asdict(result), default=str))


if __name__ == "__main__":
    main()
