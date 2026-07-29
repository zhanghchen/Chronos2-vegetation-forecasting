# Shared plotting style for this project - independent copy from AELSTM's
# plotting_utils.py (kept consistent in spirit: 300 DPI, PNG+PDF, fixed
# colors) since the two projects must not share code.
from pathlib import Path

import matplotlib
matplotlib.use("AGG")
import matplotlib.pyplot as plt

DPI = 300
FIGSIZE = (12, 6)
FONT_SIZES = {"title": 14, "label": 12, "tick": 10, "legend": 10}

GROUND_TRUTH_COLOR = "#555555"
ZERO_SHOT_COLOR = "#0072B2"   # blue
FINETUNED_COLOR = "#D55E00"  # vermillion

# x-axis order for the merged AELSTM + Chronos-2 comparison chart (grouped
# by site/color, matching AELSTM's own cross_pixel_r2_bars.png convention).
ALL_MODEL_ORDER = ["AELSTM", "BiLSTM", "LSTM", "GRU", "RNN", "CNN", "RF", "SVM", "zero_shot", "finetuned_lora"]

plt.rcParams.update({
    "savefig.dpi": DPI,
    "font.size": FONT_SIZES["tick"],
    "axes.titlesize": FONT_SIZES["title"],
    "axes.labelsize": FONT_SIZES["label"],
    "xtick.labelsize": FONT_SIZES["tick"],
    "ytick.labelsize": FONT_SIZES["tick"],
    "legend.fontsize": FONT_SIZES["legend"],
    "lines.linewidth": 2.2,
    "axes.spines.top": False,
    "axes.spines.right": False,
})


def save_fig(fig, output_dir, stem):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "pdf"):
        fig.savefig(output_dir / f"{stem}.{ext}", dpi=DPI, bbox_inches="tight")
    plt.close(fig)


def plot_prediction(dates, true, pred, title, output_dir, stem, pred_color=ZERO_SHOT_COLOR, pred_label="Predicted"):
    fig, ax = plt.subplots(figsize=FIGSIZE, constrained_layout=True)
    ax.plot(dates, true, color=GROUND_TRUTH_COLOR, linewidth=2.6, label="Observed")
    ax.plot(dates, pred, color=pred_color, linewidth=2.2, label=pred_label)
    ax.set_title(title, loc="left")
    ax.set_xlabel("Date")
    ax.set_ylabel("LAI")
    ax.legend(frameon=False)
    save_fig(fig, output_dir, stem)


def plot_prediction_multi(dates, true, series, title, output_dir, stem):
    """series: list of (label, values, color) tuples, e.g. zero-shot + fine-tuned together."""
    fig, ax = plt.subplots(figsize=FIGSIZE, constrained_layout=True)
    ax.plot(dates, true, color=GROUND_TRUTH_COLOR, linewidth=2.6, label="Observed")
    for label, values, color in series:
        ax.plot(dates, values, color=color, linewidth=2.2, label=label)
    ax.set_title(title, loc="left")
    ax.set_xlabel("Date")
    ax.set_ylabel("LAI")
    ax.legend(frameon=False)
    save_fig(fig, output_dir, stem)
