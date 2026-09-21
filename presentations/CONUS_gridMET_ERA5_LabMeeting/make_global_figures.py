# NEW figures for the integrated deck's Part 2 (replacing the CONUS-ERA5
# section with the global non-CONUS ERA5+MODIS experiment). Reads only
# already-saved results - no new experiments.
from pathlib import Path

import matplotlib
matplotlib.use("AGG")
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path("/home/deh25003/chronos-forecasting/Chronos2-vegetation-forecasting")
ERA5_ROOT = ROOT / "experiments/global_era5_chronos"
OUT = Path(__file__).resolve().parent / "figures"
OUT.mkdir(exist_ok=True)

CONUS_COLOR = "#2F6F5E"   # Part 1 (gridMET, CONUS) - matches the deck's ACCENT green
GLOBAL_COLOR = "#8C1D40"  # Part 2 (global ERA5) - new, distinct from the old CONUS-ERA5 blue
DPI = 300


def main():
    p32 = pd.read_csv(ROOT / "outputs/purity32_pixel_study/zero_shot_32pixels.csv")
    g68 = pd.read_csv(ERA5_ROOT / "outputs/era5_global70_clean.csv")

    fig, ax = plt.subplots(figsize=(7, 6.2), constrained_layout=True)
    data = [p32["R2"].values, g68["R2"].values]
    bp = ax.boxplot(data, tick_labels=[f"Part 1: CONUS gridMET\n(n={len(p32)})", f"Part 2: Global ERA5\n(n={len(g68)})"],
                     patch_artist=True, showmeans=True, widths=0.55)
    for patch, c in zip(bp["boxes"], [CONUS_COLOR, GLOBAL_COLOR]):
        patch.set_facecolor(c)
        patch.set_alpha(0.75)
    for i, vals in enumerate(data, start=1):
        jitter = 0.08 * (pd.Series(range(len(vals))) % 5 - 2) / 2.5
        ax.scatter([i] * len(vals) + jitter, vals, color="black", alpha=0.35, s=14, zorder=5)
    ax.axhline(0, color="black", lw=0.8)
    ax.axhline(0.8, color="#888888", lw=0.8, ls="--")
    ax.text(2.4, 0.81, "R²=0.8", fontsize=8, color="#888888", va="bottom")
    ax.set_ylabel("Zero-shot Chronos-2 $R^2$")
    ax.set_title("CONUS (gridMET) vs. global non-CONUS (ERA5) —\ndisjoint pixel sets, same zero-shot protocol",
                 loc="left", fontsize=12, fontweight="bold")
    med1, med2 = p32["R2"].median(), g68["R2"].median()
    ax.text(1, -1.05, f"median={med1:.3f}", ha="center", fontsize=10, color=CONUS_COLOR, fontweight="bold")
    ax.text(2, -1.05, f"median={med2:.3f}", ha="center", fontsize=10, color=GLOBAL_COLOR, fontweight="bold")
    ax.set_ylim(-1.15, 1.05)
    fig.savefig(OUT / "conus_vs_global_r2_boxplot.png", dpi=DPI, bbox_inches="tight")
    fig.savefig(OUT / "conus_vs_global_r2_boxplot.pdf", bbox_inches="tight")
    plt.close(fig)
    print("saved conus_vs_global_r2_boxplot.png")


if __name__ == "__main__":
    main()
