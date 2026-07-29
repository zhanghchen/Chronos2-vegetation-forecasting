# Builds (1) a combined zero-shot + LoRA fine-tuned plot per pixel, and
# (2) a comparison table/plot against the AELSTM project's 8 models. This
# script only *reads* the AELSTM project's already-saved CSV outputs (for
# reporting purposes) - it never imports AELSTM code or writes into its
# directory, keeping the two projects independent as required.
import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

import common_pipeline as cp
import plotting_utils as pu

AELSTM_OUTPUTS = Path(__file__).resolve().parent.parent.parent / "AELSTM" / "outputs" / "model_comparison"


def combined_plot(site):
    zs = pd.read_csv(cp.OUTPUTS_ROOT / "zero_shot" / site / "predictions.csv", parse_dates=["date"])
    ft = pd.read_csv(cp.OUTPUTS_ROOT / "finetuned_lora" / site / "predictions.csv", parse_dates=["date"])

    output_dir = cp.OUTPUTS_ROOT / "combined" / site
    pu.plot_prediction_multi(
        zs["date"], zs["ground_truth"],
        [("Zero-shot", zs["prediction"], pu.ZERO_SHOT_COLOR),
         ("LoRA fine-tuned", ft["prediction"], pu.FINETUNED_COLOR)],
        f"{site} — Chronos-2 predicted vs. observed LAI, {cp.TEST_YEAR}",
        output_dir, "prediction_plot_combined",
    )


def build_consolidated_predictions(sites):
    """Wide-format CSV: site, date, ground_truth, zero_shot, finetuned_lora -
    mirrors the AELSTM project's observed_vs_predicted_all_models.csv."""
    rows = []
    for site in sites:
        zs = pd.read_csv(cp.OUTPUTS_ROOT / "zero_shot" / site / "predictions.csv", parse_dates=["date"])
        ft = pd.read_csv(cp.OUTPUTS_ROOT / "finetuned_lora" / site / "predictions.csv", parse_dates=["date"])
        table = zs[["date", "ground_truth"]].copy()
        table["zero_shot"] = zs["prediction"].values
        table["finetuned_lora"] = ft["prediction"].values
        table.insert(0, "site", site)
        rows.append(table)

    combined = pd.concat(rows, ignore_index=True)
    combined.to_csv(cp.OUTPUTS_ROOT / "observed_vs_predicted_chronos2.csv", index=False)
    return combined


def build_rank_consistency(all_results, sites):
    """Mirrors AELSTM's cross_pixel_rank_consistency.csv: rank (1=best R2)
    per model per site, plus mean/std rank across sites."""
    pivot = all_results.pivot(index="model", columns="site", values="R2")[sites]
    pivot = pivot.reindex(pu.ALL_MODEL_ORDER)
    rank = pivot.rank(ascending=False, axis=0)
    rank["mean_rank"] = rank.mean(axis=1)
    rank["std_rank"] = rank[sites].std(axis=1)
    rank = rank.sort_values("mean_rank")
    rank.to_csv(cp.OUTPUTS_ROOT / "all_models_rank_consistency.csv")
    return rank


def plot_all_models_bars(all_results, sites):
    """Grouped bar chart of R2 per model, one bar-group per site - mirrors
    AELSTM's cross_pixel_r2_bars.png, extended to include Chronos-2."""
    r2_pivot = all_results.pivot(index="model", columns="site", values="R2")[sites].reindex(pu.ALL_MODEL_ORDER)

    fig, ax = plt.subplots(figsize=(14, 6), constrained_layout=True)
    n_sites = len(sites)
    x = np.arange(len(pu.ALL_MODEL_ORDER))
    width = 0.8 / n_sites
    site_palette = [plt.cm.tab10(i) for i in range(n_sites)]

    for i, site in enumerate(sites):
        ax.bar(x + i * width - (n_sites - 1) * width / 2, r2_pivot[site].values, width,
               label=site, color=site_palette[i])

    ax.set_xticks(x)
    ax.set_xticklabels(pu.ALL_MODEL_ORDER, rotation=20, ha="right")
    ax.set_ylabel("R²")
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_title("AELSTM-family models + Chronos-2 (zero-shot / LoRA): R² across pixels")
    ax.legend(frameon=False, ncol=min(n_sites, 3))
    pu.save_fig(fig, cp.OUTPUTS_ROOT, "all_models_r2_bars")


def load_aelstm_metrics(site):
    path = AELSTM_OUTPUTS / site / "comparison_metrics.csv"
    if not path.exists():
        print(f"Note: no AELSTM results found for site '{site}' at {path}; skipping in comparison.")
        return None
    df = pd.read_csv(path)
    df = df.rename(columns={"Model": "model"})
    df["site"] = site
    df["mode"] = "AELSTM-project"
    return df


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sites", nargs="+", default=cp.SITES)
    args = parser.parse_args()

    for site in args.sites:
        combined_plot(site)
        print(f"Saved combined plot for {site}")

    chronos2_results = pd.read_csv(cp.OUTPUTS_ROOT / "chronos2_all_results.csv")
    chronos2_results = chronos2_results.rename(columns={"mode": "model"})
    chronos2_results["mode"] = "Chronos-2"

    aelstm_frames = [load_aelstm_metrics(s) for s in args.sites]
    aelstm_frames = [f for f in aelstm_frames if f is not None]

    all_results = pd.concat([chronos2_results] + aelstm_frames, ignore_index=True)
    all_results = all_results[["site", "mode", "model", "RMSE", "MAE", "MAPE", "R2", "Pearson_r"]]
    all_results.to_csv(cp.OUTPUTS_ROOT / "chronos2_vs_aelstm.csv", index=False)

    for site in args.sites:
        sub = all_results[all_results["site"] == site].sort_values("R2", ascending=False)
        print(f"\n=== {site}: all models ranked by R2 ===")
        print(sub[["model", "mode", "RMSE", "R2", "Pearson_r"]].to_string(index=False))

    preds = build_consolidated_predictions(args.sites)
    print(f"\nSaved observed_vs_predicted_chronos2.csv ({len(preds)} rows)")

    rank_table = build_rank_consistency(all_results, args.sites)
    print("\n=== Rank (1=best R2) by model x site, all 10 methods ===")
    print(rank_table.round(2).to_string())

    plot_all_models_bars(all_results, args.sites)
    print("Saved all_models_r2_bars.{png,pdf}")

    print(f"\nSaved chronos2_vs_aelstm.csv to {cp.OUTPUTS_ROOT}")


if __name__ == "__main__":
    main()
