# Builds the final PFT-ablation comparison for Chronos-2 zero-shot:
# baseline vs. +fractional-PFT vs. +dominant-PFT, across the 4 pixels, plus
# the mixed-vs-pure read and a plot. Reads outputs/pft_ablation/ (new,
# separate from outputs/zero_shot/, outputs/finetuned_lora/,
# outputs/finetuned_lora_improved/, outputs/advanced_finetuning/ - none of
# which are touched).
from pathlib import Path

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import common_pipeline as cp

OUTPUT_DIR = cp.OUTPUTS_ROOT / "pft_ablation"
SITES = ["evergreen", "low_amplitude", "high_amplitude_deciduous", "mixed_forest_grass"]
SITE_PFT_LABEL = {
    "evergreen": "95% TREES_NE (near-pure)",
    "low_amplitude": "84% GRASS_NAT / 16% TREES_NE (near-pure)",
    "high_amplitude_deciduous": "89% TREES_BD (near-pure)",
    "mixed_forest_grass": "50% TREES_BD / 50% GRASS_NAT (mixed)",
}
IS_MIXED = {"evergreen": False, "low_amplitude": False, "high_amplitude_deciduous": False, "mixed_forest_grass": True}


def build_table():
    df = pd.read_csv(OUTPUT_DIR / "pft_ablation_all_results.csv")
    rows = []
    for site in SITES:
        sub = df[df.site == site].set_index("condition")
        rows.append({
            "Site": site, "PFT_composition": SITE_PFT_LABEL[site], "Mixed_pixel": IS_MIXED[site],
            "Baseline_R2": sub.loc["baseline", "R2"], "Fractional_R2": sub.loc["fractional", "R2"],
            "Dominant_R2": sub.loc["dominant", "R2"],
            "Delta_R2_fractional": sub.loc["fractional", "R2"] - sub.loc["baseline", "R2"],
            "Delta_R2_dominant": sub.loc["dominant", "R2"] - sub.loc["baseline", "R2"],
            "Delta_R2_fractional_minus_dominant": sub.loc["fractional", "R2"] - sub.loc["dominant", "R2"],
            "Baseline_RMSE": sub.loc["baseline", "RMSE"], "Fractional_RMSE": sub.loc["fractional", "RMSE"],
            "Dominant_RMSE": sub.loc["dominant", "RMSE"],
        })
    table = pd.DataFrame(rows)
    table.to_csv(OUTPUT_DIR / "pft_ablation_comparison_table.csv", index=False)
    print(table.to_string(index=False))
    return table


def plot_r2(table):
    fig, ax = plt.subplots(figsize=(9, 5.5), constrained_layout=True)
    x = range(len(SITES))
    w = 0.26
    ax.bar([i - w for i in x], table["Baseline_R2"], width=w, label="Baseline", color="#7a7a7a")
    ax.bar(list(x), table["Fractional_R2"], width=w, label="+Fractional PFT", color="#1f5c4a")
    ax.bar([i + w for i in x], table["Dominant_R2"], width=w, label="+Dominant PFT", color="#a8791f")
    ax.set_xticks(list(x))
    ax.set_xticklabels(SITES, rotation=15, ha="right")
    ax.set_ylabel("R² (test year 2022, zero-shot)")
    ax.set_title("Chronos-2 zero-shot: PFT ablation across 4 pixels", loc="left", fontsize=13)
    ax.legend(frameon=False)
    fig.savefig(OUTPUT_DIR / "pft_ablation_r2_by_pixel.png", dpi=150, facecolor="white")
    plt.close(fig)


def plot_predictions(site):
    fig, ax = plt.subplots(figsize=(11, 5), constrained_layout=True)
    colors = {"baseline": "#7a7a7a", "fractional": "#1f5c4a", "dominant": "#a8791f"}
    for condition in ["baseline", "fractional", "dominant"]:
        preds = pd.read_csv(OUTPUT_DIR / site / condition / "predictions.csv", parse_dates=["date"])
        if condition == "baseline":
            ax.plot(preds.date, preds.ground_truth, color="black", linewidth=2.4, label="Observed", zorder=10)
        ax.plot(preds.date, preds.prediction, color=colors[condition], linewidth=1.8,
                 label=condition, marker="o", markersize=3)
    ax.set_title(f"{site} — Chronos-2 zero-shot, 2022 ({SITE_PFT_LABEL[site]})", loc="left", fontsize=12)
    ax.set_ylabel("LAI")
    ax.tick_params(axis="x", rotation=20)
    ax.legend(frameon=False, fontsize=9)
    fig.savefig(OUTPUT_DIR / f"prediction_plot_{site}.png", dpi=150, facecolor="white")
    plt.close(fig)


def main():
    table = build_table()
    plot_r2(table)
    for site in SITES:
        plot_predictions(site)
    print(f"\nSaved comparison table + figures to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
