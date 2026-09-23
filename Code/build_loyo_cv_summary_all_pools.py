# Aggregates the zero-shot LOYO-CV results for BOTH pixel pools:
#   - CONUS 70-pixel pool: outputs/loyo_cv/<site>/fold_<year>_metrics.csv
#     (Code/loyo_cv_chronos2.py, run on the full 70-pixel pool -
#     the 3 already-published core pixels' pre-existing fold files, which
#     also contain finetuned_lora rows from the original 3-pixel study, are
#     filtered to mode=="zero_shot" here, never modified)
#   - Global 68-pixel pool: experiments/global_era5_chronos/outputs/loyo_cv/
#     <pixel>/fold_<year>_metrics.csv (run_loyo_cv_global.py)
# Both pools share the IDENTICAL protocol: fixed 12-year rolling context
# window, held-out years 2012-2022 (11 folds), zero-shot Chronos-2 only.
#
# Produces, for each pool: a long-format all-folds table, a per-pixel
# mean/median/std/var summary, the headline "average variance" statistic
# (mean of each pixel's own R² variance across its 11 folds - directly
# answers "how much does a single pixel's score swing year to year, on
# average across pixels"), and comparison figures.
from pathlib import Path

import matplotlib
matplotlib.use("AGG")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path("/home/deh25003/chronos-forecasting/Chronos2-vegetation-forecasting")
CONUS_LOYO_DIR = ROOT / "outputs/loyo_cv"
GLOBAL_LOYO_DIR = ROOT / "experiments/global_era5_chronos/outputs/loyo_cv"
OUT_DIR = ROOT / "outputs/loyo_cv_pools_summary"
OUT_DIR.mkdir(parents=True, exist_ok=True)

CONUS_COLOR = "#2F6F5E"
GLOBAL_COLOR = "#8C1D40"

CLASS_COLORS = {
    "TREES_NE": "#1B7837", "TREES-NE": "#1B7837", "TREES_BD": "#5AAE61", "TREES-BD": "#5AAE61",
    "TREES_ND": "#A6DBA0", "TREES-ND": "#A6DBA0", "TREES-BE": "#2C9E5B",
    "SHRUBS_NE": "#B35806", "SHRUBS-NE": "#B35806", "SHRUBS_BD": "#E08214", "SHRUBS-BD": "#E08214",
    "SHRUBS_ND": "#FDB863", "SHRUBS-ND": "#FDB863", "SHRUBS-BE": "#8C6BB1",
    "GRASS_NAT": "#762A83", "GRASS-NAT": "#762A83", "GRASS_MAN": "#C2A5CF", "GRASS-MAN": "#C2A5CF",
}


def plot_pool_bar(per_pixel, class_map, pool_name, title, out_stem):
    df = per_pixel.reset_index().sort_values("mean", ascending=False)
    colors = [CLASS_COLORS.get(class_map.get(s, ""), "#888888") for s in df["site"]]
    fig, ax = plt.subplots(figsize=(15, 5.5), constrained_layout=True)
    ax.bar(range(len(df)), df["mean"], yerr=df["std"], color=colors, edgecolor="black",
           linewidth=0.3, ecolor="#00000055", capsize=1.5, error_kw={"linewidth": 0.7})
    ax.axhline(0, color="black", lw=0.8)
    ax.axhline(df["mean"].median(), color="#0072B2", lw=1.2, ls="--")
    ax.set_xticks(range(len(df)))
    ax.set_xticklabels(df["site"], rotation=90, fontsize=5.5)
    ax.set_ylabel("Mean R² across 11 LOYO folds (error bar = ±1 std)")
    ax.set_title(title, loc="left", fontsize=12.5, fontweight="bold")
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in dict.fromkeys(CLASS_COLORS[k] for k in class_map.values() if k in CLASS_COLORS).keys()]
    fig.savefig(OUT_DIR / f"{out_stem}.png", dpi=220, bbox_inches="tight")
    fig.savefig(OUT_DIR / f"{out_stem}.pdf", bbox_inches="tight")
    plt.close(fig)
    print(f"saved {out_stem}.png")


