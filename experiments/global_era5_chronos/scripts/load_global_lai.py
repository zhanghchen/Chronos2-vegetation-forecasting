# QC-filters the AppEEARS MOD15A2H.061 point-sample results (raw combined
# CSV, one row per pixel-date) and writes one `date,LAI` CSV per pixel,
# matching the exact column contract run_era5_chronos.py's build_merged_df
# expects (identical to the CONUS AELSTM site CSVs' `date,LAI` columns).
#
# QC rule (standard, conservative MOD15A2H convention): keep only
# observations where FparLai_QC's MODLAND bit == 0 ("Good quality, main
# algorithm with or without saturation") AND the raw Lai_500m value is in
# its valid range (<=100 raw, i.e. <=10.0 m^2/m^2 after the 0.1 scale
# factor - values 249-255 are documented fill/error codes, not real LAI).
# This drops ~32% of pixel-dates (mostly polar-night/persistent-cloud
# high-latitude observations), which is disclosed as a per-pixel coverage
# column in the output summary rather than silently interpolated over.
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW_CSV = ROOT / "data/global_lai/raw/chronos2-global70-lai-v1-MOD15A2H-061-results.csv"
OUT_DIR = ROOT / "data/global_lai/processed"
OUT_DIR.mkdir(parents=True, exist_ok=True)

MIN_TOTAL_OBS = 100   # need a reasonable amount of context signal
MIN_TEST_YEAR_OBS = 5  # need at least a few 2022 observations to score against
TEST_YEAR = 2022


def main():
    df = pd.read_csv(RAW_CSV, usecols=["ID", "Date", "MOD15A2H_061_Lai_500m", "MOD15A2H_061_FparLai_QC_MODLAND"])
    df.columns = ["pixel_id", "date", "lai_raw", "modland_qc"]
    df["date"] = pd.to_datetime(df["date"])

    good = df[(df["modland_qc"] == "0b0") & (df["lai_raw"] <= 100)].copy()
    good["LAI"] = good["lai_raw"] * 0.1  # ScaleFactor from the MOD15A2H.061 product spec

    coverage_rows = []
    n_written = 0
    for pixel_id, g in good.groupby("pixel_id"):
        g = g.sort_values("date")[["date", "LAI"]].reset_index(drop=True)
        n_test = (g["date"].dt.year == TEST_YEAR).sum()
        usable = len(g) >= MIN_TOTAL_OBS and n_test >= MIN_TEST_YEAR_OBS
        coverage_rows.append({"pixel_id": pixel_id, "n_good_obs": len(g), "n_test_year_obs": n_test,
                               "date_min": g["date"].min(), "date_max": g["date"].max(), "usable": usable})
        if usable:
            g.to_csv(OUT_DIR / f"{pixel_id}.csv", index=False)
            n_written += 1

    cov = pd.DataFrame(coverage_rows).sort_values("n_good_obs")
    cov.to_csv(ROOT / "data/global_lai/coverage_report.csv", index=False)
    print(f"{n_written}/{len(cov)} pixels have usable LAI ({MIN_TOTAL_OBS}+ good obs, {MIN_TEST_YEAR_OBS}+ in {TEST_YEAR})")
    print(f"\nExcluded pixels (insufficient coverage):")
    print(cov[~cov["usable"]][["pixel_id", "n_good_obs", "n_test_year_obs"]].to_string(index=False))
    print(f"\nSaved per-pixel CSVs to {OUT_DIR}")
    print(f"Saved coverage report to data/global_lai/coverage_report.csv")


if __name__ == "__main__":
    main()
