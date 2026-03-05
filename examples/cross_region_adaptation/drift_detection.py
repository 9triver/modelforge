"""Data distribution drift detection between East and North China.

Implements PSI (Population Stability Index) and KS (Kolmogorov-Smirnov) tests
for each shared feature to quantify distribution shift.

PSI interpretation:
  < 0.1:  No significant shift
  0.1-0.25: Moderate shift — monitor closely
  > 0.25: Significant shift — model likely needs adaptation

Usage:
  python drift_detection.py \\
      --reference hua_dong_train.csv \\
      --target hua_bei_train.csv \\
      --features temperature,hour,day_of_week,is_weekend,month
"""

import argparse
import json

import numpy as np
import pandas as pd
from scipy import stats


def compute_psi(reference: np.ndarray, target: np.ndarray, bins: int = 10) -> float:
    """Population Stability Index between two distributions."""
    breakpoints = np.percentile(reference, np.linspace(0, 100, bins + 1))
    breakpoints = np.unique(breakpoints)

    ref_counts = np.histogram(reference, bins=breakpoints)[0]
    tgt_counts = np.histogram(target, bins=breakpoints)[0]

    eps = 1e-6
    ref_pct = ref_counts / len(reference) + eps
    tgt_pct = tgt_counts / len(target) + eps

    return float(np.sum((tgt_pct - ref_pct) * np.log(tgt_pct / ref_pct)))


def compute_ks(reference: np.ndarray, target: np.ndarray) -> dict:
    """Kolmogorov-Smirnov test between two distributions."""
    stat, p_value = stats.ks_2samp(reference, target)
    return {
        "statistic": round(float(stat), 4),
        "p_value": float(p_value),
        "significant": p_value < 0.05,
    }


def analyze_drift(ref_df: pd.DataFrame, tgt_df: pd.DataFrame,
                  features: list[str]) -> dict:
    """Run PSI and KS tests on shared features."""
    shared = [f for f in features if f in ref_df.columns and f in tgt_df.columns]
    not_shared = [f for f in features if f not in ref_df.columns or f not in tgt_df.columns]

    if not_shared:
        print(f"[警告] 以下特征不在两个数据集中共享: {not_shared}")

    results = {"features": [], "summary": {}}
    n_significant = 0

    for feat in shared:
        ref = ref_df[feat].dropna().values.astype(float)
        tgt = tgt_df[feat].dropna().values.astype(float)
        psi = compute_psi(ref, tgt)
        ks = compute_ks(ref, tgt)

        severity = "none" if psi < 0.1 else "moderate" if psi < 0.25 else "significant"
        if severity == "significant":
            n_significant += 1

        results["features"].append({
            "name": feat,
            "psi": round(psi, 4),
            "psi_severity": severity,
            "ks_statistic": ks["statistic"],
            "ks_p_value": ks["p_value"],
            "ks_significant": ks["significant"],
            "ref_mean": round(float(np.mean(ref)), 2),
            "tgt_mean": round(float(np.mean(tgt)), 2),
            "ref_std": round(float(np.std(ref)), 2),
            "tgt_std": round(float(np.std(tgt)), 2),
        })

    results["summary"] = {
        "features_analyzed": len(shared),
        "significant_drift": n_significant,
        "recommendation": (
            "显著分布偏移: 建议使用目标域数据重新训练或微调模型"
            if n_significant > 0
            else "分布基本一致: 可直接应用模型"
        ),
    }
    return results


def main():
    p = argparse.ArgumentParser(description="Distribution drift detection (PSI/KS)")
    p.add_argument("--reference", required=True, help="Reference (source domain) CSV")
    p.add_argument("--target", required=True, help="Target (new domain) CSV")
    p.add_argument("--features", required=True,
                   help="Comma-separated list of features to analyze")
    p.add_argument("--output", default="drift_report.json")
    args = p.parse_args()

    ref_df = pd.read_csv(args.reference)
    tgt_df = pd.read_csv(args.target)
    features = [f.strip() for f in args.features.split(",")]

    print("=" * 60)
    print("Distribution Drift Detection")
    print("=" * 60)
    print(f"Reference: {args.reference} ({len(ref_df)} rows)")
    print(f"Target:    {args.target} ({len(tgt_df)} rows)")
    print(f"Features:  {features}\n")

    report = analyze_drift(ref_df, tgt_df, features)

    for feat in report["features"]:
        indicator = {"none": "✓", "moderate": "△", "significant": "✗"}[feat["psi_severity"]]
        print(f"  {indicator} {feat['name']:20s}  PSI={feat['psi']:.4f} ({feat['psi_severity']:11s})  "
              f"KS={feat['ks_statistic']:.4f}  "
              f"ref={feat['ref_mean']:.1f}±{feat['ref_std']:.1f}  "
              f"tgt={feat['tgt_mean']:.1f}±{feat['tgt_std']:.1f}")

    s = report["summary"]
    print(f"\n结论: {s['features_analyzed']} 特征分析, "
          f"{s['significant_drift']} 个显著漂移")
    print(f"建议: {s['recommendation']}")

    with open(args.output, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n报告已保存: {args.output}")

    return report


if __name__ == "__main__":
    main()
