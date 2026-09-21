# Summary tables + figures for the 70-pixel (68 usable) non-CONUS global
# zero-shot Chronos-2 experiment (cloud ERA5 + MODIS MOD15A2H LAI). Reads
# only already-saved results (outputs/era5_global70.csv) - no new runs.
from pathlib import Path

import geopandas as gpd
import matplotlib
matplotlib.use("AGG")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "outputs"
POOL_CSV = ROOT / "data_selection/global_candidate_pixels_70.csv"

DPI = 300
INK = "#1C2119"
MUTED = "#5C6355"
MAP_FILL = "#EEF0EA"
MAP_EDGE = "#FFFFFF"
PANEL_BG = "#FAFAF7"
COUNTRIES_SHP = "/home/deh25003/.local/share/cartopy/shapefiles/natural_earth/cultural/ne_110m_admin_0_countries.shp"

# ESA CCI class names (hyphenated, as used by select_global_pixels.py) -
# same color identity as the CONUS deck's CLASS_COLORS (Code/build_purity32_pixel_comparison.py)
# wherever the class also appears there, extended with 3 additional
# classes (TREES-BE, SHRUBS-BE, TREES-BE not present in the CONUS pool).
CLASS_COLORS = {
    "TREES-NE": "#1B7837", "TREES-BD": "#5AAE61", "TREES-BE": "#2C9E5B", "TREES-ND": "#A6DBA0",
    "SHRUBS-NE": "#B35806", "SHRUBS-BE": "#8C6BB1", "SHRUBS-BD": "#E08214", "SHRUBS-ND": "#FDB863",
    "GRASS-NAT": "#762A83", "GRASS-MAN": "#C2A5CF",
}


