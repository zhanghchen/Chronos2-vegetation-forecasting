# Builds the final comparison for the multi-pixel PFT-conditioning
# experiment: baseline (no PFT) vs. dominant vs. fractional, for both
# Experiment A (temporal holdout, all 70 pixels) and Experiment B (spatial
# holdout, 15 unseen pixels), plus the mixed-vs-pure / purity-vs-improvement
# analysis. Reads only outputs/pft_multipixel/ (new; does not touch
# outputs/zero_shot/, outputs/pft_ablation/, or any other experiment).
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import common_pipeline as cp
import pft_multipixel_dataset as pmd

OUTPUT_DIR = cp.OUTPUTS_ROOT / "pft_multipixel"
CONDITIONS = ["baseline", "dominant", "fractional"]
EXPERIMENTS = {"expA_temporal": "expA_all70", "expB_spatial": "expB_holdout15"}


def load_condition_metrics(tag, label):
    if tag == "baseline":
        df = pd.read_csv(OUTPUT_DIR / "baseline" / f"metrics_{label}.csv")
    else:
        exp_tag = "expA_temporal" if label == "expA_all70" else "expB_spatial"
        df = pd.read_csv(OUTPUT_DIR / exp_tag / tag / f"metrics_{label}.csv")
    df["condition"] = tag
    return df


def build_master_table(sel):
    rows = []
    for exp_tag, label in EXPERIMENTS.items():
        for condition in CONDITIONS:
            df = load_condition_metrics(condition, label)
            df["experiment"] = exp_tag
            rows.append(df)
    master = pd.concat(rows, ignore_index=True)
    master = master.merge(
        sel[["pixel_id", "dominant_pft", "pft_purity", "pft_entropy"]], on="pixel_id", how="left"
    )
    master.to_csv(OUTPUT_DIR / "pft_multipixel_all_metrics.csv", index=False)
    return master


def summary_table(master):
    rows = []
    for exp_tag in EXPERIMENTS:
        sub = master[master.experiment == exp_tag]
        for condition in CONDITIONS:
            c = sub[sub.condition == condition]
            rows.append({
                "Experiment": exp_tag, "PFT_representation": condition,
                "Mean_R2": c.R2.mean(), "Median_R2": c.R2.median(), "Std_R2": c.R2.std(),
                "Mean_RMSE": c.RMSE.mean(), "Mean_MAE": c.MAE.mean(), "Mean_Pearson_r": c.Pearson_r.mean(),
                "N_pixels": len(c),
            })
    table = pd.DataFrame(rows)
    baseline_r2 = table[table.PFT_representation == "baseline"].set_index("Experiment")["Mean_R2"]
    table["Delta_R2_vs_baseline"] = table.apply(
        lambda r: r["Mean_R2"] - baseline_r2[r["Experiment"]], axis=1
    )
    table.to_csv(OUTPUT_DIR / "summary_table.csv", index=False)
    print(table.to_string(index=False))
    return table


def per_pixel_pivot(master):
    piv = master.pivot_table(index=["pixel_id", "experiment", "dominant_pft", "pft_purity", "pft_entropy"],
                               columns="condition", values="R2").reset_index()
    piv["delta_fractional_vs_baseline"] = piv["fractional"] - piv["baseline"]
    piv["delta_dominant_vs_baseline"] = piv["dominant"] - piv["baseline"]
    piv["delta_fractional_vs_dominant"] = piv["fractional"] - piv["dominant"]
    piv.to_csv(OUTPUT_DIR / "per_pixel_r2_pivot.csv", index=False)
    return piv


def by_dominant_pft(piv):
    g = piv.groupby(["experiment", "dominant_pft"]).agg(
        n=("pixel_id", "size"),
        mean_delta_fractional=("delta_fractional_vs_baseline", "mean"),
        mean_delta_dominant=("delta_dominant_vs_baseline", "mean"),
    ).reset_index()
    g.to_csv(OUTPUT_DIR / "by_dominant_pft.csv", index=False)
    return g


def mixed_vs_pure(piv):
    corr_purity = piv["pft_purity"].corr(piv["delta_fractional_vs_dominant"])
    corr_entropy = piv["pft_entropy"].corr(piv["delta_fractional_vs_dominant"])
    summary = pd.DataFrame([{
        "correlation_purity_vs_frac_minus_dom_delta": corr_purity,
        "correlation_entropy_vs_frac_minus_dom_delta": corr_entropy,
        "n_pixels": len(piv),
    }])
    summary.to_csv(OUTPUT_DIR / "mixed_vs_pure_correlation.csv", index=False)
    print("\n=== Mixed vs. pure: does fractional's edge over dominant grow with mixture? ===")
    print(summary.to_string(index=False))

    fig, ax = plt.subplots(figsize=(8, 6), constrained_layout=True)
    for exp_tag, marker in zip(EXPERIMENTS, ["o", "^"]):
        sub = piv[piv.experiment == exp_tag]
        ax.scatter(sub["pft_entropy"], sub["delta_fractional_vs_dominant"], marker=marker,
                    label=exp_tag, alpha=0.7, s=50)
    ax.axhline(0, color="#999", linewidth=0.8)
    ax.set_xlabel("PFT entropy (higher = more mixed)")
    ax.set_ylabel("R²(fractional) - R²(dominant)")
    ax.set_title("Does fractional PFT's edge over dominant grow with mixture?", loc="left", fontsize=12)
    ax.legend(frameon=False)
    fig.savefig(OUTPUT_DIR / "mixed_vs_pure_scatter.png", dpi=150, facecolor="white")
    plt.close(fig)
    return summary


def plot_r2_summary(table):
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5), constrained_layout=True, sharey=True)
    for ax, exp_tag in zip(axes, EXPERIMENTS):
        sub = table[table.Experiment == exp_tag].set_index("PFT_representation").reindex(CONDITIONS)
        colors = ["#7a7a7a", "#a8791f", "#1f5c4a"]
        ax.bar(CONDITIONS, sub["Mean_R2"], color=colors)
        ax.set_title(exp_tag, loc="left", fontsize=12)
        ax.set_ylabel("Mean R² (test year 2022)")
    fig.suptitle("Multi-pixel PFT conditioning: mean R² by condition", fontsize=14, fontweight="bold")
    fig.savefig(OUTPUT_DIR / "r2_summary_by_experiment.png", dpi=150, facecolor="white")
    plt.close(fig)


def main():
    sel = pmd.load_selection_table()
    master = build_master_table(sel)
    table = summary_table(master)
    piv = per_pixel_pivot(master)
    by_dominant_pft(piv)
    mixed_vs_pure(piv)
    plot_r2_summary(table)
    print(f"\nSaved all comparison outputs to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
