# Prof. Wang's requested analysis: R^2 computed ACROSS the 11 LOYO held-out
# years at each FIXED position in the 8-day composite/seasonal cycle (e.g.
# "the 1st 8-day composite of the year, across all 11 held-out years"),
# rather than across time WITHIN one held-out year (the original per-fold
# R^2, which is dominated by the seasonal cycle itself - both actual and
# predicted LAI follow a strong yearly shape, so within-year R^2 looks good
# even when the model isn't specifically tracking real year-to-year
# deviations). Fixing the calendar position removes the seasonal component,
# isolating genuine inter-annual variability.
#
# For each composite_index k (1..46, the MOD13/MODIS-style 8-day-period
# index within a year: DOY 1,9,17,... -> 1,2,3,...), pools EVERY (pixel,
# year) pair's (ground_truth, prediction) at that position - across all
# pixels AND all 11 held-out years in a pool - then computes one R^2 over
# that pooled sample (requires >= MIN_POOLED_N points; else marked
# insufficient, not silently computed on too little data).
#
# Reads outputs/loyo_cv_predictions/ (CONUS) and
# experiments/global_era5_chronos/outputs/loyo_cv_predictions/ (global),
# both built by loyo_cv_capture_predictions{,_global}.py - purely additive
# outputs, no existing published result touched.
from pathlib import Path

import matplotlib
matplotlib.use("AGG")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import r2_score

ROOT = Path("/home/deh25003/chronos-forecasting/Chronos2-vegetation-forecasting")
CONUS_PRED_DIR = ROOT / "outputs/loyo_cv_predictions"
GLOBAL_PRED_DIR = ROOT / "experiments/global_era5_chronos/outputs/loyo_cv_predictions"
OUT_DIR = ROOT / "outputs/loyo_cv_pools_summary"
OUT_DIR.mkdir(parents=True, exist_ok=True)

CONUS_COLOR = "#2F6F5E"
GLOBAL_COLOR = "#8C1D40"
MIN_POOLED_N = 30  # need a real sample to trust an R2 estimate


def load_all_predictions(pred_dir):
    rows = []
    for site_dir in sorted(pred_dir.iterdir()):
        if not site_dir.is_dir():
            continue
        for f in sorted(site_dir.glob("fold_*_predictions.csv")):
            rows.append(pd.read_csv(f))
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


MIN_YEARS_PER_PIXEL = 8  # need most of the 11 held-out years present for a pixel's own R2 to mean anything


def r2_by_composite_position_pooled(df):
    """Pools ALL (pixel, year) pairs at each position, one R2 over the
    combined sample. NOTE: this conflates between-pixel differences (e.g.
    forest vs. grassland baseline LAI - easy to "explain") with genuine
    within-pixel inter-annual variability. Kept as a secondary reference,
    NOT the primary answer to "does the model capture year-to-year
    variability at a given location" - see r2_by_composite_position_per_pixel."""
    rows = []
    for k, g in df.groupby("composite_index"):
        n = len(g)
        if n < MIN_POOLED_N:
            rows.append({"composite_index": k, "n_pooled": n, "R2": np.nan})
            continue
        r2 = r2_score(g["ground_truth"], g["prediction"])
        rows.append({"composite_index": k, "n_pooled": n, "R2": r2})
    return pd.DataFrame(rows).sort_values("composite_index")


