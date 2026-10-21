# Summarizes Prof. Wang's anomaly-forecasting follow-up
# (Code/loyo_cv_anomaly_chronos2.py / experiments/global_era5_chronos/
# scripts/loyo_cv_anomaly_global.py): Chronos-2 forecasts the LAI ANOMALY
# directly (not raw LAI, decomposed afterward) for both pools, scored
# against the held-out year's true anomaly.
from pathlib import Path

import matplotlib
matplotlib.use("AGG")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path("/home/deh25003/chronos-forecasting/Chronos2-vegetation-forecasting")
CONUS_CSV = ROOT / "outputs/loyo_cv_anomaly/all_folds_anomaly.csv"
GLOBAL_CSV = ROOT / "experiments/global_era5_chronos/outputs/loyo_cv_anomaly/all_folds_anomaly.csv"
OUT_DIR = ROOT / "outputs/loyo_cv_pools_summary"
OUT_DIR.mkdir(parents=True, exist_ok=True)

CONUS_COLOR = "#2F6F5E"
GLOBAL_COLOR = "#8C1D40"


def summarize(df, pool_name):
    print(f"\n=== {pool_name} ({len(df)} folds) ===")
    for col in ["R2_anomaly", "Pearson_r_anomaly", "R2_raw_reconstructed"]:
        print(f"{col}: mean={df[col].mean():.4f} median={df[col].median():.4f} std={df[col].std():.4f}")
    return dict(pool=pool_name, n_folds=len(df),
                mean_R2_anomaly=df["R2_anomaly"].mean(), median_R2_anomaly=df["R2_anomaly"].median(),
                mean_Pearson_r_anomaly=df["Pearson_r_anomaly"].mean(),
                median_Pearson_r_anomaly=df["Pearson_r_anomaly"].median(),
                mean_R2_raw_reconstructed=df["R2_raw_reconstructed"].mean(),
                median_R2_raw_reconstructed=df["R2_raw_reconstructed"].median())


def main():
    conus = pd.read_csv(CONUS_CSV)
    glob_ = pd.read_csv(GLOBAL_CSV)

    conus_summary = summarize(conus, "CONUS (70 pixels)")
    global_summary = summarize(glob_, "Global (68 pixels)")
    pd.DataFrame([conus_summary, global_summary]).to_csv(OUT_DIR / "loyo_anomaly_summary.csv", index=False)

    # Distribution comparison: Pearson r (anomaly) per fold, both pools - the
    # primary, sample-size-robust answer to "how well does the model capture
    # year-to-year variability," directly forecast rather than decomposed
    # post-hoc.
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5), constrained_layout=True)
    for ax, col, title in zip(axes, ["Pearson_r_anomaly", "R2_anomaly"],
                               ["Pearson r (LAI anomaly, per fold)", "R² (LAI anomaly, per fold)"]):
        data = [conus[col].dropna(), glob_[col].dropna()]
        bp = ax.boxplot(data, labels=["CONUS\n(770 folds)", "Global\n(748 folds)"], widths=0.5,
                         patch_artist=True, showmeans=True, medianprops=dict(color="black"))
        for patch, color in zip(bp["boxes"], [CONUS_COLOR, GLOBAL_COLOR]):
            patch.set_facecolor(color); patch.set_alpha(0.35)
        ax.axhline(0, color="#888888", lw=0.8)
        ax.set_title(title, fontsize=12.5, fontweight="bold", loc="left")
        ax.tick_params(labelsize=10)
    fig.suptitle("Forecasting the LAI anomaly directly (Prof. Wang's follow-up) vs. zero-shot Chronos-2",
                 fontsize=13, fontweight="bold")
    fig.savefig(OUT_DIR / "loyo_anomaly_boxplot.png", dpi=200, bbox_inches="tight")
    fig.savefig(OUT_DIR / "loyo_anomaly_boxplot.pdf", bbox_inches="tight")
    plt.close(fig)
    print("saved loyo_anomaly_boxplot.png")

    # Per-test-year mean Pearson r (anomaly), both pools - is any year uniformly
    # hard, same question as the raw-LAI "Is Any Single Year Uniformly Hard?" slide.
    conus_by_year = conus.groupby("test_year")["Pearson_r_anomaly"].mean()
    global_by_year = glob_.groupby("test_year")["Pearson_r_anomaly"].mean()
    fig, ax = plt.subplots(figsize=(10, 5), constrained_layout=True)
    ax.plot(conus_by_year.index, conus_by_year.values, "o-", color=CONUS_COLOR, label="CONUS (70 pixels)")
    ax.plot(global_by_year.index, global_by_year.values, "o-", color=GLOBAL_COLOR, label="Global (68 pixels)")
    ax.axhline(0, color="#888888", lw=0.8)
    ax.set_xlabel("Held-out test year"); ax.set_ylabel("Mean Pearson r (LAI anomaly) across pixels")
    ax.set_title("Anomaly-forecasting skill by held-out year", fontsize=12.5, fontweight="bold", loc="left")
    ax.legend(frameon=False)
    fig.savefig(OUT_DIR / "loyo_anomaly_by_year.png", dpi=200, bbox_inches="tight")
    plt.close(fig)
    print("saved loyo_anomaly_by_year.png")


if __name__ == "__main__":
    main()
