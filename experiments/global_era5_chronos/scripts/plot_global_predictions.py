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
import matplotlib.dates
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
LAI_DIR = ROOT / "data/global_lai/processed"
RESULTS_DIR = ROOT / "results_global"
OUT_DIR = ROOT / "outputs"

GROUND_TRUTH_COLOR = "#555555"
CONTEXT_COLOR = "#9AA294"
PRED_COLOR = "#8C1D40"  # matches the deck's global-experiment accent

# Top-8 performers by R2, spanning diverse regions/classes - g032 and g065
# were the two best; the other 6 are the next-best distinct-region/class
# pixels (not just the raw top-6, to avoid e.g. 4 Siberia grasslands in a
# row - see era5_global70_clean.csv for the full ranking).
CURATED = [
    ("g032_shrubs_bd", "Mediterranean shrubland"),
    ("g065_shrubs_bd", "Central/Southern Africa shrubland"),
    ("g005_grass_nat", "Siberia / Boreal Eurasia grassland"),
    ("g009_grass_nat", "Canada grassland"),
    ("g014_trees_ne", "Siberia / Boreal Eurasia evergreen forest"),
    ("g024_trees_ne", "Western Europe evergreen forest"),
    ("g035_grass_man", "East Asia managed grassland"),
    ("g068_grass_nat", "Southern S. America grassland"),
]

# separate diagnostic selection (mixed strong + failure cases) used for the
# report's failure-mode discussion - kept distinct from the "great
# performers" showcase above per explicit request.
CURATED_DIAGNOSTIC = [
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


def plot_test_year(ax, pixel_id, subtitle):
    """Zoomed to just the 2022 test year - no pre-2022 context line."""
    _, pred, metrics = load_pixel(pixel_id)
    ax.plot(pred["date"], pred["ground_truth"], color=GROUND_TRUTH_COLOR, linewidth=2.4, marker="o",
             markersize=3.5, label="Observed (2022)")
    ax.plot(pred["date"], pred["prediction"], color=PRED_COLOR, linewidth=2.2, ls="--", marker="o",
             markersize=3.5, label="Zero-shot Chronos-2")
    r2 = float(metrics["R2"])
    pear = float(metrics["Pearson_r"])
    ax.set_title(f"{pixel_id}  —  {subtitle}\nR²={r2:.3f}, Pearson r={pear:.3f}", loc="left", fontsize=10.5)
    ax.set_ylabel("LAI")
    ax.tick_params(labelsize=8)
    ax.xaxis.set_major_locator(matplotlib.dates.MonthLocator())
    ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%b"))


def build_grid(pixels, stem, suptitle, nrows, ncols, plot_fn, figsize):
    fig, axes = plt.subplots(nrows, ncols, figsize=figsize, constrained_layout=True)
    for ax, (pixel_id, subtitle) in zip(axes.flat, pixels):
        plot_fn(ax, pixel_id, subtitle)
    for ax in axes.flat[len(pixels):]:
        ax.axis("off")
    axes.flat[0].legend(frameon=False, fontsize=9, loc="upper left")
    fig.suptitle(suptitle, fontsize=13, fontweight="bold")
    fig.savefig(OUT_DIR / f"{stem}.png", dpi=220, bbox_inches="tight")
    fig.savefig(OUT_DIR / f"{stem}.pdf", bbox_inches="tight")
    plt.close(fig)
    print(f"saved {stem}.png")


def main():
    # "great performers" showcase (8 pixels: g032 + g065 kept, 6 more added, per request)
    build_grid(CURATED, "global70_top_performers",
               "Zero-shot Chronos-2, global (non-CONUS) experiment: top performers, diverse regions\n"
               "(full 2000–2021 context shown faint, 2022 forecast scored against observed LAI)",
               4, 2, plot_one, figsize=(15, 16))
    build_grid(CURATED, "global70_top_performers_testyear",
               "Zero-shot Chronos-2, global (non-CONUS) experiment: top performers, 2022 test year only",
               4, 2, plot_test_year, figsize=(15, 16))

    # original mixed diagnostic grid (3 strong + 3 failure-mode examples) -
    # still referenced by ERA5_GLOBAL70_REPORT.md's failure-cases discussion
    build_grid(CURATED_DIAGNOSTIC, "global70_prediction_examples",
               "Zero-shot Chronos-2, global (non-CONUS) experiment: observed vs. predicted LAI\n"
               "(full 2000–2021 context shown faint, 2022 forecast scored against observed LAI)",
               3, 2, plot_one, figsize=(15, 12))
    build_grid(CURATED_DIAGNOSTIC, "global70_prediction_examples_testyear",
               "Zero-shot Chronos-2, global (non-CONUS) experiment: 2022 test year only",
               3, 2, plot_test_year, figsize=(15, 12))

    # also save each one individually at full size (e.g. for the pixel the user opened)
    indiv_dir = OUT_DIR / "global70_prediction_plots"
    indiv_dir.mkdir(exist_ok=True)
    testyear_dir = OUT_DIR / "global70_prediction_plots_testyear"
    testyear_dir.mkdir(exist_ok=True)
    all_pixels = sorted(p.stem for p in LAI_DIR.glob("*.csv"))
    for pixel_id in all_pixels:
        if not (RESULTS_DIR / pixel_id / "predictions_era5_cloud.csv").exists():
            continue
        fig, ax = plt.subplots(figsize=(10, 4.5), constrained_layout=True)
        plot_one(ax, pixel_id, "")
        ax.legend(frameon=False, fontsize=9, loc="upper left")
        fig.savefig(indiv_dir / f"{pixel_id}.png", dpi=180, bbox_inches="tight")
        plt.close(fig)

        fig, ax = plt.subplots(figsize=(8, 4.5), constrained_layout=True)
        plot_test_year(ax, pixel_id, "")
        ax.legend(frameon=False, fontsize=9, loc="best")
        fig.savefig(testyear_dir / f"{pixel_id}.png", dpi=180, bbox_inches="tight")
        plt.close(fig)
    print(f"saved {len(all_pixels)} individual prediction plots to {indiv_dir} and {testyear_dir}")


if __name__ == "__main__":
    main()