def r2_by_composite_position_per_pixel(df):
    """PRIMARY analysis, matching Prof. Wang's description exactly: for
    EACH pixel separately, at each fixed composite position, compute R2
    using ONLY that pixel's own (up to 11) held-out-year values - isolates
    genuine within-pixel inter-annual variability, uncontaminated by
    between-pixel spatial differences. Then aggregate (mean/median) across
    pixels to get one typical-R2 value per position. With <=11 points per
    pixel-position, any single pixel's R2 is noisy; the point of averaging
    across ~70/~68 pixels is to average that noise out."""
    per_pixel_rows = []
    for (k, site), g in df.groupby(["composite_index", "site"]):
        if g["test_year"].nunique() < MIN_YEARS_PER_PIXEL:
            continue
        r2 = r2_score(g["ground_truth"], g["prediction"])
        # Pearson r as a complementary, small-sample-robust statistic: R2 can
        # blow up arbitrarily negative with n<=11 points whenever there's a
        # systematic bias/scale mismatch, even if the model still ranks
        # years in roughly the right order - Pearson r stays bounded in
        # [-1,1] and is far less sensitive to that specific failure mode.
        pearson_r = np.corrcoef(g["ground_truth"], g["prediction"])[0, 1] if g["ground_truth"].std() > 0 and g["prediction"].std() > 0 else np.nan
        per_pixel_rows.append({"composite_index": k, "site": site, "n_years": g["test_year"].nunique(),
                                "R2": r2, "Pearson_r": pearson_r})
    per_pixel_df = pd.DataFrame(per_pixel_rows)

    rows = []
    for k, g in per_pixel_df.groupby("composite_index"):
        rows.append({"composite_index": k, "n_pixels": len(g),
                     "R2_mean": g["R2"].mean(), "R2_median": g["R2"].median(), "R2_std": g["R2"].std(),
                     "Pearson_r_mean": g["Pearson_r"].mean(), "Pearson_r_median": g["Pearson_r"].median()})
    return pd.DataFrame(rows).sort_values("composite_index"), per_pixel_df


def plot_sequence(conus_seq, global_seq, stem, ylabel, title, col="R2"):
    fig, ax = plt.subplots(figsize=(12, 6), constrained_layout=True)
    ax.plot(conus_seq["composite_index"], conus_seq[col], marker="o", ms=4, color=CONUS_COLOR, lw=1.8,
             label="CONUS (70 pixels)")
    ax.plot(global_seq["composite_index"], global_seq[col], marker="o", ms=4, color=GLOBAL_COLOR, lw=1.8,
             label="Global (68 pixels)")
    ax.axhline(0, color="black", lw=0.8)
    ax.set_xlabel("8-day composite position within the year (1 = Jan 1-8, ~46 = late Dec)")
    ax.set_ylabel(ylabel)
    ax.set_title(title, loc="left", fontsize=12.5, fontweight="bold")
    ax.legend(frameon=False, loc="lower center")
    fig.savefig(OUT_DIR / f"{stem}.png", dpi=220, bbox_inches="tight")
    fig.savefig(OUT_DIR / f"{stem}.pdf", bbox_inches="tight")
    plt.close(fig)
    print(f"saved {stem}.png")


def summarize_pooled(seq, pool_name):
    valid = seq.dropna(subset=["R2"])
    print(f"\n=== {pool_name}: POOLED (secondary/reference) R2-by-composite-position ===")
    print(f"mean={valid['R2'].mean():.4f} median={valid['R2'].median():.4f} std={valid['R2'].std():.4f}")
    return {"pool": pool_name, "mean_R2": valid["R2"].mean(), "median_R2": valid["R2"].median(),
            "std_R2": valid["R2"].std(), "min_R2": valid["R2"].min(), "max_R2": valid["R2"].max()}


def summarize_per_pixel(seq, pool_name):
    print(f"\n=== {pool_name}: PER-PIXEL (PRIMARY) R2-by-composite-position ===")
    print(f"mean of per-position mean R2:   {seq['R2_mean'].mean():.4f}")
    print(f"mean of per-position median R2: {seq['R2_median'].mean():.4f}")
    print(f"mean of per-position std R2:    {seq['R2_std'].mean():.4f}")
    print(f"range across positions: {seq['R2_mean'].min():.4f} to {seq['R2_mean'].max():.4f}")
    print(f"mean of per-position mean Pearson r:   {seq['Pearson_r_mean'].mean():.4f}")
    print(f"mean of per-position median Pearson r: {seq['Pearson_r_median'].mean():.4f}")
    return {"pool": pool_name, "mean_of_position_mean_R2": seq["R2_mean"].mean(),
            "mean_of_position_median_R2": seq["R2_median"].mean(),
            "mean_of_position_std_R2": seq["R2_std"].mean(),
            "min_position_mean_R2": seq["R2_mean"].min(), "max_position_mean_R2": seq["R2_mean"].max(),
            "mean_of_position_mean_Pearson_r": seq["Pearson_r_mean"].mean(),
            "mean_of_position_median_Pearson_r": seq["Pearson_r_median"].mean()}


