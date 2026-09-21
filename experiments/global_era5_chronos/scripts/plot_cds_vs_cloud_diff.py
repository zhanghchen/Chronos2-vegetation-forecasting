# Visual (not just correlation-based) comparison of CDS ("real"/reference)
# ERA5 vs. cloud (Google ARCO-ERA5) ERA5 for the 7 final Chronos-2 climate
# variables, evergreen pixel, 2021-2022 - the same period/data already used
# for the numeric equivalence validation in
# reports/ERA5_CLOUD_EQUIVALENCE_REPORT.md. Per explicit request, this
# shows the actual data (time series overlay + running difference) rather
# than only summarizing it as a correlation coefficient.
from pathlib import Path

import matplotlib
matplotlib.use("AGG")
import matplotlib.dates
import matplotlib.pyplot as plt
import pandas as pd

SCRATCH = Path("/gpfs/sharedfs1/vscode_temp/claude-1024136/-home-deh25003-chronos-forecasting/7e05eaf0-dc4c-49b9-9938-e50cb41eb412/scratchpad")
OUT_DIR = Path("/home/deh25003/chronos-forecasting/Chronos2-vegetation-forecasting/experiments/global_era5_chronos/outputs")

CDS_COLOR = "#2F6F5E"     # matches the project's gridMET/"reference" green
CLOUD_COLOR = "#3A6EA5"   # matches the project's ERA5/cloud blue
DIFF_COLOR = "#B5651D"

VARS = {
    "tmmx": "Max temperature (K)", "tmmn": "Min temperature (K)",
    "pr": "Precipitation (mm/day)", "srad": "Solar radiation (W/m²)",
    "vpd": "Vapor pressure deficit (kPa)", "sph": "Specific humidity (kg/kg)",
    "vs": "Wind speed (m/s)",
}


def main():
    cds = pd.read_csv(SCRATCH / "cds_final_evergreen_2021_2022.csv", index_col=0, parse_dates=True)
    cloud = pd.read_csv(SCRATCH / "arco_final_evergreen_2021_2022.csv", index_col=0, parse_dates=True)
    common = cds.index.intersection(cloud.index)
    cds, cloud = cds.loc[common], cloud.loc[common]

    fig, axes = plt.subplots(len(VARS), 2, figsize=(15, 3.1 * len(VARS)), constrained_layout=True,
                              gridspec_kw={"width_ratios": [2.3, 1]})
    fig.suptitle("CDS (reference) vs. cloud ERA5 — evergreen pixel, 2021–2022, daily", fontsize=15, fontweight="bold")

    for i, (col, label) in enumerate(VARS.items()):
        ax_ts, ax_diff = axes[i, 0], axes[i, 1]
        ax_ts.plot(common, cds[col], color=CDS_COLOR, lw=1.1, label="CDS (reference)")
        ax_ts.plot(common, cloud[col], color=CLOUD_COLOR, lw=1.1, ls="--", label="Cloud (ARCO-ERA5)")
        ax_ts.set_ylabel(label, fontsize=9.5)
        ax_ts.tick_params(labelsize=8)
        if i == 0:
            ax_ts.legend(frameon=False, fontsize=9, loc="upper right")
        ax_ts.set_title(f"({chr(97+i)}1) {col} — daily time series", loc="left", fontsize=10)

        diff = cloud[col] - cds[col]
        ax_diff.fill_between(common, diff, 0, color=DIFF_COLOR, alpha=0.6, linewidth=0)
        ax_diff.axhline(0, color="black", lw=0.7)
        ax_diff.set_title(f"({chr(97+i)}2) cloud − CDS difference", loc="left", fontsize=10)
        ax_diff.tick_params(labelsize=8)
        mae = diff.abs().mean()
        ax_diff.text(0.02, 0.92, f"mean |diff| = {mae:.4g}", transform=ax_diff.transAxes,
                     fontsize=8.5, va="top", color=DIFF_COLOR)

    fig.savefig(OUT_DIR / "cds_vs_cloud_era5_timeseries.png", dpi=220, bbox_inches="tight")
    fig.savefig(OUT_DIR / "cds_vs_cloud_era5_timeseries.pdf", bbox_inches="tight")
    plt.close(fig)
    print("saved cds_vs_cloud_era5_timeseries.png")

    # --- compact 3-variable version for slide embedding: one clear-agreement
    # example (tmmx), the one real discrepancy (pr), and one more
    # agreement example (srad) ---
    slide_vars = {"tmmx": VARS["tmmx"], "pr": VARS["pr"], "srad": VARS["srad"]}
    fig4, axes4 = plt.subplots(len(slide_vars), 2, figsize=(13, 2.6 * len(slide_vars)), constrained_layout=True,
                                gridspec_kw={"width_ratios": [2.3, 1]})
    for i, (col, label) in enumerate(slide_vars.items()):
        ax_ts, ax_diff = axes4[i, 0], axes4[i, 1]
        ax_ts.plot(common, cds[col], color=CDS_COLOR, lw=1.1, label="CDS (reference)")
        ax_ts.plot(common, cloud[col], color=CLOUD_COLOR, lw=1.1, ls="--", label="Cloud (ARCO-ERA5)")
        ax_ts.set_ylabel(label, fontsize=10)
        ax_ts.tick_params(labelsize=9)
        if i == 0:
            ax_ts.legend(frameon=False, fontsize=10, loc="upper right")
        diff = cloud[col] - cds[col]
        ax_diff.fill_between(common, diff, 0, color=DIFF_COLOR, alpha=0.6, linewidth=0)
        ax_diff.axhline(0, color="black", lw=0.7)
        ax_diff.tick_params(labelsize=9)
        ax_diff.xaxis.set_major_locator(matplotlib.dates.YearLocator())
        ax_diff.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%Y"))
        ax_ts.xaxis.set_major_locator(matplotlib.dates.MonthLocator([1, 4, 7, 10]))
        mae = diff.abs().mean()
        ax_diff.set_title(f"cloud−CDS, mean|diff|={mae:.3g}", loc="left", fontsize=9.5, color=DIFF_COLOR)
    axes4[0, 0].set_title("Daily time series, evergreen pixel, 2021-2022", loc="left", fontsize=10.5)
    fig4.savefig(OUT_DIR / "cds_vs_cloud_era5_timeseries_slide.png", dpi=220, bbox_inches="tight")
    plt.close(fig4)
    print("saved cds_vs_cloud_era5_timeseries_slide.png")


if __name__ == "__main__":
    main()
