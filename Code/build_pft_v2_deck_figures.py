# Builds the 2 new figures needed for the PFT-v2 advisor deck that don't
# already exist in a presentation-ready form: (1) the real-vs-shuffled PFT
# bar chart (the central result), (2) an overfitting-curve comparison
# between the original 2-window experiment and the new 8-window
# experiment. All numbers read directly from saved CSVs - nothing here is
# invented. Saved to outputs/pft_v2/deck_figures/ (new subfolder).
from pathlib import Path

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import common_pipeline as cp

OUTPUT_DIR = cp.OUTPUTS_ROOT / "pft_v2" / "deck_figures"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

INK = "#1C2119"
MUTED = "#5B6358"
ACCENT = "#2F6F5E"
ACCENT_DARK = "#1E4A33"
WARN = "#B5651D"
FAINT = "#C7CDBE"
GREY = "#9AA294"

plt.rcParams.update({
    "font.family": "DejaVu Sans", "text.color": INK, "axes.edgecolor": "#DDE2DC",
    "axes.labelcolor": INK, "xtick.color": INK, "ytick.color": INK,
    "axes.spines.top": False, "axes.spines.right": False,
})


def fig_real_vs_shuffled():
    summary = pd.read_csv(cp.OUTPUTS_ROOT / "pft_v2" / "final_2022_summary.csv")
    ttest = pd.read_csv(cp.OUTPUTS_ROOT / "pft_v2" / "real_vs_shuffled_ttest.csv").iloc[0]

    order = ["baseline_zero_shot", "low_rank_fractional", "low_rank_dominant", "low_rank_shuffled_control"]
    labels = ["Zero-shot\n(no PFT)", "Real PFT\n(fractional)", "Real PFT\n(dominant)", "Shuffled PFT\n(control)"]
    colors = [GREY, ACCENT, ACCENT, WARN]
    vals = [summary.set_index("method").loc[m, "mean_R2"] for m in order]

    fig, ax = plt.subplots(figsize=(9.5, 6.2), constrained_layout=True)
    bars = ax.bar(labels, vals, color=colors, width=0.6, zorder=3, edgecolor="white", linewidth=0.5)
    base = vals[0]
    for bar, v, m in zip(bars, vals, order):
        delta = v - base
        label = f"{v:.4f}" if m == "baseline_zero_shot" else f"{v:.4f}\n(Δ={delta:+.4f})"
        ax.text(bar.get_x() + bar.get_width() / 2, v + 0.004, label, ha="center", va="bottom",
                fontsize=11.5, color=INK, fontweight="bold")
    ax.set_ylim(0.75, 0.775)
    ax.set_ylabel("Mean R²  (held-out 2022, 70 pixels)", fontsize=12)
    ax.set_title("Real PFT ≈ Shuffled PFT on the final 2022 test", fontsize=14, fontweight="bold", loc="left", pad=14)
    ax.grid(axis="y", color="#EEF0EA", zorder=0)

    ax.text(0.985, 0.04,
             f"paired t-test p = {ttest.paired_ttest_p:.3f}   |   Wilcoxon p = {ttest.wilcoxon_p:.3f}\n"
             f"{int(ttest.n_pixels_real_better)}/70 pixels favor real PFT   ·   "
             f"{int(ttest.n_pixels_shuffled_better)}/70 favor shuffled",
             transform=ax.transAxes, ha="right", va="bottom", fontsize=10.5, color=MUTED,
             bbox=dict(boxstyle="round,pad=0.5", fc="#F5F6F1", ec="#DDE2DC"))
    fig.savefig(OUTPUT_DIR / "real_vs_shuffled_bar.png", dpi=200, facecolor="white")
    plt.close(fig)
    print("Saved real_vs_shuffled_bar.png")


def fig_overfitting_comparison():
    old = pd.read_csv(cp.OUTPUTS_ROOT / "pft_multipixel" / "expA_temporal" / "fractional" / "search_curve.csv")
    old = old[old.lr == 0.001]
    new = pd.read_csv(cp.OUTPUTS_ROOT / "pft_v2" / "screen_fractional" / "low_rank" / "search_curve.csv")
    new = new[new.lr == 0.001]

    fig, axes = plt.subplots(1, 2, figsize=(13, 5.3), constrained_layout=True, sharey=False)

    ax = axes[0]
    ax.plot(old.step, old.train_loss, marker="o", markersize=4, color=ACCENT, label="Train loss")
    ax.plot(old.step, old.val_loss, marker="s", markersize=4, color=WARN, label="Validation loss")
    ax.axvline(0, color=WARN, linestyle="--", linewidth=1.2, alpha=0.7)
    ax.set_title("Original design: 2 training windows\n(deep-MLP FiLM)", fontsize=12, loc="left")
    ax.set_xlabel("Training step")
    ax.set_ylabel("Loss")
    ax.legend(frameon=False, fontsize=10)
    ax.annotate("best step = 0", xy=(0, old.val_loss.iloc[0]), xytext=(35, old.val_loss.iloc[0] - 0.005),
                 fontsize=10, color=WARN, arrowprops=dict(arrowstyle="->", color=WARN))

    ax = axes[1]
    ax.plot(new.step, new.train_loss, marker="o", markersize=4, color=ACCENT, label="Train loss")
    ax.plot(new.step, new.val_loss, marker="s", markersize=4, color=WARN, label="Validation loss")
    best_step = new.loc[new.val_loss.idxmin(), "step"]
    ax.axvline(best_step, color=WARN, linestyle="--", linewidth=1.2, alpha=0.7)
    ax.set_title("4x more supervision: 8 training windows\n(rank-8 bottleneck FiLM)", fontsize=12, loc="left")
    ax.set_xlabel("Training step")
    ax.legend(frameon=False, fontsize=10)
    ax.annotate(f"best step = {int(best_step)}", xy=(best_step, new.val_loss.min()),
                 xytext=(best_step + 30, new.val_loss.min() + 0.003),
                 fontsize=10, color=WARN, arrowprops=dict(arrowstyle="->", color=WARN))

    fig.suptitle("Validation loss never shows a sustained improvement, before or after 4x more training data",
                 fontsize=13.5, fontweight="bold")
    fig.savefig(OUTPUT_DIR / "overfitting_comparison.png", dpi=200, facecolor="white")
    plt.close(fig)
    print("Saved overfitting_comparison.png")


if __name__ == "__main__":
    fig_real_vs_shuffled()
    fig_overfitting_comparison()
