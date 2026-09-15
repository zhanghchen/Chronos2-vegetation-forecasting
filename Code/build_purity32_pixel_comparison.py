# Builds the summary figures for the 32-pixel "pure and diverse" zero-shot
# Chronos-2 generalization study (see CHRONOS2_PURITY32_REPORT.md). Reads
# outputs/purity32_pixel_study/zero_shot_32pixels.csv (already-verified
# per-pixel metrics: 3 already-published core pixels + 29 newly-run pixels,
# all zero-shot, all scored against raw observed LAI) -- no new experiments,
# only new visualizations of already-saved results.
from pathlib import Path

import matplotlib
matplotlib.use("AGG")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import plotting_utils as pu

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "outputs" / "purity32_pixel_study"

CLASS_COLORS = {
    "TREES_NE": "#1B7837", "TREES_BD": "#5AAE61", "TREES_ND": "#A6DBA0",
    "SHRUBS_NE": "#B35806", "SHRUBS_BD": "#E08214", "SHRUBS_ND": "#FDB863",
    "GRASS_NAT": "#762A83", "GRASS_MAN": "#C2A5CF",
}


def main():
    df = pd.read_csv(OUT_DIR / "zero_shot_32pixels.csv").sort_values("R2", ascending=False).reset_index(drop=True)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6), constrained_layout=True,
                                    gridspec_kw={"width_ratios": [1.6, 1]})

    colors = [CLASS_COLORS.get(c, "#888888") for c in df["dominant_pft"]]
    ax1.bar(range(len(df)), df["R2"], color=colors, edgecolor="black", linewidth=0.3)
    ax1.axhline(0, color="black", lw=0.8)
    ax1.axhline(df["R2"].median(), color=pu.ZERO_SHOT_COLOR, lw=1.2, ls="--", label=f"median = {df['R2'].median():.3f}")
    ax1.set_xticks(range(len(df)))
    ax1.set_xticklabels(df["site"], rotation=90, fontsize=6.5)
    ax1.set_ylabel("Zero-shot Chronos-2 $R^2$ (vs. raw observed LAI)")
    ax1.set_title("(a) All 32 pixels, sorted by $R^2$", loc="left")
    ax1.legend(frameon=False, fontsize=9)
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in CLASS_COLORS.values()]
    ax1.legend(handles + [plt.Line2D([0], [0], color=pu.ZERO_SHOT_COLOR, ls="--")],
               list(CLASS_COLORS.keys()) + [f"median={df['R2'].median():.3f}"],
               frameon=False, fontsize=7, loc="lower left", ncol=2)

    order = df.groupby("dominant_pft")["R2"].median().sort_values(ascending=False).index
    data = [df[df["dominant_pft"] == c]["R2"].values for c in order]
    bp = ax2.boxplot(data, tick_labels=order, patch_artist=True, showmeans=True)
    for patch, c in zip(bp["boxes"], order):
        patch.set_facecolor(CLASS_COLORS.get(c, "#888888"))
        patch.set_alpha(0.7)
    ax2.axhline(0, color="black", lw=0.8)
    ax2.set_xticklabels(order, rotation=45, ha="right", fontsize=8)
    ax2.set_ylabel("$R^2$")
    ax2.set_title("(b) By dominant vegetation class", loc="left")

    pu.save_fig(fig, OUT_DIR, "r2_by_pixel_and_class")
    print("Saved figures to", OUT_DIR)

    # summary table
    overall = df[["RMSE", "MAE", "MAPE", "R2", "Pearson_r"]].agg(["mean", "median", "std", "min", "max"])
    overall.to_csv(OUT_DIR / "summary_overall.csv")
    by_class = df.groupby("dominant_pft")["R2"].agg(["count", "mean", "median", "std", "min", "max"]).sort_values("mean", ascending=False)
    by_class.to_csv(OUT_DIR / "summary_by_class.csv")
    print(overall)
    print(by_class)


if __name__ == "__main__":
    main()
