# Consolidates the predictor-ablation results from both projects (AELSTM's
# 8 models - AELSTM/outputs/predictor_ablation/ - and this project's
# Chronos-2 zero-shot - outputs/predictor_ablation/) against each method's
# already-computed full-7-predictor baseline (never rerun here), into one
# long-format table with delta metrics, a predictor-importance ranking, and
# figures answering: which predictors matter most, whether different models
# depend on different predictors, whether importance shifts across
# vegetation types, and whether the Phase-2 reduced sets maintain or improve
# performance. Reads only already-saved files; never writes into AELSTM's
# directory; no retraining.
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

import common_pipeline as cp
import plotting_utils as pu
from build_fair_comparison import AELSTM_MODEL_COLORS

AELSTM_ROOT = Path(__file__).resolve().parent.parent.parent / "AELSTM"
AELSTM_ABLATION_DIR = AELSTM_ROOT / "outputs" / "predictor_ablation"
AELSTM_BASELINE_DIR = AELSTM_ROOT / "outputs" / "model_comparison"
CHRONOS2_ABLATION_DIR = cp.OUTPUTS_ROOT / "predictor_ablation"

OUTPUT_DIR = CHRONOS2_ABLATION_DIR / "comparison"
SITES = cp.SITES
ALL_PREDICTORS = ["tmmx", "tmmn", "pr", "srad", "vpd", "sph", "vs"]
LOPO_CONFIGS = [f"no_{p}" for p in ALL_PREDICTORS]
PHASE2_CONFIGS = ["top3_essential", "drop_least_important_pair", "no_temperature", "no_moisture"]
ALL_METHOD_ORDER = pu.ALL_MODEL_ORDER[:8] + ["zero_shot"]  # 8 AELSTM-family + zero-shot (no LoRA here)


def load_baseline():
    rows = []
    for site in SITES:
        b = pd.read_csv(AELSTM_BASELINE_DIR / site / "comparison_metrics_vs_raw_observations.csv")
        b = b.rename(columns={"model": "model"})
        b["site"] = site
        rows.append(b[["site", "model", "RMSE", "MAE", "R2", "Pearson_r"]])
        with open(cp.OUTPUTS_ROOT / "zero_shot" / site / "metrics.txt") as f:
            metrics = {}
            for line in f:
                k, v = line.strip().split(": ")
                metrics[k] = float(v)
        rows.append(pd.DataFrame([{"site": site, "model": "zero_shot", "RMSE": metrics["RMSE"],
                                    "MAE": metrics["MAE"], "R2": metrics["R2"], "Pearson_r": metrics["Pearson_r"]}]))
    baseline = pd.concat(rows, ignore_index=True)
    return baseline.rename(columns={c: f"baseline_{c}" for c in ["RMSE", "MAE", "R2", "Pearson_r"]})


def load_ablation():
    aelstm = pd.read_csv(AELSTM_ABLATION_DIR / "all_ablation_results.csv")[
        ["site", "model", "predictor_set", "n_predictors", "predictors", "RMSE", "MAE", "R2", "Pearson_r"]]
    chronos2 = pd.read_csv(CHRONOS2_ABLATION_DIR / "all_ablation_results.csv")[
        ["site", "model", "predictor_set", "n_predictors", "predictors", "RMSE", "MAE", "R2", "Pearson_r"]]
    return pd.concat([aelstm, chronos2], ignore_index=True)


def model_color(model):
    return AELSTM_MODEL_COLORS.get(model, pu.ZERO_SHOT_COLOR)


def build_long_table(ablation, baseline):
    merged = ablation.merge(baseline, on=["site", "model"])
    for m in ["RMSE", "MAE", "R2", "Pearson_r"]:
        merged[f"delta_{m}"] = merged[m] - merged[f"baseline_{m}"]
    merged.to_csv(OUTPUT_DIR / "predictor_ablation_all_results.csv", index=False)
    return merged


def build_importance_ranking(merged):
    lopo = merged[merged.predictor_set.isin(LOPO_CONFIGS)].copy()
    lopo["dropped_predictor"] = lopo["predictor_set"].str.replace("no_", "", regex=False)
    ranking = lopo.groupby("dropped_predictor")["delta_R2"].agg(["mean", "std", "min", "max", "count"])
    ranking = ranking.sort_values("mean")
    ranking.to_csv(OUTPUT_DIR / "predictor_importance_ranking.csv")
    return lopo, ranking


def plot_importance_bar(ranking):
    fig, ax = plt.subplots(figsize=(10, 6), constrained_layout=True)
    order = ranking.index.tolist()
    colors = ["#B2182B" if v < 0 else "#1B7837" for v in ranking["mean"]]
    ax.barh(order, ranking["mean"], xerr=ranking["std"], color=colors, capsize=3)
    ax.axvline(0, color="black", linewidth=0.9)
    ax.set_xlabel("Mean ΔR² when predictor is removed (across 9 methods × 3 pixels)")
    ax.set_title("Predictor importance ranking (leave-one-predictor-out)", loc="left")
    ax.invert_yaxis()
    pu.save_fig(fig, OUTPUT_DIR, "predictor_importance_ranking")


