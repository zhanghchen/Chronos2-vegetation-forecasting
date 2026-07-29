# Recomputes the 8 AELSTM-family models' metrics against the RAW observed
# LAI (instead of the Savitzky-Golay-smoothed target their own pipeline
# reports as "ground_truth"), so the comparison against Chronos-2 (which
# was always evaluated against raw observations) is genuinely apples-to-
# apples. Also builds one summary figure per pixel overlaying all 10
# methods (8 AELSTM-family + Chronos-2 zero-shot + LoRA fine-tuned) against
# the raw observations, plus a consolidated CSV of every method's
# predictions. Uses each model's already-saved predictions - no
# retraining. Only reads AELSTM's saved files; never modifies them.
import argparse
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt

import common_pipeline as cp
import plotting_utils as pu

AELSTM_DATA = Path(__file__).resolve().parent.parent.parent / "AELSTM" / "data" / "processed" / "sites"
AELSTM_OUTPUTS = Path(__file__).resolve().parent.parent.parent / "AELSTM" / "outputs" / "model_comparison"
AELSTM_MODELS = ["AELSTM", "BiLSTM", "LSTM", "GRU", "RNN", "CNN", "RF", "SVM"]
AELSTM_MODEL_COLORS = {
    "AELSTM": "#000000", "BiLSTM": "#E69F00", "LSTM": "#56B4E9", "GRU": "#009E73",
    "RNN": "#F0E442", "CNN": "#0072B2", "RF": "#D55E00", "SVM": "#CC79A7",
}
FINAL_COMPARISON_DIR = cp.OUTPUTS_ROOT / "final_comparison"


def raw_ground_truth(site):
    df = pd.read_csv(AELSTM_DATA / f"{site}.csv", parse_dates=["date"])
    df = df[df["date"].dt.year == cp.TEST_YEAR]
    lat, lon = float(df["lat"].iloc[0]), float(df["lon"].iloc[0])
    gt = df[["date", "LAI"]].rename(columns={"LAI": "raw_ground_truth"}).reset_index(drop=True)
    return gt, lat, lon


def recompute_aelstm_metrics(site):
    raw_gt, _, _ = raw_ground_truth(site)
    rows = []
    for model in AELSTM_MODELS:
        preds = pd.read_csv(AELSTM_OUTPUTS / site / model / "predictions.csv", parse_dates=["date"])
        original_gt_rmse = ((preds["ground_truth"] - preds["prediction"]) ** 2).mean() ** 0.5

        merged = preds[["date", "prediction"]].merge(raw_gt, on="date", how="inner")
        metrics = cp.compute_metrics(merged["raw_ground_truth"], merged["prediction"])
        metrics.update(site=site, model=model, mode="AELSTM-project (vs. raw obs.)",
                        RMSE_vs_smoothed_target=original_gt_rmse)
        rows.append(metrics)
    return pd.DataFrame(rows)


def build_all_methods_table(site, raw_gt, lat, lon):
    table = raw_gt.copy()
    for model in AELSTM_MODELS:
        preds = pd.read_csv(AELSTM_OUTPUTS / site / model / "predictions.csv", parse_dates=["date"])[["date", "prediction"]]
        table[model] = table[["date"]].merge(preds, on="date", how="left")["prediction"].values
    for mode, col in [("zero_shot", "Chronos-2 (zero-shot)"), ("finetuned_lora", "Chronos-2 (LoRA fine-tuned)")]:
        preds = pd.read_csv(cp.OUTPUTS_ROOT / mode / site / "predictions.csv", parse_dates=["date"])[["date", "prediction"]]
        table[col] = table[["date"]].merge(preds, on="date", how="left")["prediction"].values
    table.insert(0, "lon", lon)
    table.insert(0, "lat", lat)
    table.insert(0, "site", site)
    return table


