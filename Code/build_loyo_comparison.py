# Consolidates the LOYO-CV results from both projects (AELSTM's 8 models -
# AELSTM/outputs/loyo_cv/ - and this project's 2 Chronos-2 variants -
# outputs/loyo_cv/) into one long-format table across all 10 methods, a
# per-(model, site) mean+std-across-folds summary, per-site rank-consistency
# tables, and figures comparing models across years and pixels. Every number
# in both source tables is already scored against RAW observed LAI (AELSTM's
# loyo_cv_experiment.py merges with raw obs directly; this project's data was
# never smoothed), so no additional ground-truth correction is needed here -
# unlike chronos2_vs_aelstm.csv's naive merge of the single-2022-split
# results. Reads only already-saved fold CSVs from both projects; never
# writes into AELSTM's directory; no retraining.
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

import common_pipeline as cp
import plotting_utils as pu
from build_fair_comparison import AELSTM_MODEL_COLORS

AELSTM_LOYO_DIR = Path(__file__).resolve().parent.parent.parent / "AELSTM" / "outputs" / "loyo_cv"
CHRONOS2_LOYO_DIR = cp.OUTPUTS_ROOT / "loyo_cv"
OUTPUT_DIR = CHRONOS2_LOYO_DIR / "comparison"

CORE_COLS = ["site", "model", "test_year", "RMSE", "MAE", "MAPE", "R2", "Pearson_r", "ACC"]
METRICS = ["RMSE", "MAE", "MAPE", "R2", "Pearson_r", "ACC"]


def load_all(sites):
    frames = []
    for site in sites:
        aelstm = pd.read_csv(AELSTM_LOYO_DIR / site / "all_folds_metrics.csv")
        frames.append(aelstm[CORE_COLS])

        chronos2 = pd.read_csv(CHRONOS2_LOYO_DIR / site / "all_folds_metrics.csv").rename(columns={"mode": "model"})
        frames.append(chronos2[CORE_COLS])
    return pd.concat(frames, ignore_index=True)


def build_summary(all_df):
    agg = {}
    for m in METRICS:
        agg[f"mean_{m}"] = (m, "mean")
        agg[f"std_{m}"] = (m, "std")
        agg[f"median_{m}"] = (m, "median")
    summary = all_df.groupby(["site", "model"]).agg(**agg, n_folds=("test_year", "count")).reset_index()
    summary["model"] = pd.Categorical(summary["model"], categories=pu.ALL_MODEL_ORDER, ordered=True)
    return summary.sort_values(["site", "model"]).reset_index(drop=True)


def build_rank_consistency(all_df, site):
    sub = all_df[all_df.site == site]
    pivot = sub.pivot(index="model", columns="test_year", values="R2").reindex(pu.ALL_MODEL_ORDER)
    year_cols = pivot.columns.tolist()
    rank = pivot.rank(ascending=False, axis=0)
    rank["mean_rank"] = rank[year_cols].mean(axis=1)
    rank["std_rank"] = rank[year_cols].std(axis=1)
    return rank.sort_values("mean_rank")


def model_color(model):
    if model in AELSTM_MODEL_COLORS:
        return AELSTM_MODEL_COLORS[model]
    return pu.ZERO_SHOT_COLOR if model == "zero_shot" else pu.FINETUNED_COLOR


def plot_r2_by_year(all_df, site):
    sub = all_df[all_df.site == site]
    fig, ax = plt.subplots(figsize=(12, 6.5), constrained_layout=True)
    for model in pu.ALL_MODEL_ORDER:
        m = sub[sub.model == model].sort_values("test_year")
        is_chronos2 = model in ("zero_shot", "finetuned_lora")
        ax.plot(m["test_year"], m["R2"], marker="o", markersize=4,
                color=model_color(model), linewidth=2.6 if is_chronos2 else 1.6,
                linestyle="--" if model == "finetuned_lora" else "-",
                alpha=0.95 if (is_chronos2 or model == "AELSTM") else 0.8, label=model)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xlabel("Held-out test year")
    ax.set_ylabel("R²")
    ax.set_title(f"{site} — LOYO-CV: R² by held-out year, fixed 12-year training window", loc="left")
    ax.legend(frameon=False, ncol=5, loc="upper center", bbox_to_anchor=(0.5, -0.12), fontsize=9)
    pu.save_fig(fig, OUTPUT_DIR, f"loyo_r2_by_year_{site}")


