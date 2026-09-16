# Builds the summary tables/figures for the large-scale cloud-ERA5 zero-shot
# Chronos-2 study (run_era5_chronos_batch.py's output), and compares against
# the existing gridMET zero-shot results for the SAME pixels
# (outputs/purity32_pixel_study/zero_shot_70pixels.csv) - matched pixels
# only, matched 22-year context in both, so this is a fair, like-for-like
# comparison. No new experiments are run here, only analysis of already-
# saved results.
import sys
from pathlib import Path

import matplotlib
matplotlib.use("AGG")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

CODE_DIR = Path("/home/deh25003/chronos-forecasting/Chronos2-vegetation-forecasting/Code")
sys.path.insert(0, str(CODE_DIR))
import plotting_utils as pu  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "outputs"
GRIDMET_CSV = Path("/home/deh25003/chronos-forecasting/Chronos2-vegetation-forecasting/outputs/purity32_pixel_study/zero_shot_70pixels.csv")

CLASS_COLORS = {
    "TREES_NE": "#1B7837", "TREES_BD": "#5AAE61", "TREES_ND": "#A6DBA0",
    "SHRUBS_NE": "#B35806", "SHRUBS_BD": "#E08214", "SHRUBS_ND": "#FDB863",
    "GRASS_NAT": "#762A83", "GRASS_MAN": "#C2A5CF",
}


