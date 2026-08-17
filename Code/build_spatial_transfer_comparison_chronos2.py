# Builds the comparison figure/table for spatial_transfer_chronos2.py's
# output, plus a combined figure with AELSTM's 8-model spatial-transfer
# result. Reads only already-saved CSVs; no retraining.
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import common_pipeline as cp

SOURCE_SITE = "evergreen"
TARGET_SITE = "evergreen_west"
OUT = cp.OUTPUTS_ROOT / "spatial_transfer" / f"{SOURCE_SITE}_to_{TARGET_SITE}"
AELSTM_OUT = cp.DATA_DIR.parent / "AELSTM" / "outputs" / "spatial_transfer" / f"{SOURCE_SITE}_to_{TARGET_SITE}"

OBS_COLOR = "#2b2b2b"
ZS_COLOR = "#7a7a7a"
TRANSFER_COLOR = "#1f5c4a"


def build_summary(metrics):
    metrics = metrics.set_index("condition")
    all_results = pd.read_csv(cp.OUTPUTS_ROOT / "chronos2_all_results.csv")
    source_local_lora = all_results[(all_results.site == SOURCE_SITE) & (all_results["mode"] == "finetuned_lora")]["R2"].values[0]
    target_local_lora = all_results[(all_results.site == TARGET_SITE) & (all_results["mode"] == "finetuned_lora")]["R2"].values[0]

    rows = [
        {"condition": "zero_shot (target-native, reference)", "R2": metrics.loc["zero_shot_target_native", "R2"],
         "RMSE": metrics.loc["zero_shot_target_native", "RMSE"], "Pearson_r": metrics.loc["zero_shot_target_native", "Pearson_r"]},
        {"condition": f"LoRA, source-local ({SOURCE_SITE} trained+tested there)", "R2": source_local_lora,
         "RMSE": None, "Pearson_r": None},
        {"condition": f"LoRA, target-local ({TARGET_SITE} trained+tested there)", "R2": target_local_lora,
         "RMSE": None, "Pearson_r": None},
        {"condition": f"LoRA, transfer ({SOURCE_SITE}→{TARGET_SITE}, no retraining)",
         "R2": metrics.loc["lora_transfer_from_source", "R2"],
         "RMSE": metrics.loc["lora_transfer_from_source", "RMSE"],
         "Pearson_r": metrics.loc["lora_transfer_from_source", "Pearson_r"]},
    ]
    summary = pd.DataFrame(rows)
    summary.to_csv(OUT / "spatial_transfer_summary_chronos2.csv", index=False)
    print(summary.round(4).to_string(index=False))
    return summary


def plot_prediction_curves(preds, metrics):
    fig, ax = plt.subplots(figsize=(11, 5.5), constrained_layout=True)
    obs = preds[preds.condition == "zero_shot_target_native"][["date", "observed"]].drop_duplicates().sort_values("date")
    ax.plot(pd.to_datetime(obs.date), obs.observed, color=OBS_COLOR, linewidth=2.6,
            label=f"Observed ({TARGET_SITE})", zorder=4)

    zs = preds[preds.condition == "zero_shot_target_native"].sort_values("date")
    r2_zs = metrics.set_index("condition").loc["zero_shot_target_native", "R2"]
    ax.plot(pd.to_datetime(zs.date), zs.prediction, color=ZS_COLOR, linewidth=1.8, linestyle="--",
            marker="o", markersize=3, label=f"Zero-shot, target-native (R²={r2_zs:.2f})", zorder=2)

    tr = preds[preds.condition == "lora_transfer_from_source"].sort_values("date")
    r2_tr = metrics.set_index("condition").loc["lora_transfer_from_source", "R2"]
    ax.plot(pd.to_datetime(tr.date), tr.prediction, color=TRANSFER_COLOR, linewidth=2.0,
            marker="o", markersize=3.5, label=f"LoRA transfer, {SOURCE_SITE}→{TARGET_SITE} (R²={r2_tr:.2f})", zorder=3)

    ax.set_title(f"Chronos-2 spatial transfer: {SOURCE_SITE} → {TARGET_SITE}, 2022", loc="left", fontsize=12.5)
    ax.set_ylabel("LAI")
    ax.tick_params(axis="x", rotation=20)
    ax.legend(frameon=False, fontsize=9, loc="upper left")
    fig.savefig(OUT / "spatial_transfer_prediction_curves_chronos2.png", dpi=150, facecolor="white")
    plt.close(fig)


def plot_combined_r2(summary):
    """Side-by-side: 8 AELSTM models' R2 drop (transfer - target_local) vs. Chronos-2 LoRA's."""
    aelstm = pd.read_csv(AELSTM_OUT / "spatial_transfer_summary_table.csv")
    fig, ax = plt.subplots(figsize=(10.5, 6), constrained_layout=True)

    labels = list(aelstm.sort_values("drop_vs_target_local", ascending=False)["model"]) + ["Chronos-2\n(LoRA)"]
    target_local_lora = summary.loc[summary.condition.str.contains("target-local"), "R2"].values[0]
    transfer_lora = summary.loc[summary.condition.str.contains("transfer"), "R2"].values[0]
    chronos_drop = transfer_lora - target_local_lora
    drops = list(aelstm.sort_values("drop_vs_target_local", ascending=False)["drop_vs_target_local"]) + [chronos_drop]

    colors = ["#1f5c4a"] * (len(labels) - 1) + ["#c0562f"]
    ax.bar(range(len(labels)), drops, color=colors)
    ax.axhline(0, color="black", linewidth=1)
    ax.set_xticks(range(len(labels))); ax.set_xticklabels(labels)
    ax.set_ylabel("ΔR² (transfer − target-local)")
    ax.set_title("How much R² is lost under spatial transfer, by model", loc="left", fontsize=12.5)
    fig.savefig(OUT / "spatial_transfer_r2_drop_combined.png", dpi=150, facecolor="white")
    plt.close(fig)


def main():
    metrics = pd.read_csv(OUT / "transfer_metrics_chronos2.csv")
    preds = pd.read_csv(OUT / "transfer_predictions_chronos2.csv", parse_dates=["date"])
    summary = build_summary(metrics)
    plot_prediction_curves(preds, metrics)
    plot_combined_r2(summary)
    print(f"\nSaved figures + summary table to {OUT}")


if __name__ == "__main__":
    main()