def plot_all_methods(site, table, lat, lon):
    ns = "N" if lat >= 0 else "S"
    ew = "E" if lon >= 0 else "W"

    fig, ax = plt.subplots(figsize=(13, 6.5), constrained_layout=True)
    ax.plot(table["date"], table["raw_ground_truth"], color=pu.GROUND_TRUTH_COLOR,
            linewidth=3.0, label="Observed (raw)", zorder=20)

    for model in AELSTM_MODELS:
        is_aelstm = model == "AELSTM"
        ax.plot(table["date"], table[model], color=AELSTM_MODEL_COLORS[model],
                linewidth=2.6 if is_aelstm else 1.6, alpha=0.95 if is_aelstm else 0.75,
                zorder=10 if is_aelstm else 5, label=model)

    ax.plot(table["date"], table["Chronos-2 (zero-shot)"], color=pu.ZERO_SHOT_COLOR,
            linewidth=2.8, zorder=15, label="Chronos-2 (zero-shot)")
    ax.plot(table["date"], table["Chronos-2 (LoRA fine-tuned)"], color=pu.FINETUNED_COLOR,
            linewidth=2.8, linestyle="--", zorder=15, label="Chronos-2 (LoRA fine-tuned)")

    ax.set_title(f"{site}  —  {abs(lat):.4f}°{ns}, {abs(lon):.4f}°{ew}  "
                 f"— all methods vs. raw observed LAI ({cp.TEST_YEAR})", loc="left", fontsize=13)
    ax.set_xlabel("Date")
    ax.set_ylabel("LAI")
    ax.legend(frameon=False, ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.12), fontsize=9.5)
    pu.save_fig(fig, FINAL_COMPARISON_DIR / site, "all_methods_vs_raw_obs")


def build_final_comparison(sites):
    """One figure per pixel with all 10 methods vs. raw observations, plus
    one consolidated CSV across all requested sites."""
    tables = []
    for site in sites:
        raw_gt, lat, lon = raw_ground_truth(site)
        table = build_all_methods_table(site, raw_gt, lat, lon)
        plot_all_methods(site, table, lat, lon)
        tables.append(table)
        print(f"[{site}] lat={lat:.4f}, lon={lon:.4f} — saved final_comparison/{site}/all_methods_vs_raw_obs.{{png,pdf}}")

    combined = pd.concat(tables, ignore_index=True)
    FINAL_COMPARISON_DIR.mkdir(parents=True, exist_ok=True)
    combined.to_csv(FINAL_COMPARISON_DIR / "all_methods_vs_raw_obs.csv", index=False)
    print(f"Saved consolidated all_methods_vs_raw_obs.csv ({len(combined)} rows) to {FINAL_COMPARISON_DIR}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sites", nargs="+", default=cp.SITES)
    args = parser.parse_args()

    aelstm_corrected = pd.concat([recompute_aelstm_metrics(s) for s in args.sites], ignore_index=True)

    chronos2 = pd.read_csv(cp.OUTPUTS_ROOT / "chronos2_all_results.csv").rename(columns={"mode": "model"})
    chronos2["mode"] = "Chronos-2 (vs. raw obs.)"

    combined = pd.concat([
        aelstm_corrected[["site", "mode", "model", "RMSE", "MAE", "MAPE", "R2", "Pearson_r"]],
        chronos2[["site", "mode", "model", "RMSE", "MAE", "MAPE", "R2", "Pearson_r"]],
    ], ignore_index=True)
    combined.to_csv(cp.OUTPUTS_ROOT / "fair_comparison_vs_raw_observations.csv", index=False)

    for site in args.sites:
        sub = combined[combined.site == site].sort_values("R2", ascending=False)
        print(f"\n=== {site}: all 10 methods ranked by R2, ALL vs. raw observed LAI ===")
        print(sub[["model", "RMSE", "R2", "Pearson_r"]].to_string(index=False))

    rank_pivot = combined.pivot(index="model", columns="site", values="R2")[args.sites]
    rank_pivot = rank_pivot.reindex(pu.ALL_MODEL_ORDER)
    rank = rank_pivot.rank(ascending=False, axis=0)
    rank["mean_rank"] = rank.mean(axis=1)
    rank["std_rank"] = rank[args.sites].std(axis=1)
    rank = rank.sort_values("mean_rank")
    rank.to_csv(cp.OUTPUTS_ROOT / "fair_comparison_rank_consistency.csv")
    print("\n=== Corrected rank (1=best R2), ALL methods vs. raw observations ===")
    print(rank.round(2).to_string())

    print(f"\nSaved fair_comparison_vs_raw_observations.csv and "
          f"fair_comparison_rank_consistency.csv to {cp.OUTPUTS_ROOT}")

    build_final_comparison(args.sites)


if __name__ == "__main__":
    main()
