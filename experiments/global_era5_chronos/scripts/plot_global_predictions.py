# Per-pixel prediction-vs-observed LAI visualizations for the 70-pixel
# global (non-CONUS) experiment. Reads only already-saved results
# (data/global_lai/processed/*.csv for the full observed LAI history,
# results_global/<pixel>/predictions_era5_cloud.csv for the 2022 forecast)
# - no new Chronos-2 runs. Style matches the project's existing
# Code/plotting_utils.py::plot_prediction convention (observed in grey,
# prediction in accent color), extended to also show the pre-2022 context
# history so the seasonal pattern Chronos-2 is extrapolating from is visible.
from pathlib import Path

import matplotlib
matplotlib.use("AGG")
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
LAI_DIR = ROOT / "data/global_lai/processed"
RESULTS_DIR = ROOT / "results_global"
OUT_DIR = ROOT / "outputs"

GROUND_TRUTH_COLOR = "#555555"
CONTEXT_COLOR = "#9AA294"
PRED_COLOR = "#8C1D40"  # matches the deck's global-experiment accent

# Curated selection spanning the full performance range, incl. the pixel
# the user opened directly (g001_shrubs_nd) - see
# ERA5_GLOBAL70_REPORT.md's "Failure cases" section for the reasoning
# behind each one's inclusion.
CURATED = [
    ("g032_shrubs_bd", "Best: Mediterranean shrubland"),
    ("g065_shrubs_bd", "Strong: Central/Southern Africa shrubland"),
    ("g009_grass_nat", "Solid: Canada grassland"),
    ("g001_shrubs_nd", "Weak, short context: \"Other\" shrubland"),
    ("g015_trees_nd", "Miscalibrated but correlated: Siberia forest"),
    ("g052_grass_nat", "Worst, anti-correlated: Amazon grassland"),
]


def load_pixel(pixel_id):
    lai = pd.read_csv(LAI_DIR / f"{pixel_id}.csv", parse_dates=["date"])
    pred = pd.read_csv(RESULTS_DIR / pixel_id / "predictions_era5_cloud.csv", parse_dates=["date"])
    metrics = {}
    for line in (RESULTS_DIR / pixel_id / "metrics_era5_cloud.txt").read_text().splitlines():
        k, v = line.split(":", 1)
        metrics[k.strip()] = v.strip()
    context = lai[lai["date"] < "2022-01-01"]
    return context, pred, metrics


def plot_one(ax, pixel_id, subtitle):
    context, pred, metrics = load_pixel(pixel_id)
    ax.plot(context["date"], context["LAI"], color=CONTEXT_COLOR, linewidth=1.0, label="Observed (context)")
    ax.plot(pred["date"], pred["ground_truth"], color=GROUND_TRUTH_COLOR, linewidth=2.2, label="Observed (2022, scored)")
    ax.plot(pred["date"], pred["prediction"], color=PRED_COLOR, linewidth=2.0, ls="--", label="Zero-shot Chronos-2")
    ax.axvline(pd.Timestamp("2022-01-01"), color="black", lw=0.7, ls=":")
    r2 = float(metrics["R2"])
    pear = float(metrics["Pearson_r"])
    ctx_n = metrics["context_steps"]
    ax.set_title(f"{pixel_id}  —  {subtitle}\nR²={r2:.3f}, Pearson r={pear:.3f}, context={ctx_n} steps",
                 loc="left", fontsize=10.5)
    ax.set_ylabel("LAI")
    ax.tick_params(labelsize=8)


def main():
    fig, axes = plt.subplots(3, 2, figsize=(15, 12), constrained_layout=True)
    for ax, (pixel_id, subtitle) in zip(axes.flat, CURATED):
        plot_one(ax, pixel_id, subtitle)
    axes.flat[0].legend(frameon=False, fontsize=9, loc="upper left")
    fig.suptitle("Zero-shot Chronos-2, global (non-CONUS) experiment: observed vs. predicted LAI\n"
                 "(full 2000–2021 context shown faint, 2022 forecast scored against observed LAI)",
                 fontsize=13, fontweight="bold")
    fig.savefig(OUT_DIR / "global70_prediction_examples.png", dpi=220, bbox_inches="tight")
    fig.savefig(OUT_DIR / "global70_prediction_examples.pdf", bbox_inches="tight")
    plt.close(fig)
    print("saved global70_prediction_examples.png")

    # also save each one individually at full size (e.g. for the pixel the user opened)
    indiv_dir = OUT_DIR / "global70_prediction_plots"
    indiv_dir.mkdir(exist_ok=True)
    all_pixels = sorted(p.stem for p in LAI_DIR.glob("*.csv"))
    for pixel_id in all_pixels:
        if not (RESULTS_DIR / pixel_id / "predictions_era5_cloud.csv").exists():
            continue
        fig, ax = plt.subplots(figsize=(10, 4.5), constrained_layout=True)
        plot_one(ax, pixel_id, "")
        ax.legend(frameon=False, fontsize=9, loc="upper left")
        fig.savefig(indiv_dir / f"{pixel_id}.png", dpi=180, bbox_inches="tight")
        plt.close(fig)
    print(f"saved {len(all_pixels)} individual prediction plots to {indiv_dir}")


if __name__ == "__main__":
    main()
