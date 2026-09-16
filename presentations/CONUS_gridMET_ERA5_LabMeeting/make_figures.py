# Builds the NEW figures for the dual-experiment lab-meeting deck (build_deck.py
# in this same directory). Reads only already-saved result/selection CSVs -- no
# new Chronos-2 runs. Reuses the project's existing CLASS_COLORS convention
# (Code/build_purity32_pixel_comparison.py, Code/build_era5_cloud_comparison.py)
# so these new figures read consistently with the existing ones reused in the
# same deck.
from pathlib import Path

import geopandas as gpd
import matplotlib
matplotlib.use("AGG")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle

ROOT = Path("/home/deh25003/chronos-forecasting/Chronos2-vegetation-forecasting")
AELSTM_ROOT = Path("/home/deh25003/chronos-forecasting/AELSTM")
OUT = Path(__file__).resolve().parent / "figures"
OUT.mkdir(exist_ok=True)

DPI = 300
INK = "#1C2119"
MUTED = "#5C6355"
MAP_FILL = "#EEF0EA"
MAP_EDGE = "#FFFFFF"
PANEL_BG = "#FAFAF7"

# identical to Code/build_purity32_pixel_comparison.py & build_era5_cloud_comparison.py
CLASS_COLORS = {
    "TREES_NE": "#1B7837", "TREES_BD": "#5AAE61", "TREES_ND": "#A6DBA0",
    "SHRUBS_NE": "#B35806", "SHRUBS_BD": "#E08214", "SHRUBS_ND": "#FDB863",
    "GRASS_NAT": "#762A83", "GRASS_MAN": "#C2A5CF",
}
CLASS_LABELS = {
    "TREES_NE": "Trees, needleleaf evergreen", "TREES_BD": "Trees, broadleaf deciduous",
    "TREES_ND": "Trees, needleleaf deciduous", "SHRUBS_NE": "Shrubs, needleleaf evergreen",
    "SHRUBS_BD": "Shrubs, broadleaf deciduous", "SHRUBS_ND": "Shrubs, needleleaf deciduous",
    "GRASS_NAT": "Grass, natural", "GRASS_MAN": "Grass, managed/cropland",
}
ERA5_COLOR = "#3A6EA5"    # matches build_era5_progress_deck.py's BLUE
GRIDMET_COLOR = "#2F6F5E"  # matches ACCENT

STATES_SHP = "/home/deh25003/.local/share/cartopy/shapefiles/natural_earth/cultural/ne_50m_admin_1_states_provinces_lakes.shp"
COUNTRIES_SHP = "/home/deh25003/.local/share/cartopy/shapefiles/natural_earth/cultural/ne_110m_admin_0_countries.shp"


def conus_states():
    states = gpd.read_file(STATES_SHP)
    exclude = {"Alaska", "Hawaii", "Puerto Rico"}
    return states[(states["admin"] == "United States of America") & (~states["name"].isin(exclude))]


def draw_pixel_map(df, out_name, title, n_label):
    """df must have columns lat, lon, dominant_pft. Two-panel figure: (a) a
    small world-context inset showing WHERE on Earth these pixels are (so the
    deck never implies global sampling for a CONUS-only pixel set), (b) the
    main zoomed CONUS map with every pixel plotted and colored by dominant
    vegetation class."""
    fig = plt.figure(figsize=(11, 7.6), constrained_layout=True)
    gs = fig.add_gridspec(1, 4, width_ratios=[1, 3, 0.02, 0.02])

    # ---- (a) global context inset ----
    ax0 = fig.add_subplot(gs[0])
    world = gpd.read_file(COUNTRIES_SHP)
    world.plot(ax=ax0, facecolor=MAP_FILL, edgecolor=MAP_EDGE, linewidth=0.4, zorder=1)
    ax0.set_facecolor(PANEL_BG)
    ax0.set_xlim(-170, -50)
    ax0.set_ylim(5, 75)
    ax0.set_xticks([]); ax0.set_yticks([])
    for spine in ax0.spines.values():
        spine.set_visible(False)
    box = Rectangle((-125, 24), 58, 25, facecolor="none", edgecolor="#C0392B", linewidth=1.6, zorder=5)
    ax0.add_patch(box)
    ax0.set_title("Geographic context", loc="left", fontsize=10, fontweight="bold", color=INK)
    ax0.text(-160, 12, "All pixels are CONUS-only\n(no global sampling)", fontsize=7.5, color=MUTED, style="italic")

    # ---- (b) zoomed CONUS map, colored by class ----
    ax1 = fig.add_subplot(gs[1])
    conus = conus_states()
    conus.plot(ax=ax1, facecolor=MAP_FILL, edgecolor=MAP_EDGE, linewidth=1.0, zorder=1)
    ax1.set_facecolor(PANEL_BG)
    ax1.set_xlim(-127, -65)
    ax1.set_ylim(23, 50)
    ax1.set_aspect(1.35)
    ax1.set_xticks([]); ax1.set_yticks([])
    for spine in ax1.spines.values():
        spine.set_visible(False)

    colors = [CLASS_COLORS.get(c, "#888888") for c in df["dominant_pft"]]
    ax1.scatter(df["lon"], df["lat"], s=60, c=colors, edgecolor="white", linewidth=0.9, zorder=5)
    ax1.set_title(f"{title} (n={n_label})", loc="left", fontsize=12, fontweight="bold", color=INK)

    present_classes = [c for c in CLASS_COLORS if c in set(df["dominant_pft"])]
    handles = [Line2D([0], [0], marker="o", color="none", markerfacecolor=CLASS_COLORS[c],
                       markeredgecolor="white", markersize=9, label=CLASS_LABELS[c]) for c in present_classes]
    ax1.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.02), frameon=False,
               fontsize=8.5, ncol=4, handletextpad=0.5, columnspacing=1.2)

    fig.savefig(OUT / out_name, dpi=DPI, bbox_inches="tight")
    fig.savefig(OUT / out_name.replace(".png", ".pdf"), bbox_inches="tight")
    plt.close(fig)
    print("saved", out_name)