def plot_r2_heatmap(all_df, site):
    sub = all_df[all_df.site == site]
    pivot = sub.pivot(index="model", columns="test_year", values="R2").reindex(pu.ALL_MODEL_ORDER)

    fig, ax = plt.subplots(figsize=(10, 6), constrained_layout=True)
    im = ax.imshow(pivot.values, aspect="auto", cmap="RdYlGn", vmin=-0.5, vmax=1.0)
    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels(pivot.columns, rotation=45)
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels(pivot.index)
    ax.set_xlabel("Held-out test year")
    ax.set_title(f"{site} — LOYO-CV: R² heatmap (model × held-out year)", loc="left")
    fig.colorbar(im, ax=ax, label="R²")
    pu.save_fig(fig, OUTPUT_DIR, f"loyo_r2_heatmap_{site}")


def plot_mean_r2_bars(summary, sites):
    fig, ax = plt.subplots(figsize=(14, 6.5), constrained_layout=True)
    n_sites = len(sites)
    x = np.arange(len(pu.ALL_MODEL_ORDER))
    width = 0.8 / n_sites
    site_palette = [plt.cm.tab10(i) for i in range(n_sites)]

    for i, site in enumerate(sites):
        s = summary[summary.site == site].set_index("model").reindex(pu.ALL_MODEL_ORDER)
        ax.bar(x + i * width - (n_sites - 1) * width / 2, s["mean_R2"], width,
               yerr=s["std_R2"], capsize=3, label=site, color=site_palette[i])

    ax.set_xticks(x)
    ax.set_xticklabels(pu.ALL_MODEL_ORDER, rotation=20, ha="right")
    ax.set_ylabel("Mean R² across 11 held-out years (error bars: std across years)")
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_title("LOYO-CV: mean ± std R² across held-out years, all 10 methods", loc="left")
    ax.legend(frameon=False, ncol=min(n_sites, 3))
    pu.save_fig(fig, OUTPUT_DIR, "loyo_mean_r2_bars")


def plot_median_r2_bars(summary, sites):
    """Companion to plot_mean_r2_bars(): the mean+/-std view is dominated by
    any single extreme fold (e.g. evergreen/2012's drought year - see
    COMPARISON note), which is real and shouldn't be hidden, but also
    shouldn't be the only view. Median R2 shows "typical held-out-year"
    performance instead."""
    fig, ax = plt.subplots(figsize=(14, 6.5), constrained_layout=True)
    n_sites = len(sites)
    x = np.arange(len(pu.ALL_MODEL_ORDER))
    width = 0.8 / n_sites
    site_palette = [plt.cm.tab10(i) for i in range(n_sites)]

    for i, site in enumerate(sites):
        s = summary[summary.site == site].set_index("model").reindex(pu.ALL_MODEL_ORDER)
        ax.bar(x + i * width - (n_sites - 1) * width / 2, s["median_R2"], width,
               label=site, color=site_palette[i])

    ax.set_xticks(x)
    ax.set_xticklabels(pu.ALL_MODEL_ORDER, rotation=20, ha="right")
    ax.set_ylabel("Median R² across 11 held-out years")
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_title("LOYO-CV: median R² across held-out years (robust to single-year outliers), all 10 methods", loc="left")
    ax.legend(frameon=False, ncol=min(n_sites, 3))
    pu.save_fig(fig, OUTPUT_DIR, "loyo_median_r2_bars")


def main():
    sites = cp.SITES
    all_df = load_all(sites)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    all_df.to_csv(OUTPUT_DIR / "loyo_all_folds.csv", index=False)
    print(f"Saved loyo_all_folds.csv ({len(all_df)} rows)")

    summary = build_summary(all_df)
    summary.to_csv(OUTPUT_DIR / "loyo_summary_mean_std.csv", index=False)
    print(f"Saved loyo_summary_mean_std.csv ({len(summary)} rows)")
    for site in sites:
        print(f"\n=== {site}: R2 across 11 held-out years (mean +/- std, median) ===")
        s = summary[summary.site == site][["model", "mean_R2", "std_R2", "median_R2"]]
        print(s.to_string(index=False))

    for site in sites:
        rank = build_rank_consistency(all_df, site)
        rank.to_csv(OUTPUT_DIR / f"loyo_rank_consistency_{site}.csv")
        plot_r2_by_year(all_df, site)
        plot_r2_heatmap(all_df, site)

    plot_mean_r2_bars(summary, sites)
    plot_median_r2_bars(summary, sites)
    print(f"\nSaved rank-consistency CSVs and figures to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