def main():
    df = pd.read_csv(OUT_DIR / "era5_global70.csv")
    pool = pd.read_csv(POOL_CSV)
    ok = df[df["R2"].notna()].copy().sort_values("R2", ascending=False).reset_index(drop=True)
    print(f"{len(ok)} succeeded out of {len(pool)} selected pixels")

    ok.to_csv(OUT_DIR / "era5_global70_clean.csv", index=False)
    overall = ok[["RMSE", "MAE", "MAPE", "R2", "Pearson_r"]].agg(["mean", "median", "std", "min", "max"])
    overall.to_csv(OUT_DIR / "era5_global70_summary_overall.csv")
    by_class = ok.groupby("dominant_pft")["R2"].agg(["count", "mean", "median", "std", "min", "max"]).sort_values("mean", ascending=False)
    by_class.to_csv(OUT_DIR / "era5_global70_summary_by_class.csv")
    by_region = ok.groupby("region")["R2"].agg(["count", "mean", "median"]).sort_values("mean", ascending=False)
    by_region.to_csv(OUT_DIR / "era5_global70_summary_by_region.csv")
    print(overall)
    print(by_class)
    print(by_region)

    # --- world map, colored by dominant vegetation class ---
    merged = pool.merge(ok[["site", "R2"]], left_on="pixel_id", right_on="site", how="left")
    fig, ax = plt.subplots(figsize=(14, 7.5), constrained_layout=True)
    world = gpd.read_file(COUNTRIES_SHP)
    world.plot(ax=ax, facecolor=MAP_FILL, edgecolor=MAP_EDGE, linewidth=0.5, zorder=1)
    ax.set_facecolor(PANEL_BG)
    ax.set_xlim(-180, 180)
    ax.set_ylim(-60, 82)
    ax.set_xticks([]); ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)
    colors = [CLASS_COLORS.get(c, "#888888") for c in merged["dominant_pft"]]
    ax.scatter(merged["lon"], merged["lat"], s=55, c=colors, edgecolor="white", linewidth=0.8, zorder=5)
    ax.set_title(f"70 non-CONUS global pixels selected for the ERA5+MODIS zero-shot experiment "
                 f"(CONUS explicitly excluded by design; {len(ok)}/70 had usable LAI)", loc="left",
                 fontsize=12.5, fontweight="bold", color=INK)
    present_classes = [c for c in CLASS_COLORS if c in set(merged["dominant_pft"])]
    handles = [Line2D([0], [0], marker="o", color="none", markerfacecolor=CLASS_COLORS[c],
                       markeredgecolor="white", markersize=9, label=c.replace("-", " ").title()) for c in present_classes]
    ax.legend(handles=handles, loc="lower left", frameon=False, fontsize=8.5, ncol=5,
              bbox_to_anchor=(0.0, -0.02))
    fig.savefig(OUT_DIR / "global70_map.png", dpi=DPI, bbox_inches="tight")
    fig.savefig(OUT_DIR / "global70_map.pdf", bbox_inches="tight")
    plt.close(fig)
    print("saved global70_map.png")

    # --- R2 by pixel (sorted) + by-class boxplot ---
    fig2, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6.5), constrained_layout=True,
                                     gridspec_kw={"width_ratios": [1.8, 1]})
    colors2 = [CLASS_COLORS.get(c, "#888888") for c in ok["dominant_pft"]]
    ax1.bar(range(len(ok)), ok["R2"], color=colors2, edgecolor="black", linewidth=0.3)
    ax1.axhline(0, color="black", lw=0.8)
    ax1.axhline(ok["R2"].median(), color="#0072B2", lw=1.2, ls="--")
    ax1.set_xticks(range(len(ok)))
    ax1.set_xticklabels(ok["site"], rotation=90, fontsize=5.5)
    ax1.set_ylabel("Zero-shot Chronos-2 $R^2$ (global, ERA5 + MODIS LAI)")
    ax1.set_title(f"(a) All {len(ok)} usable pixels, sorted by $R^2$", loc="left")
    handles2 = [plt.Rectangle((0, 0), 1, 1, color=c) for c in CLASS_COLORS.values()]
    ax1.legend(handles2 + [Line2D([0], [0], color="#0072B2", ls="--")],
               [c.replace("-", " ").title() for c in CLASS_COLORS] + [f"median={ok['R2'].median():.3f}"],
               frameon=False, fontsize=7, loc="lower left", ncol=2)
    order = ok.groupby("dominant_pft")["R2"].median().sort_values(ascending=False).index
    data = [ok[ok["dominant_pft"] == c]["R2"].values for c in order]
    bp = ax2.boxplot(data, tick_labels=[c.replace("-", " ").title() for c in order], patch_artist=True, showmeans=True)
    for patch, c in zip(bp["boxes"], order):
        patch.set_facecolor(CLASS_COLORS.get(c, "#888888"))
        patch.set_alpha(0.7)
    ax2.axhline(0, color="black", lw=0.8)
    ax2.set_xticklabels([c.replace("-", " ").title() for c in order], rotation=45, ha="right", fontsize=8)
    ax2.set_ylabel("$R^2$")
    ax2.set_title("(b) By dominant vegetation class", loc="left")
    fig2.savefig(OUT_DIR / "global70_r2_by_pixel_and_class.png", dpi=DPI, bbox_inches="tight")
    fig2.savefig(OUT_DIR / "global70_r2_by_pixel_and_class.pdf", bbox_inches="tight")
    plt.close(fig2)
    print("saved global70_r2_by_pixel_and_class.png")

    # --- context-length vs R2 (the key confound: MODIS gaps shorten context for many pixels) ---
    fig3, ax = plt.subplots(figsize=(7.5, 6), constrained_layout=True)
    ax.scatter(ok["context_steps"], ok["R2"], c=colors2, edgecolor="black", linewidth=0.5, s=45, zorder=3)
    ax.set_xlabel("Context length (8-day steps actually available, 2000-2021)")
    ax.set_ylabel("$R^2$")
    ax.axhline(0, color="black", lw=0.8)
    corr = np.corrcoef(ok["context_steps"], ok["R2"])[0, 1]
    ax.set_title(f"$R^2$ vs. available context length (r={corr:.2f})", loc="left", fontsize=12, fontweight="bold")
    fig3.savefig(OUT_DIR / "global70_context_vs_r2.png", dpi=DPI, bbox_inches="tight")
    plt.close(fig3)
    print("saved global70_context_vs_r2.png")


if __name__ == "__main__":
    main()