def load_pool(loyo_dir, exclude_dirs=("comparison",)):
    rows = []
    for site_dir in sorted(loyo_dir.iterdir()):
        if not site_dir.is_dir() or site_dir.name in exclude_dirs:
            continue
        for fold_csv in sorted(site_dir.glob("fold_*_metrics.csv")):
            df = pd.read_csv(fold_csv)
            df = df[df["mode"] == "zero_shot"]
            rows.append(df)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def summarize(all_folds, pool_name):
    per_pixel = all_folds.groupby("site")["R2"].agg(["count", "mean", "median", "std", "min", "max"])
    per_pixel["var"] = per_pixel["std"] ** 2
    per_pixel = per_pixel.sort_values("mean", ascending=False)
    per_pixel.to_csv(OUT_DIR / f"loyo_{pool_name}_per_pixel_summary.csv")

    avg_variance = per_pixel["var"].mean()
    avg_std = per_pixel["std"].mean()
    median_variance = per_pixel["var"].median()
    n_pixels = len(per_pixel)
    n_folds = len(all_folds)
    print(f"\n=== {pool_name} ===")
    print(f"n_pixels={n_pixels}, n_folds={n_folds}")
    print(f"mean of per-pixel mean R2:   {per_pixel['mean'].mean():.4f}")
    print(f"mean of per-pixel median R2: {per_pixel['median'].mean():.4f}")
    print(f"AVERAGE VARIANCE (mean of per-pixel R2 variance across 11 folds): {avg_variance:.4f}")
    print(f"MEDIAN VARIANCE (robust to outlier pixels):                       {median_variance:.4f}")
    print(f"AVERAGE STD (mean of per-pixel R2 std across 11 folds):          {avg_std:.4f}")
    top_outliers = per_pixel.sort_values("var", ascending=False).head(3)
    print(f"Top-3 highest-variance pixels:\n{top_outliers[['count','mean','var']]}")
    return per_pixel, avg_variance, avg_std, median_variance


def plot_comparison(conus_pp, global_pp, conus_folds, global_folds):
    # (a) per-pixel mean R2 distribution, both pools
    fig, axes = plt.subplots(1, 2, figsize=(14, 6), constrained_layout=True)
    ax = axes[0]
    data = [conus_pp["mean"].values, global_pp["mean"].values]
    bp = ax.boxplot(data, tick_labels=[f"CONUS (70)\navg var={conus_pp['var'].mean():.3f}",
                                        f"Global (68)\navg var={global_pp['var'].mean():.3f}"],
                     patch_artist=True, showmeans=True, widths=0.5)
    for patch, c in zip(bp["boxes"], [CONUS_COLOR, GLOBAL_COLOR]):
        patch.set_facecolor(c); patch.set_alpha(0.75)
    ax.axhline(0, color="black", lw=0.8)
    ax.set_ylabel("Per-pixel mean R² across 11 LOYO folds")
    ax.set_title("(a) Per-pixel mean R² (LOYO-CV, 2012-2022)", loc="left", fontsize=11.5)

    # (b) per-pixel R2 VARIANCE distribution, both pools - log scale, since a
    # handful of already-diagnosed outlier pixels (e.g. evergreen's 2012
    # drought fold) are >100x the typical pixel's variance and would
    # otherwise compress every other box to an unreadable sliver
    ax2 = axes[1]
    data2 = [conus_pp["var"].values, global_pp["var"].values]
    bp2 = ax2.boxplot(data2, tick_labels=[f"CONUS (70)\nmedian var={conus_pp['var'].median():.3f}",
                                           f"Global (68)\nmedian var={global_pp['var'].median():.3f}"],
                       patch_artist=True, showmeans=True, widths=0.5)
    for patch, c in zip(bp2["boxes"], [CONUS_COLOR, GLOBAL_COLOR]):
        patch.set_facecolor(c); patch.set_alpha(0.75)
    ax2.set_yscale("log")
    ax2.set_ylabel("Per-pixel R² variance across 11 LOYO folds (log scale)")
    ax2.set_title("(b) Year-to-year variance per pixel (lower = more stable)", loc="left", fontsize=11.5)
    fig.suptitle("LOYO-CV robustness check: does a pixel's R² swing a lot year to year?", fontsize=13, fontweight="bold")
    fig.savefig(OUT_DIR / "loyo_variance_comparison.png", dpi=220, bbox_inches="tight")
    fig.savefig(OUT_DIR / "loyo_variance_comparison.pdf", bbox_inches="tight")
    plt.close(fig)
    print("saved loyo_variance_comparison.png")

    # (c) R2 by held-out year, both pools (year-difficulty)
    fig2, ax3 = plt.subplots(figsize=(10, 5.5), constrained_layout=True)
    conus_by_year = conus_folds.groupby("test_year")["R2"].median()
    global_by_year = global_folds.groupby("test_year")["R2"].median()
    ax3.plot(conus_by_year.index, conus_by_year.values, marker="o", color=CONUS_COLOR, lw=2, label="CONUS (70 pixels, median)")
    ax3.plot(global_by_year.index, global_by_year.values, marker="o", color=GLOBAL_COLOR, lw=2, label="Global (68 pixels, median)")
    ax3.axhline(0, color="black", lw=0.7)
    ax3.set_xlabel("Held-out test year")
    ax3.set_ylabel("Median R² across pixels")
    ax3.set_title("LOYO-CV: is any year uniformly hard?", loc="left", fontsize=12, fontweight="bold")
    ax3.legend(frameon=False)
    fig2.savefig(OUT_DIR / "loyo_r2_by_year.png", dpi=220, bbox_inches="tight")
    fig2.savefig(OUT_DIR / "loyo_r2_by_year.pdf", bbox_inches="tight")
    plt.close(fig2)
    print("saved loyo_r2_by_year.png")