def main():
    df = pd.read_csv(OUT_DIR / "era5_cloud_70pixels.csv")
    failed = df[df.get("error").notna()] if "error" in df.columns else df.iloc[0:0]
    ok = df[df["R2"].notna()].copy() if "R2" in df.columns else df.copy()
    ok = ok.sort_values("R2", ascending=False).reset_index(drop=True)
    print(f"{len(ok)} succeeded, {len(failed)} failed out of {len(df)}")

    # --- deliverable 2/3/4: result table + summary stats + per-pixel metrics ---
    ok.to_csv(OUT_DIR / "era5_cloud_70pixels_clean.csv", index=False)
    overall = ok[["RMSE", "MAE", "MAPE", "R2", "Pearson_r"]].agg(["mean", "median", "std", "min", "max"])
    overall.to_csv(OUT_DIR / "era5_cloud_summary_overall.csv")
    by_class = ok.groupby("dominant_pft")["R2"].agg(["count", "mean", "median", "std", "min", "max"]).sort_values("mean", ascending=False)
    by_class.to_csv(OUT_DIR / "era5_cloud_summary_by_class.csv")
    by_region = ok.groupby("region")["R2"].agg(["count", "mean", "median"]).sort_values("mean", ascending=False)
    by_region.to_csv(OUT_DIR / "era5_cloud_summary_by_region.csv")
    print(overall)
    print(by_class)
    print(by_region)

    # --- deliverable 5: comparison against gridMET, matched pixels only ---
    gridmet = pd.read_csv(GRIDMET_CSV)[["site", "RMSE", "MAE", "MAPE", "R2", "Pearson_r"]]
    gridmet.columns = ["site"] + [f"gridmet_{c}" for c in ["RMSE", "MAE", "MAPE", "R2", "Pearson_r"]]
    merged = ok.merge(gridmet, on="site", how="inner")
    merged["R2_diff_era5_minus_gridmet"] = merged["R2"] - merged["gridmet_R2"]
    merged.to_csv(OUT_DIR / "era5_cloud_vs_gridmet_matched.csv", index=False)
    print(f"\nMatched pixels for ERA5-vs-gridMET comparison: {len(merged)}/{len(ok)}")
    print(f"Mean R2: ERA5-cloud={merged['R2'].mean():.4f}  gridMET={merged['gridmet_R2'].mean():.4f}  "
          f"diff={merged['R2_diff_era5_minus_gridmet'].mean():+.4f}")
    print(f"Median R2: ERA5-cloud={merged['R2'].median():.4f}  gridMET={merged['gridmet_R2'].median():.4f}")
    n_era5_better = (merged["R2_diff_era5_minus_gridmet"] > 0).sum()
    print(f"ERA5 scores higher R2 on {n_era5_better}/{len(merged)} matched pixels")

    # --- deliverable 6a: R2-by-pixel bar + by-class boxplot (ERA5-cloud) ---
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6.5), constrained_layout=True,
                                    gridspec_kw={"width_ratios": [1.8, 1]})
    colors = [CLASS_COLORS.get(c, "#888888") for c in ok["dominant_pft"]]
    ax1.bar(range(len(ok)), ok["R2"], color=colors, edgecolor="black", linewidth=0.3)
    ax1.axhline(0, color="black", lw=0.8)
    ax1.axhline(ok["R2"].median(), color=pu.ZERO_SHOT_COLOR, lw=1.2, ls="--")
    ax1.set_xticks(range(len(ok)))
    ax1.set_xticklabels(ok["site"], rotation=90, fontsize=5.5)
    ax1.set_ylabel("Zero-shot Chronos-2 $R^2$ (cloud ERA5, vs. raw observed LAI)")
    ax1.set_title(f"(a) All {len(ok)} pixels, sorted by $R^2$ (cloud ERA5, 22-yr context)", loc="left")
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in CLASS_COLORS.values()]
    ax1.legend(handles + [plt.Line2D([0], [0], color=pu.ZERO_SHOT_COLOR, ls="--")],
               list(CLASS_COLORS.keys()) + [f"median={ok['R2'].median():.3f}"],
               frameon=False, fontsize=7, loc="lower left", ncol=2)
    order = ok.groupby("dominant_pft")["R2"].median().sort_values(ascending=False).index
    data = [ok[ok["dominant_pft"] == c]["R2"].values for c in order]
    bp = ax2.boxplot(data, tick_labels=order, patch_artist=True, showmeans=True)
    for patch, c in zip(bp["boxes"], order):
        patch.set_facecolor(CLASS_COLORS.get(c, "#888888"))
        patch.set_alpha(0.7)
    ax2.axhline(0, color="black", lw=0.8)
    ax2.set_xticklabels(order, rotation=45, ha="right", fontsize=8)
    ax2.set_ylabel("$R^2$")
    ax2.set_title("(b) By dominant vegetation class", loc="left")
    pu.save_fig(fig, OUT_DIR, "era5_cloud_r2_by_pixel_and_class")

    # --- deliverable 6b: ERA5-cloud vs gridMET scatter, matched pixels ---
    fig2, ax = plt.subplots(figsize=(7, 7), constrained_layout=True)
    colors2 = [CLASS_COLORS.get(c, "#888888") for c in merged["dominant_pft"]]
    ax.scatter(merged["gridmet_R2"], merged["R2"], c=colors2, edgecolor="black", linewidth=0.4, s=40, zorder=3)
    lims = [min(merged[["gridmet_R2", "R2"]].min()) - 0.05, 1.02]
    ax.plot(lims, lims, "k--", lw=1, zorder=1)
    ax.set_xlim(lims); ax.set_ylim(lims)
    ax.set_xlabel("gridMET zero-shot $R^2$ (same pixel, same 22-yr context)")
    ax.set_ylabel("Cloud ERA5 zero-shot $R^2$")
    ax.set_title(f"ERA5 (cloud) vs. gridMET, {len(merged)} matched pixels\n"
                 f"mean $\\Delta R^2$={merged['R2_diff_era5_minus_gridmet'].mean():+.3f}")
    handles2 = [plt.Line2D([0], [0], marker="o", color="w", markerfacecolor=c, markeredgecolor="black", markersize=8)
                for c in CLASS_COLORS.values()]
    ax.legend(handles2, list(CLASS_COLORS.keys()), frameon=False, fontsize=7, loc="lower right", ncol=2)
    pu.save_fig(fig2, OUT_DIR, "era5_cloud_vs_gridmet_scatter")

    # --- deliverable 8: failures/outliers ---
    print("\n--- Failed pixels ---")
    if len(failed):
        print(failed[["site", "error"]].to_string(index=False))
    else:
        print("(none)")
    print("\n--- Bottom 5 by R2 (potential outliers) ---")
    print(ok.tail(5)[["site", "dominant_pft", "region", "pft_purity", "RMSE", "R2", "Pearson_r"]].to_string(index=False))


if __name__ == "__main__":
    main()
