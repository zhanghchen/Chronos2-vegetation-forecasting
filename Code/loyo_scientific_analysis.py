# Scientific analysis of the LOYO-CV results (not another metrics dump):
# full per-model distribution statistics, which held-out years are
# consistently difficult and why (checked against the raw LAI/climate data,
# not just inferred from R2), whether Chronos-2 holds up better than the
# AELSTM family specifically on difficult years, cross-site rank
# consistency and top/bottom-finish frequency, and outlier-fold
# investigation figures. Reads only outputs/loyo_cv/comparison/loyo_all_folds.csv
# (already built by build_loyo_comparison.py) plus the raw site CSVs for the
# outlier investigation - no retraining, no new per-fold CSVs.
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

import common_pipeline as cp
import plotting_utils as pu
from build_fair_comparison import AELSTM_MODEL_COLORS
from loyo_cv_chronos2 import circular_doy_climatology

AELSTM_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "AELSTM" / "data" / "processed" / "sites"
OUTPUT_DIR = cp.OUTPUTS_ROOT / "loyo_cv" / "comparison"
AELSTM_FAMILY = ["AELSTM", "BiLSTM", "LSTM", "GRU", "RNN", "CNN", "RF", "SVM"]

# (site, year) folds flagged as genuine outliers: median-R2 z-score < -1.0
# *and* a practically large R2 drop (excludes high_amplitude_deciduous's
# 2020/2021, which are statistically "low" for that pixel but still R2>0.92 -
# noise around an already-excellent baseline, not a real difficulty).
OUTLIER_FOLDS = [("evergreen", 2012), ("low_amplitude", 2018)]


def model_color(model):
    if model in AELSTM_MODEL_COLORS:
        return AELSTM_MODEL_COLORS[model]
    return pu.ZERO_SHOT_COLOR if model == "zero_shot" else pu.FINETUNED_COLOR


def load_all():
    return pd.read_csv(OUTPUT_DIR / "loyo_all_folds.csv")


def full_summary_stats(df):
    stats = df.groupby(["site", "model"])["R2"].agg(["mean", "median", "std", "min", "max"]).round(4)
    stats.columns = [f"R2_{c}" for c in stats.columns]
    for m in ["RMSE", "MAE", "Pearson_r", "ACC"]:
        s = df.groupby(["site", "model"])[m].agg(["mean", "median", "std", "min", "max"]).round(4)
        s.columns = [f"{m}_{c}" for c in s.columns]
        stats = stats.join(s)
    stats = stats.reset_index()
    stats["model"] = pd.Categorical(stats["model"], categories=pu.ALL_MODEL_ORDER, ordered=True)
    return stats.sort_values(["site", "model"])


def year_difficulty(df):
    year_med = df.groupby(["site", "test_year"])["R2"].median().reset_index()
    year_med["z"] = year_med.groupby("site")["R2"].transform(lambda x: (x - x.mean()) / x.std())
    return year_med


