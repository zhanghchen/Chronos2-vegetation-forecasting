# Exploratory subgroup analysis for the global (non-CONUS) LOYO-CV pool:
# full pool (n=68, the primary result) vs. a performance-selected
# "top-performing subset" (n=20, selection rule: highest per-pixel mean
# LOYO-CV R² across the 11 held-out years 2012-2022).
#
# This is EXPLICITLY an illustrative/exploratory comparison, not a second
# estimate of "the" global result - the subset is selected BY the outcome
# metric itself, so its statistics are conditional on that selection and
# say nothing about the full pool's typical performance. Both figures and
# every printed number below carry that framing; the full-pool statistics
# remain the primary, reported result throughout this project's other
# reports (ERA5_GLOBAL70_REPORT.md, the LOYO-CV deck).
from pathlib import Path

import matplotlib
matplotlib.use("AGG")
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path("/home/deh25003/chronos-forecasting/Chronos2-vegetation-forecasting")
LOYO_SUMMARY = ROOT / "outputs/loyo_cv_pools_summary"
OUT_DIR = LOYO_SUMMARY
N_SUBSET = 20

FULL_COLOR = "#8C1D40"
SUBSET_COLOR = "#D4A017"


def main():
    pp = pd.read_csv(LOYO_SUMMARY / "loyo_global68_per_pixel_summary.csv")
    subset = pp.sort_values("mean", ascending=False).head(N_SUBSET)
    subset.to_csv(OUT_DIR / f"loyo_global_top{N_SUBSET}_subset.csv", index=False)

    rows = [
        {"group": f"Full global pool (n={len(pp)}) — PRIMARY RESULT",
         "mean_R2": pp["mean"].mean(), "median_R2": pp["median"].median(),
         "avg_variance": pp["var"].mean(), "median_variance": pp["var"].median()},
        {"group": f"Top-{N_SUBSET} by mean R2 — EXPLORATORY, performance-selected",
         "mean_R2": subset["mean"].mean(), "median_R2": subset["median"].median(),
         "avg_variance": subset["var"].mean(), "median_variance": subset["var"].median()},
    ]
    summary = pd.DataFrame(rows)
    summary.to_csv(OUT_DIR / "loyo_global_full_vs_top20_summary.csv", index=False)
    print(summary.to_string(index=False))
    print(f"\nSelection threshold: mean R2 >= {subset['mean'].min():.3f} (the {N_SUBSET}th-highest of {len(pp)} pixels)")

    # boxplot: full pool vs subset, R2 distribution (per-pixel mean R2 across 11 folds)
    fig, ax = plt.subplots(figsize=(7, 6.2), constrained_layout=True)
    data = [pp["mean"].values, subset["mean"].values]
    bp = ax.boxplot(data, tick_labels=[f"Full pool\n(n={len(pp)})", f"Top-{N_SUBSET} subset\n(n={N_SUBSET})"],
                     patch_artist=True, showmeans=True, widths=0.5)
    for patch, c in zip(bp["boxes"], [FULL_COLOR, SUBSET_COLOR]):
        patch.set_facecolor(c); patch.set_alpha(0.75)
    ax.axhline(0, color="black", lw=0.8)
    ax.set_ylabel("Per-pixel mean R² across 11 LOYO folds")
    ax.set_title("Global pool: full result vs. an exploratory\nperformance-selected subset", loc="left",
                 fontsize=12, fontweight="bold")
    ax.text(0.5, -0.16, f"Selection rule: top {N_SUBSET} of {len(pp)} pixels ranked BY mean R² itself\n"
            "(subset statistics are conditional on this selection, not an independent estimate)",
            transform=ax.transAxes, ha="center", fontsize=9, color="#B5651D", style="italic")
    fig.savefig(OUT_DIR / "loyo_global_full_vs_top20_boxplot.png", dpi=220, bbox_inches="tight")
    fig.savefig(OUT_DIR / "loyo_global_full_vs_top20_boxplot.pdf", bbox_inches="tight")
    plt.close(fig)
    print("saved loyo_global_full_vs_top20_boxplot.png")


if __name__ == "__main__":
    main()