def main():
    conus_all = load_all_predictions(CONUS_PRED_DIR)
    global_all = load_all_predictions(GLOBAL_PRED_DIR)
    print(f"CONUS: {len(conus_all)} total (pixel,year,composite) predictions loaded")
    print(f"Global: {len(global_all)} total (pixel,year,composite) predictions loaded")

    # PRIMARY: per-pixel R2 across its own 11 years, then averaged across pixels
    conus_pp_seq, conus_pp_raw = r2_by_composite_position_per_pixel(conus_all)
    global_pp_seq, global_pp_raw = r2_by_composite_position_per_pixel(global_all)
    conus_pp_seq.to_csv(OUT_DIR / "loyo_conus70_r2_by_position_per_pixel.csv", index=False)
    global_pp_seq.to_csv(OUT_DIR / "loyo_global68_r2_by_position_per_pixel.csv", index=False)
    conus_pp_raw.to_csv(OUT_DIR / "loyo_conus70_r2_by_position_per_pixel_raw.csv", index=False)
    global_pp_raw.to_csv(OUT_DIR / "loyo_global68_r2_by_position_per_pixel_raw.csv", index=False)

    conus_pp_summary = summarize_per_pixel(conus_pp_seq, "CONUS (70 pixels)")
    global_pp_summary = summarize_per_pixel(global_pp_seq, "Global (68 pixels)")
    pd.DataFrame([conus_pp_summary, global_pp_summary]).to_csv(
        OUT_DIR / "loyo_r2_by_position_per_pixel_summary.csv", index=False)

    plot_sequence(conus_pp_seq.rename(columns={"R2_mean": "R2"}), global_pp_seq.rename(columns={"R2_mean": "R2"}),
                  "loyo_r2_by_composite_position_per_pixel",
                  "Mean per-pixel R² across its own 11 held-out years",
                  "Inter-annual variability at a fixed calendar position, PER PIXEL then averaged\n"
                  "(isolates within-pixel year-to-year variation from between-pixel spatial differences)")
    plot_sequence(conus_pp_seq.rename(columns={"Pearson_r_mean": "R2"}), global_pp_seq.rename(columns={"Pearson_r_mean": "R2"}),
                  "loyo_pearsonr_by_composite_position_per_pixel",
                  "Mean per-pixel Pearson r across its own 11 held-out years",
                  "Same isolation as above, using Pearson r (more robust than R² at n<=11 points per pixel)")

    # SECONDARY/reference: pooled across pixels+years (conflates spatial + temporal variance - see docstring)
    conus_seq = r2_by_composite_position_pooled(conus_all)
    global_seq = r2_by_composite_position_pooled(global_all)
    conus_seq.to_csv(OUT_DIR / "loyo_conus70_r2_by_composite_position_pooled.csv", index=False)
    global_seq.to_csv(OUT_DIR / "loyo_global68_r2_by_composite_position_pooled.csv", index=False)
    conus_summary = summarize_pooled(conus_seq, "CONUS (70 pixels)")
    global_summary = summarize_pooled(global_seq, "Global (68 pixels)")
    pd.DataFrame([conus_summary, global_summary]).to_csv(
        OUT_DIR / "loyo_r2_by_composite_position_pooled_summary.csv", index=False)
    plot_sequence(conus_seq, global_seq, "loyo_r2_by_composite_position_pooled",
                  "R² across the 11 held-out years, pooled across pixels",
                  "Reference only: pooled across pixels (conflates spatial + inter-annual variance - see report)")


if __name__ == "__main__":
    main()