def print_findings(df, stats, year_med):
    print("=" * 70)
    print("FULL SUMMARY STATISTICS (R2), per site/model")
    print("=" * 70)
    for site in cp.SITES:
        print(f"\n--- {site} ---")
        s = stats[stats.site == site][["model", "R2_mean", "R2_median", "R2_std", "R2_min", "R2_max"]]
        print(s.to_string(index=False))

    print("\n" + "=" * 70)
    print("YEAR DIFFICULTY (median R2 across all 10 models, z-score within site)")
    print("=" * 70)
    print(year_med.sort_values("z").to_string(index=False))

    df = df.copy()
    df["rank"] = df.groupby(["site", "test_year"])["R2"].rank(ascending=False)
    print("\n" + "=" * 70)
    print("CROSS-SITE RANK CONSISTENCY (rank 1=best, out of 10, across all 33 folds)")
    print("=" * 70)
    overall = df.groupby("model")["rank"].agg(["mean", "std", "min", "max"]).round(2)
    overall = overall.reindex(pu.ALL_MODEL_ORDER).sort_values("mean")
    top3 = df[df["rank"] <= 3].groupby("model").size().reindex(overall.index, fill_value=0)
    bot3 = df[df["rank"] >= 8].groupby("model").size().reindex(overall.index, fill_value=0)
    overall["top3_of_33"] = top3
    overall["bottom3_of_33"] = bot3
    print(overall.to_string())

    print("\n" + "=" * 70)
    print("CHRONOS-2 IN DIFFICULT vs. NORMAL FOLDS")
    print("=" * 70)
    difficult_set = set(OUTLIER_FOLDS)
    df["is_difficult"] = df.apply(lambda r: (r["site"], r["test_year"]) in difficult_set, axis=1)
    aelstm_fold_mean = df[df.model.isin(AELSTM_FAMILY)].groupby(["site", "test_year"])["R2"].mean()
    aelstm_fold_mean.name = "aelstm_mean"
    merged = df.merge(aelstm_fold_mean, on=["site", "test_year"])
    merged["advantage_vs_aelstm_family"] = merged["R2"] - merged["aelstm_mean"]
    for model in ["zero_shot", "finetuned_lora"]:
        sub = merged[merged.model == model]
        print(f"\n{model}:")
        print(sub.groupby("is_difficult")[["rank", "advantage_vs_aelstm_family"]].mean().round(3).to_string())
    print("\nPer-outlier-fold detail (Chronos-2's exact rank of 10):")
    for site, year in OUTLIER_FOLDS:
        sub = df[(df.site == site) & (df.test_year == year)].sort_values("rank")
        cz = sub[sub.model.isin(["zero_shot", "finetuned_lora"])]
        print(f"  {site}/{year}: zero_shot rank={int(cz[cz.model=='zero_shot']['rank'].iloc[0])}, "
              f"finetuned_lora rank={int(cz[cz.model=='finetuned_lora']['rank'].iloc[0])} (of 10)")


def plot_r2_distributions(df):
    fig, axes = plt.subplots(1, 3, figsize=(18, 6), constrained_layout=True)
    for ax, site in zip(axes, cp.SITES):
        sub = df[df.site == site]
        data = [sub[sub.model == m]["R2"].values for m in pu.ALL_MODEL_ORDER]
        bp = ax.boxplot(data, tick_labels=pu.ALL_MODEL_ORDER, patch_artist=True, showmeans=True,
                         medianprops=dict(color="black", linewidth=1.8),
                         meanprops=dict(marker="D", markerfacecolor="white", markeredgecolor="black", markersize=5))
        for patch, model in zip(bp["boxes"], pu.ALL_MODEL_ORDER):
            patch.set_facecolor(model_color(model))
            patch.set_alpha(0.75)
        ax.axhline(0, color="black", linewidth=0.8, linestyle=":")
        ax.set_xticklabels(pu.ALL_MODEL_ORDER, rotation=40, ha="right")
        ax.set_title(site, loc="left")
        ax.set_ylabel("R² across 11 held-out years" if site == cp.SITES[0] else "")
    fig.suptitle("Distribution of R² across 11 held-out years, per model and pixel "
                  "(box=IQR, line=median, diamond=mean)", fontsize=pu.FONT_SIZES["title"])
    pu.save_fig(fig, OUTPUT_DIR, "loyo_r2_distributions")