def draw_winloss(df, out_name):
    """Sorted per-pixel bar of R2(ERA5-cloud) - R2(gridMET), colored by which
    source wins - directly visualizes the 31/70 vs 39/70 split."""
    d = df.sort_values("R2_diff_era5_minus_gridmet", ascending=False).reset_index(drop=True)
    n_era5_win = (d["R2_diff_era5_minus_gridmet"] > 0).sum()
    n_gridmet_win = (d["R2_diff_era5_minus_gridmet"] < 0).sum()

    fig, ax = plt.subplots(figsize=(11, 5), constrained_layout=True)
    colors = [ERA5_COLOR if v > 0 else GRIDMET_COLOR for v in d["R2_diff_era5_minus_gridmet"]]
    ax.bar(range(len(d)), d["R2_diff_era5_minus_gridmet"], color=colors, width=0.82, zorder=3)
    ax.axhline(0, color=INK, linewidth=0.9, zorder=4)
    ax.set_xlim(-1, len(d))
    ax.set_xticks([])
    ax.set_ylabel("$R^2$(ERA5-cloud) $-$ $R^2$(gridMET)\n(same pixel, same 22-yr context)")
    ax.set_title(f"ERA5 scores higher on {n_era5_win}/{len(d)} pixels, gridMET higher on {n_gridmet_win}/{len(d)}",
                 loc="left", fontsize=13, fontweight="bold", color=INK)
    handles = [Rectangle((0, 0), 1, 1, color=ERA5_COLOR, label=f"ERA5 (cloud) higher  (n={n_era5_win})"),
               Rectangle((0, 0), 1, 1, color=GRIDMET_COLOR, label=f"gridMET higher  (n={n_gridmet_win})")]
    ax.legend(handles=handles, loc="upper right", frameon=False, fontsize=10)
    ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False)
    fig.savefig(OUT / out_name, dpi=DPI, bbox_inches="tight")
    fig.savefig(OUT / out_name.replace(".png", ".pdf"), bbox_inches="tight")
    plt.close(fig)
    print("saved", out_name)


def draw_byclass_comparison(df, out_name):
    """Grouped bar: mean R2 by dominant vegetation class, ERA5-cloud vs
    gridMET, same 70 pixels."""
    by_class = df.groupby("dominant_pft").agg(era5=("R2", "mean"), gridmet=("gridmet_R2", "mean"),
                                                n=("R2", "count")).sort_values("gridmet", ascending=False)
    x = np.arange(len(by_class))
    w = 0.36
    fig, ax = plt.subplots(figsize=(11, 5), constrained_layout=True)
    ax.bar(x - w / 2, by_class["gridmet"], width=w, color=GRIDMET_COLOR, label="gridMET", zorder=3)
    ax.bar(x + w / 2, by_class["era5"], width=w, color=ERA5_COLOR, label="ERA5 (cloud)", zorder=3)
    ax.axhline(0, color=INK, linewidth=0.9, zorder=4)
    ax.set_xticks(x)
    ax.set_xticklabels([f"{CLASS_LABELS[c].replace(', ', '\n')}\n(n={n})" for c, n in zip(by_class.index, by_class["n"])],
                        fontsize=8.5)
    ax.set_ylabel("Mean $R^2$ (zero-shot Chronos-2)")
    ax.set_title("Mean $R^2$ by vegetation class: ERA5 (cloud) vs. gridMET, same 70 pixels", loc="left",
                 fontsize=12.5, fontweight="bold", color=INK)
    ax.legend(frameon=False, fontsize=10, loc="lower left")
    ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False)
    fig.savefig(OUT / out_name, dpi=DPI, bbox_inches="tight")
    fig.savefig(OUT / out_name.replace(".png", ".pdf"), bbox_inches="tight")
    plt.close(fig)
    print("saved", out_name)


def main():
    pool = pd.read_csv(AELSTM_ROOT / "outputs/pft_multipixel_selection/pft_diverse_pixels.csv")
    p32 = pd.read_csv(ROOT / "outputs/purity32_pixel_study/zero_shot_32pixels.csv")
    pool32 = pool[pool["pixel_id"].isin(p32["site"])]
    draw_pixel_map(pool32, "map_32pixel_conus.png",
                    "Experiment 1: 32 purity-filtered CONUS pixels (gridMET)", 32)
    draw_pixel_map(pool, "map_70pixel_conus.png",
                    "Experiment 2: 70 CONUS pixels (cloud ERA5)", 70)

    matched = pd.read_csv(ROOT / "experiments/global_era5_chronos/outputs/era5_cloud_vs_gridmet_matched.csv")
    draw_winloss(matched, "era5_vs_gridmet_winloss.png")
    draw_byclass_comparison(matched, "era5_vs_gridmet_byclass.png")


if __name__ == "__main__":
    main()
