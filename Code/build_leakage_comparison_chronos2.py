# Builds the comparison figure and summary table for
# leakage_diagnostic_2012_chronos2.py's output, and a cross-project summary
# combining it with AELSTM's 8-model leakage diagnostic
# (../AELSTM/outputs/leakage_diagnostic_2012/). Reads only already-saved
# CSVs; no retraining.
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import common_pipeline as cp

SITE = "evergreen"
LEAK_YEAR = 2012
BASE = cp.OUTPUTS_ROOT / "leakage_diagnostic_2012" / SITE
AELSTM_BASE = cp.DATA_DIR.parent / "AELSTM" / "outputs" / "leakage_diagnostic_2012" / SITE

METRIC_COLS = ["RMSE", "MAE", "R2", "Pearson_r", "ACC"]
COND_ORDER = ["zero_shot", "finetuned_lora_original", "finetuned_lora_leakage"]
COND_LABELS = {"zero_shot": "Zero-shot (reference)",
               "finetuned_lora_original": "LoRA, 2012 unseen",
               "finetuned_lora_leakage": "LoRA, 2012 seen in training"}
COLORS = {"zero_shot": "#7a7a7a", "finetuned_lora_original": "#a8791f", "finetuned_lora_leakage": "#1f5c4a"}


def build_summary_table(metrics):
    metrics = metrics.set_index("condition").loc[COND_ORDER].reset_index()
    metrics.to_csv(BASE / "leakage_summary_table_chronos2.csv", index=False)
    print(metrics[["condition"] + METRIC_COLS].round(4).to_string(index=False))

    orig = metrics.set_index("condition").loc["finetuned_lora_original"]
    leak = metrics.set_index("condition").loc["finetuned_lora_leakage"]
    rmse_pct = 100 * (orig["RMSE"] - leak["RMSE"]) / orig["RMSE"]
    print(f"\nLoRA fine-tuned: RMSE {orig['RMSE']:.4f} -> {leak['RMSE']:.4f} ({rmse_pct:.1f}% reduction)")
    print(f"LoRA fine-tuned: R2 {orig['R2']:.4f} -> {leak['R2']:.4f} (delta={leak['R2']-orig['R2']:.2f})")
    return metrics


def plot_prediction_curves(preds, metrics):
    fig, ax = plt.subplots(figsize=(11, 5.5), constrained_layout=True)
    obs = preds[preds.condition == "zero_shot"][["date", "observed"]].drop_duplicates().sort_values("date")
    ax.plot(pd.to_datetime(obs.date), obs.observed, color="#2b2b2b", linewidth=2.6, label="Observed LAI", zorder=4)
    for cond in COND_ORDER:
        sub = preds[preds.condition == cond].sort_values("date")
        r2 = metrics.set_index("condition").loc[cond, "R2"]
        style = "--" if cond != "finetuned_lora_leakage" else "-"
        ax.plot(pd.to_datetime(sub.date), sub.prediction, color=COLORS[cond], linewidth=2.0, linestyle=style,
                marker="o", markersize=3.5, label=f"{COND_LABELS[cond]} (R²={r2:.2f})", zorder=3)
    ax.set_title(f"{SITE} / {LEAK_YEAR}: Chronos-2 prediction curves — zero-shot vs. LoRA, "
                 "with and without 2012 leakage", loc="left", fontsize=12.5)
    ax.set_ylabel("LAI")
    ax.tick_params(axis="x", rotation=20)
    ax.legend(frameon=False, fontsize=9, loc="upper left")
    fig.savefig(BASE / "leakage_prediction_curves_chronos2.png", dpi=150, facecolor="white")
    plt.close(fig)


def plot_residuals(preds, metrics):
    fig, ax = plt.subplots(figsize=(11, 5), constrained_layout=True)
    ax.axhline(0, color="#999", linewidth=1)
    for cond in COND_ORDER:
        sub = preds[preds.condition == cond].sort_values("date")
        rmse = metrics.set_index("condition").loc[cond, "RMSE"]
        ax.plot(pd.to_datetime(sub.date), sub.residual, color=COLORS[cond], linewidth=1.8, marker="o",
                markersize=3.5, label=f"{COND_LABELS[cond]} (RMSE={rmse:.2f})")
    ax.set_title(f"{SITE} / {LEAK_YEAR}: Chronos-2 residuals (prediction − observed)", loc="left", fontsize=12.5)
    ax.set_ylabel("Residual")
    ax.tick_params(axis="x", rotation=20)
    ax.legend(frameon=False, fontsize=9)
    fig.savefig(BASE / "leakage_residuals_chronos2.png", dpi=150, facecolor="white")
    plt.close(fig)


def plot_cross_project_r2(metrics):
    """R2 before/after leakage, Chronos-2 LoRA alongside all 8 AELSTM models."""
    aelstm = pd.read_csv(AELSTM_BASE / "leakage_summary_table.csv")
    fig, ax = plt.subplots(figsize=(11, 6), constrained_layout=True)

    labels = list(aelstm["model"]) + ["Chronos-2\n(LoRA)"]
    r2_before = list(aelstm["R2_original"]) + [metrics.set_index("condition").loc["finetuned_lora_original", "R2"]]
    r2_after = list(aelstm["R2_leakage"]) + [metrics.set_index("condition").loc["finetuned_lora_leakage", "R2"]]

    import numpy as np
    x = np.arange(len(labels))
    w = 0.35
    colors_before = ["#a8791f"] * (len(labels) - 1) + ["#c0562f"]
    colors_after = ["#1f5c4a"] * (len(labels) - 1) + ["#1f5c4a"]
    ax.bar(x - w / 2, r2_before, w, color="#a8791f", label="Original (2012 unseen)")
    ax.bar(x + w / 2, r2_after, w, color="#1f5c4a", label="Leakage (2012 seen in training)")
    ax.axhline(0, color="black", linewidth=1)
    ax.axvline(len(labels) - 1.5, color="#999", linewidth=1, linestyle=":")
    ax.set_xticks(x); ax.set_xticklabels(labels)
    ax.set_ylabel("R² on 2012")
    ax.set_title(f"{SITE}: R² on 2012 before/after leakage — 8 AELSTM models + Chronos-2 LoRA",
                 loc="left", fontsize=12.5)
    ax.legend(frameon=False)
    fig.savefig(BASE / "leakage_cross_project_r2_comparison.png", dpi=150, facecolor="white")
    plt.close(fig)


def main():
    metrics = pd.read_csv(BASE / "leakage_diagnostic_metrics.csv")
    preds = pd.read_csv(BASE / "leakage_diagnostic_predictions.csv", parse_dates=["date"])
    metrics = build_summary_table(metrics)
    plot_prediction_curves(preds, metrics)
    plot_residuals(preds, metrics)
    plot_cross_project_r2(metrics)
    print(f"\nSaved figures + summary table to {BASE}")


if __name__ == "__main__":
    main()