def main():
    conus_folds = load_pool(CONUS_LOYO_DIR)
    global_folds = load_pool(GLOBAL_LOYO_DIR)
    conus_folds.to_csv(OUT_DIR / "loyo_conus70_all_folds.csv", index=False)
    global_folds.to_csv(OUT_DIR / "loyo_global68_all_folds.csv", index=False)

    conus_pp, conus_avg_var, conus_avg_std, conus_med_var = summarize(conus_folds, "conus70")
    global_pp, global_avg_var, global_avg_std, global_med_var = summarize(global_folds, "global68")

    conus_pool_meta = pd.read_csv(ROOT / "outputs/purity32_pixel_study/zero_shot_70pixels.csv")
    conus_class_map = dict(zip(conus_pool_meta["site"], conus_pool_meta["dominant_pft"]))
    global_pool_meta = pd.read_csv(ROOT / "experiments/global_era5_chronos/data_selection/global_candidate_pixels_70.csv")
    global_class_map = dict(zip(global_pool_meta["pixel_id"], global_pool_meta["dominant_pft"]))
    plot_pool_bar(conus_pp, conus_class_map, "conus70",
                  "CONUS (70 pixels): mean R² across 11 LOYO-CV folds (2012-2022), by pixel", "loyo_conus70_by_pixel")
    plot_pool_bar(global_pp, global_class_map, "global68",
                  "Global (68 pixels): mean R² across 11 LOYO-CV folds (2012-2022), by pixel", "loyo_global68_by_pixel")

    plot_comparison(conus_pp, global_pp, conus_folds, global_folds)

    headline = pd.DataFrame([
        {"pool": "CONUS (70 pixels)", "n_pixels": len(conus_pp), "n_folds": len(conus_folds),
         "mean_of_pixel_mean_R2": conus_pp["mean"].mean(), "mean_of_pixel_median_R2": conus_pp["median"].mean(),
         "average_variance": conus_avg_var, "median_variance": conus_med_var, "average_std": conus_avg_std},
        {"pool": "Global (68 pixels)", "n_pixels": len(global_pp), "n_folds": len(global_folds),
         "mean_of_pixel_mean_R2": global_pp["mean"].mean(), "mean_of_pixel_median_R2": global_pp["median"].mean(),
         "average_variance": global_avg_var, "median_variance": global_med_var, "average_std": global_avg_std},
    ])
    headline.to_csv(OUT_DIR / "loyo_headline_summary.csv", index=False)
    print("\n", headline.to_string(index=False))


if __name__ == "__main__":
    main()