def plot_model_predictor_heatmap(lopo):
    fig, axes = plt.subplots(1, len(SITES), figsize=(6.5 * len(SITES), 5.5), constrained_layout=True)
    for ax, site in zip(axes, SITES):
        sub = lopo[lopo.site == site]
        pivot = sub.pivot(index="dropped_predictor", columns="model", values="delta_R2")
        pivot = pivot.reindex(index=ALL_PREDICTORS, columns=[m for m in ALL_METHOD_ORDER if m in pivot.columns])
        im = ax.imshow(pivot.values, aspect="auto", cmap="RdYlGn", vmin=-0.15, vmax=0.15)
        ax.set_xticks(range(len(pivot.columns)))
        ax.set_xticklabels(pivot.columns, rotation=45, ha="right", fontsize=8)
        ax.set_yticks(range(len(pivot.index)))
        ax.set_yticklabels(pivot.index)
        ax.set_title(site, loc="left", fontsize=11)
        fig.colorbar(im, ax=ax, label="ΔR²", shrink=0.8)
    fig.suptitle("ΔR² when each predictor is removed, by model and pixel "
                 "(red = removing it hurts; green = removing it helps)", fontsize=pu.FONT_SIZES["title"])
    pu.save_fig(fig, OUTPUT_DIR, "predictor_model_pixel_heatmap")


def plot_pixel_importance(lopo):
    fig, ax = plt.subplots(figsize=(10, 6), constrained_layout=True)
    pivot = lopo.groupby(["dropped_predictor", "site"])["delta_R2"].mean().unstack("site")
    pivot = pivot.reindex(ALL_PREDICTORS)[SITES]
    x = np.arange(len(ALL_PREDICTORS))
    width = 0.8 / len(SITES)
    palette = [plt.cm.tab10(i) for i in range(len(SITES))]
    for i, site in enumerate(SITES):
        ax.bar(x + i * width - (len(SITES) - 1) * width / 2, pivot[site], width, label=site, color=palette[i])
    ax.axhline(0, color="black", linewidth=0.9)
    ax.set_xticks(x)
    ax.set_xticklabels(ALL_PREDICTORS)
    ax.set_ylabel("Mean ΔR² when removed (averaged across 9 methods)")
    ax.set_title("Predictor importance by pixel — does it shift by vegetation type?", loc="left")
    ax.legend(frameon=False)
    pu.save_fig(fig, OUTPUT_DIR, "predictor_importance_by_pixel")


def plot_reduced_sets(merged):
    phase2 = merged[merged.predictor_set.isin(PHASE2_CONFIGS)]
    fig, ax = plt.subplots(figsize=(11, 6), constrained_layout=True)
    pivot = phase2.groupby(["predictor_set", "site"])["delta_R2"].mean().unstack("site").reindex(PHASE2_CONFIGS)[SITES]
    x = np.arange(len(PHASE2_CONFIGS))
    width = 0.8 / len(SITES)
    palette = [plt.cm.tab10(i) for i in range(len(SITES))]
    for i, site in enumerate(SITES):
        ax.bar(x + i * width - (len(SITES) - 1) * width / 2, pivot[site], width, label=site, color=palette[i])
    ax.axhline(0, color="black", linewidth=0.9)
    ax.set_xticks(x)
    ax.set_xticklabels(["Top-3 essential\n(tmmx,tmmn,srad)", "Drop least-important\npair (vs,pr)",
                         "Drop temperature\npair (tmmx,tmmn)", "Drop moisture\npair (vpd,sph)"], fontsize=9)
    ax.set_ylabel("Mean ΔR² vs. full-7-predictor baseline (averaged across 9 methods)")
    ax.set_title("Phase 2: reduced predictor sets — does trimming redundancy help?", loc="left")
    ax.legend(frameon=False)
    pu.save_fig(fig, OUTPUT_DIR, "predictor_reduced_sets")

    summary = phase2.groupby(["predictor_set", "site"])[["delta_RMSE", "delta_R2"]].mean().round(4)
    summary.to_csv(OUTPUT_DIR / "reduced_sets_summary.csv")
    return summary


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    baseline = load_baseline()
    ablation = load_ablation()
    merged = build_long_table(ablation, baseline)
    print(f"Saved predictor_ablation_all_results.csv ({len(merged)} rows)")

    lopo, ranking = build_importance_ranking(merged)
    print("\n=== Predictor importance ranking (mean delta_R2, most -> least important) ===")
    print(ranking.round(4).to_string())

    plot_importance_bar(ranking)
    plot_model_predictor_heatmap(lopo)
    plot_pixel_importance(lopo)
    summary = plot_reduced_sets(merged)
    print("\n=== Phase 2 reduced-set results (mean delta vs. baseline) ===")
    print(summary.to_string())

    print(f"\nSaved all figures and tables to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