def plot_ranking_frequency(df):
    df = df.copy()
    df["rank"] = df.groupby(["site", "test_year"])["R2"].rank(ascending=False)
    order = df.groupby("model")["rank"].mean().reindex(pu.ALL_MODEL_ORDER).sort_values().index.tolist()

    top3 = df[df["rank"] <= 3].groupby("model").size().reindex(order, fill_value=0)
    mid = df[(df["rank"] > 3) & (df["rank"] < 8)].groupby("model").size().reindex(order, fill_value=0)
    bot3 = df[df["rank"] >= 8].groupby("model").size().reindex(order, fill_value=0)

    fig, ax = plt.subplots(figsize=(11, 6.5), constrained_layout=True)
    x = np.arange(len(order))
    ax.bar(x, top3, label="Top-3 finish", color="#1B7837")
    ax.bar(x, mid, bottom=top3, label="Middle (4th-7th)", color="#BBBBBB")
    ax.bar(x, bot3, bottom=top3 + mid, label="Bottom-3 finish", color="#B2182B")
    ax.set_xticks(x)
    ax.set_xticklabels(order, rotation=30, ha="right")
    ax.set_ylabel("Number of folds (out of 33 = 3 pixels x 11 held-out years)")
    ax.set_title("Ranking frequency across all 33 LOYO-CV folds, ordered by mean rank (best to worst)", loc="left")
    ax.legend(frameon=False)
    pu.save_fig(fig, OUTPUT_DIR, "loyo_ranking_frequency")


def plot_year_difficulty_heatmap(year_med):
    pivot = year_med.pivot(index="site", columns="test_year", values="z").reindex(cp.SITES)
    fig, ax = plt.subplots(figsize=(11, 3.2), constrained_layout=True)
    im = ax.imshow(pivot.values, aspect="auto", cmap="RdBu", vmin=-3, vmax=3)
    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels(pivot.columns, rotation=45)
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels(pivot.index)
    for i in range(pivot.shape[0]):
        for j in range(pivot.shape[1]):
            v = pivot.values[i, j]
            if v < -1.0:
                ax.text(j, i, f"{v:.1f}", ha="center", va="center", fontsize=9, fontweight="bold")
    ax.set_title("Year difficulty: z-score of median R² across all 10 models, within each pixel "
                 "(red = harder than that pixel's typical year)", loc="left", fontsize=12)
    fig.colorbar(im, ax=ax, label="z-score")
    pu.save_fig(fig, OUTPUT_DIR, "loyo_year_difficulty_heatmap")


def plot_outlier_investigation():
    fig, axes = plt.subplots(1, 2, figsize=(15, 5.5), constrained_layout=True)

    cases = [
        ("evergreen", 2012, 2000, axes[0], "2011-2012 US Southeast drought"),
        ("low_amplitude", 2018, 2006, axes[1], "erratic, non-seasonal LAI trajectory"),
    ]
    for site, year, window_start, ax, note in cases:
        raw = pd.read_csv(AELSTM_DATA_DIR / f"{site}.csv", parse_dates=["date"])
        raw["year"] = raw["date"].dt.year
        train = raw[(raw.year >= window_start) & (raw.year < year)]
        actual = raw[raw.year == year]

        clim = circular_doy_climatology(train, actual["date"])
        ax.plot(actual["date"], clim, color="#555555", linewidth=2.4, linestyle="--",
                label=f"{window_start}-{year - 1} climatology")
        ax.plot(actual["date"], actual[cp.TARGET_COL], color="#B2182B", linewidth=2.4, marker="o",
                markersize=4, label=f"{year} actual")
        ax.set_title(f"{site}: held-out {year} vs. its {window_start}-{year - 1} training climatology\n({note})",
                     loc="left", fontsize=11)
        ax.set_ylabel("LAI")
        ax.legend(frameon=False, fontsize=9)

    fig.suptitle("Why the two flagged outlier folds fail: actual LAI vs. what training data led every model to expect",
                 fontsize=pu.FONT_SIZES["title"])
    pu.save_fig(fig, OUTPUT_DIR, "loyo_outlier_fold_investigation")


def main():
    df = load_all()
    stats = full_summary_stats(df)
    stats.to_csv(OUTPUT_DIR / "loyo_summary_mean_std.csv", index=False)  # extends the existing file with min/max

    year_med = year_difficulty(df)
    print_findings(df, stats, year_med)

    plot_r2_distributions(df)
    plot_ranking_frequency(df)
    plot_year_difficulty_heatmap(year_med)
    plot_outlier_investigation()
    print(f"\nSaved analysis figures to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
