# Follow-up to the pool-averaged composite-position analysis
# (build_loyo_composite_position_r2.py): that analysis showed the
# POOL-AVERAGED R2/Pearson r sequence is weak (near zero, sometimes
# negative), because it averages over all 70/68 pixels including many
# weak ones. This script asks the complementary question: setting the
# cross-pixel average aside, what do the curves look like for the pixels
# that individually perform best?
#
# Selection: top 10 pixels per pool by their ORIGINAL per-pixel LOYO-CV
# mean R2 (the "mean" column of loyo_<pool>_per_pixel_summary.csv - the
# standard within-year R2, averaged across the 11 held-out years; this is
# the same "year-to-year average R2" metric already reported for every
# pixel in the original LOYO-CV study, and the same selection metric used
# for the transparent top-20 subgroup slide). This is an explicitly
# top-performer selection, not a representative sample - see the caption
# baked into each figure.
#
# For those 10 pixels, plots each one's own R2-by-composite-position and
# Pearson-r-by-composite-position curves (from the per-pixel raw output of
# build_loyo_composite_position_r2.py) as small multiples, annotated with
# that pixel's original inter-annual mean R2.
from pathlib import Path

import matplotlib
matplotlib.use("AGG")
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path("/home/deh25003/chronos-forecasting/Chronos2-vegetation-forecasting")
SUMMARY_DIR = ROOT / "outputs/loyo_cv_pools_summary"
N_TOP = 10

R2_COLOR = "#2a78d6"      # categorical slot 1 (blue)
PEARSON_COLOR = "#eb6834"  # categorical slot 2 (orange)
INK = "#0b0b0b"
MUTED = "#898781"
GRID = "#e1e0d9"


def build_pool(pool_key, pool_label, n_sites_total):
    per_pixel_summary = pd.read_csv(SUMMARY_DIR / f"loyo_{pool_key}_per_pixel_summary.csv")
    raw = pd.read_csv(SUMMARY_DIR / f"loyo_{pool_key}_r2_by_position_per_pixel_raw.csv")

    top10 = per_pixel_summary.sort_values("mean", ascending=False).head(N_TOP).reset_index(drop=True)
    top10_sites = top10["site"].tolist()
    top10.rename(columns={"mean": "inter_annual_mean_R2", "var": "inter_annual_variance"}, inplace=True)
    top10[["site", "inter_annual_mean_R2", "median", "inter_annual_variance"]].to_csv(
        SUMMARY_DIR / f"loyo_{pool_key}_top10_pixels_summary.csv", index=False)

    fig, axes = plt.subplots(2, 5, figsize=(20, 7.5), sharex=True, sharey=True, constrained_layout=True)
    fig.suptitle(
        f"{pool_label}: top {N_TOP} of {n_sites_total} pixels by their own inter-annual mean R²\n"
        "(individual best performers, NOT the pool average — selection rule: ranked by each pixel's own "
        "mean R² across its 11 held-out years)",
        fontsize=12.5, fontweight="bold", ha="center")

    for ax, (_, row) in zip(axes.flat, top10.iterrows()):
        site = row["site"]
        g = raw[raw["site"] == site].sort_values("composite_index")
        # Reindex to the full 1..46 position range so matplotlib breaks the
        # line (NaN gap) at composite positions this pixel didn't have
        # enough held-out years for, instead of drawing a straight line
        # across the gap as if there were real data there.
        g = g.set_index("composite_index").reindex(range(1, 47)).reset_index()
        ax.axhline(0, color=GRID, lw=1, zorder=0)
        ax.plot(g["composite_index"], g["R2"], color=R2_COLOR, lw=1.8, marker="o", ms=3, label="R²")
        ax.plot(g["composite_index"], g["Pearson_r"], color=PEARSON_COLOR, lw=1.8, marker="o", ms=3, label="Pearson r")
        ax.set_title(f"{site}\ninter-annual mean R²={row['inter_annual_mean_R2']:.3f}", fontsize=10, color=INK)
        ax.set_ylim(-1.05, 1.05)
        ax.tick_params(labelsize=8, colors=MUTED)
        for spine in ("top", "right"):
            ax.spines[spine].set_visible(False)
        for spine in ("left", "bottom"):
            ax.spines[spine].set_color(GRID)

    for ax in axes[-1, :]:
        ax.set_xlabel("8-day composite position", fontsize=9, color=MUTED)
    for ax in axes[:, 0]:
        ax.set_ylabel("value", fontsize=9, color=MUTED)

    handles, labels = axes.flat[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=2, frameon=False, fontsize=11, bbox_to_anchor=(0.5, -0.04))

    stem = f"loyo_{pool_key}_top10_pixel_curves"
    fig.savefig(SUMMARY_DIR / f"{stem}.png", dpi=200, bbox_inches="tight")
    fig.savefig(SUMMARY_DIR / f"{stem}.pdf", bbox_inches="tight")
    plt.close(fig)
    print(f"saved {stem}.png — top 10 sites: {top10_sites}")
    print(top10[["site", "inter_annual_mean_R2", "inter_annual_variance"]].to_string(index=False))


def main():
    build_pool("conus70", "CONUS", 70)
    print()
    build_pool("global68", "Global", 68)


if __name__ == "__main__":
    main()
