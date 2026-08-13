# Compares zero-shot Chronos-2, the original (unvalidated) LoRA fine-tune,
# and the improved (validation-selected) LoRA fine-tune from
# finetune_lora_improved.py - all three already scored against the same raw
# observed LAI (this project's data was never smoothed). Also plots each
# pixel's training/validation loss trajectory for its winning hyperparameter
# configuration (marking the selected checkpoint) and, for transparency, all
# 6 searched configurations' validation curves together. Reads only
# already-saved outputs; no retraining.
import matplotlib.pyplot as plt
import pandas as pd

import common_pipeline as cp
import plotting_utils as pu

IMPROVED_COLOR = "#6A3D9A"  # purple, distinct from ZERO_SHOT_COLOR (blue) / FINETUNED_COLOR (vermillion)
OUTPUT_DIR = cp.OUTPUTS_ROOT / "finetuned_lora_improved" / "comparison"

MODES = [
    ("zero_shot", "Zero-shot", pu.ZERO_SHOT_COLOR, "-"),
    ("finetuned_lora", "LoRA fine-tuned (original)", pu.FINETUNED_COLOR, "--"),
    ("finetuned_lora_improved", "LoRA fine-tuned (improved)", IMPROVED_COLOR, "-."),
]


def load_predictions(mode, site):
    return pd.read_csv(cp.OUTPUTS_ROOT / mode / site / "predictions.csv", parse_dates=["date"])


def build_comparison_table(sites):
    rows = []
    for site in sites:
        for mode, label, _, _ in MODES:
            preds = load_predictions(mode, site)
            metrics = cp.compute_metrics(preds["ground_truth"], preds["prediction"])
            metrics.update(site=site, mode=mode)
            rows.append(metrics)
    table = pd.DataFrame(rows)[["site", "mode", "RMSE", "MAE", "MAPE", "R2", "Pearson_r"]]
    table.to_csv(OUTPUT_DIR / "three_way_comparison.csv", index=False)
    return table


def plot_three_way(sites):
    for site in sites:
        obs = load_predictions("zero_shot", site)  # ground_truth is identical across modes
        fig, ax = plt.subplots(figsize=(12, 6.5), constrained_layout=True)
        ax.plot(obs["date"], obs["ground_truth"], color=pu.GROUND_TRUTH_COLOR, linewidth=2.8,
                label="Observed (raw)", zorder=10)
        for mode, label, color, ls in MODES:
            preds = load_predictions(mode, site)
            ax.plot(preds["date"], preds["prediction"], color=color, linestyle=ls, linewidth=2.4,
                     label=label, zorder=5)
        ax.set_title(f"{site} — zero-shot vs. original vs. improved LoRA fine-tuning, {cp.TEST_YEAR}", loc="left")
        ax.set_xlabel("Date")
        ax.set_ylabel("LAI")
        ax.legend(frameon=False)
        pu.save_fig(fig, OUTPUT_DIR, f"three_way_comparison_{site}")


def load_search_curves(site):
    search_dir = cp.OUTPUTS_ROOT / "finetuned_lora_improved" / site / "search"
    summary = pd.read_csv(cp.OUTPUTS_ROOT / "finetuned_lora_improved" / site / "search_summary.csv")
    curves = {}
    for _, row in summary.iterrows():
        tag = f"lr{row['learning_rate']:g}_r{int(row['lora_rank'])}"
        train = pd.read_csv(search_dir / f"{tag}_train_loss.csv")
        eval_ = pd.read_csv(search_dir / f"{tag}_eval_loss.csv")
        curves[tag] = {"train": train, "eval": eval_, "row": row}
    winner_tag = f"lr{summary.iloc[0]['learning_rate']:g}_r{int(summary.iloc[0]['lora_rank'])}"
    return curves, winner_tag, summary


def plot_winner_curves(sites):
    fig, axes = plt.subplots(1, len(sites), figsize=(6 * len(sites), 5.5), constrained_layout=True)
    if len(sites) == 1:
        axes = [axes]
    for ax, site in zip(axes, sites):
        curves, winner_tag, summary = load_search_curves(site)
        c = curves[winner_tag]
        ax.plot(c["train"]["step"], c["train"]["train_loss"], color="#888888", linewidth=1.8, label="Train loss")
        ax.plot(c["eval"]["step"], c["eval"]["eval_loss"], color=IMPROVED_COLOR, linewidth=2.4,
                marker="o", markersize=5, label="Validation loss")
        best_step = int(c["row"]["best_step"])
        ax.axvline(best_step, color="black", linestyle=":", linewidth=1.5)
        ax.annotate(f"selected\nstep {best_step}", (best_step, c["row"]["best_eval_loss"]),
                    textcoords="offset points", xytext=(10, 10), fontsize=9)
        lr, rank = c["row"]["learning_rate"], int(c["row"]["lora_rank"])
        ax.set_title(f"{site}\nwinner: lr={lr:g}, rank={rank}", loc="left", fontsize=11)
        ax.set_xlabel("Training step")
        ax.set_ylabel("Pinball/quantile loss")
        ax.legend(frameon=False, fontsize=9)
    fig.suptitle("Winning configuration per pixel: train vs. validation loss "
                  "(dotted line = selected checkpoint)", fontsize=pu.FONT_SIZES["title"])
    pu.save_fig(fig, OUTPUT_DIR, "finetune_winner_train_val_curves")


def plot_all_configs_curves(sites):
    fig, axes = plt.subplots(1, len(sites), figsize=(6.5 * len(sites), 5.5), constrained_layout=True)
    if len(sites) == 1:
        axes = [axes]
    palette = plt.cm.tab10.colors
    for ax, site in zip(axes, sites):
        curves, winner_tag, summary = load_search_curves(site)
        for i, (tag, c) in enumerate(curves.items()):
            is_winner = tag == winner_tag
            ax.plot(c["eval"]["step"], c["eval"]["eval_loss"], color=palette[i % 10],
                     linewidth=3.0 if is_winner else 1.6, alpha=1.0 if is_winner else 0.7,
                     marker="o", markersize=4, label=tag + (" (selected)" if is_winner else ""))
        ax.set_title(site, loc="left", fontsize=11)
        ax.set_xlabel("Training step")
        ax.set_ylabel("Validation loss")
        ax.legend(frameon=False, fontsize=8)
    fig.suptitle("All 6 searched configurations' validation loss, per pixel", fontsize=pu.FONT_SIZES["title"])
    pu.save_fig(fig, OUTPUT_DIR, "finetune_search_all_configs_curves")


def main():
    sites = cp.SITES
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    table = build_comparison_table(sites)
    print("=== Three-way comparison (zero-shot / original LoRA / improved LoRA), vs. raw observations ===")
    print(table.to_string(index=False))

    print("\n=== R2 deltas ===")
    pivot = table.pivot(index="site", columns="mode", values="R2")[[m[0] for m in MODES]]
    pivot["improved_minus_original"] = pivot["finetuned_lora_improved"] - pivot["finetuned_lora"]
    pivot["improved_minus_zeroshot"] = pivot["finetuned_lora_improved"] - pivot["zero_shot"]
    print(pivot.round(4).to_string())

    plot_three_way(sites)
    plot_winner_curves(sites)
    plot_all_configs_curves(sites)
    print(f"\nSaved three_way_comparison.csv and figures to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
