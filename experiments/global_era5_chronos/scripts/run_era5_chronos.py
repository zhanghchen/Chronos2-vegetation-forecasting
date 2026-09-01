# Runs the EXISTING Chronos-2 zero-shot pipeline (Code/common_pipeline.py,
# reused unmodified - not reimplemented, per the project's explicit
# instruction) with ERA5-derived climate covariates substituted for
# gridMET. Aligns ERA5's daily values to each LAI 8-day composite window
# using the SAME mean-aggregation convention the existing gridMET pipeline
# uses (AELSTM/preprocessing/nc_csv.py's get_climate_mean), so the ERA5
# and gridMET results are a fair, like-for-like comparison (Part 22).
#
# Reusable command:
#   python run_era5_chronos.py --lat 30.525 --lon -82.4333 --site evergreen --test-year 2022
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

CODE_DIR = Path(__file__).resolve().parents[2] / "Code"
sys.path.insert(0, str(CODE_DIR))
import common_pipeline as cp  # noqa: E402
import run_chronos2 as rc2  # noqa: E402
import era5_source as es  # noqa: E402

AELSTM_SITES_DIR = Path("/home/deh25003/chronos-forecasting/AELSTM/data/processed/sites")
OUT_DIR = Path(__file__).resolve().parents[1] / "results"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def aggregate_era5_to_lai_windows(era5_daily, lai_dates, window_days=7):
    """Mirrors nc_csv.py's get_climate_mean exactly: for each LAI
    composite starting at `date`, take the mean of the ERA5 daily values
    over [date, min(date+window_days, year_end)] - the LAI 8-day
    composite's own window, not a naive calendar-week aggregation (Part
    5's explicit requirement)."""
    rows = []
    for date in lai_dates:
        date = pd.Timestamp(date)
        year_end = pd.Timestamp(year=date.year, month=12, day=31)
        end_date = min(date + pd.Timedelta(days=window_days), year_end)
        window = era5_daily.loc[date:end_date]
        if len(window) == 0:
            rows.append({c: np.nan for c in era5_daily.columns})
        else:
            rows.append(window.mean().to_dict())
    out = pd.DataFrame(rows)
    out.insert(0, "date", lai_dates)
    return out


def build_merged_df(site_name, lat, lon, era5_years):
    lai_df = pd.read_csv(AELSTM_SITES_DIR / f"{site_name}.csv", parse_dates=["date"])[["date", "LAI"]]
    era5_daily = es.build_gridmet_equivalent(lat, lon, era5_years)
    era5_aligned = aggregate_era5_to_lai_windows(era5_daily, lai_df["date"].to_numpy())
    merged = lai_df.merge(era5_aligned, on="date", how="inner")
    return merged


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--lon", type=float, required=True)
    ap.add_argument("--site", type=str, required=True, help="name of an existing AELSTM site CSV for LAI history")
    ap.add_argument("--era5-years", type=int, nargs="+", required=True)
    ap.add_argument("--test-year", type=int, default=cp.TEST_YEAR)
    args = ap.parse_args()

    print(f"Building merged LAI+ERA5 dataframe for {args.site} ({args.lat}, {args.lon})...")
    df = build_merged_df(args.site, args.lat, args.lon, args.era5_years)
    df = df.dropna(subset=cp.FEATURE_COLS + [cp.TARGET_COL])
    print(f"{len(df)} aligned rows, {df['date'].dt.year.min()}-{df['date'].dt.year.max()}")

    input_dict, prediction_length, future_dates, ground_truth = cp.build_chronos_inputs(
        df, test_year=args.test_year
    )
    print(f"context={len(input_dict['target'])} steps, prediction_length={prediction_length}")

    device = "cuda" if __import__("torch").cuda.is_available() else "cpu"
    pipeline = rc2.get_pipeline(device)
    pred = rc2.predict_with_pipeline(pipeline, input_dict, prediction_length)
    metrics = cp.compute_metrics(ground_truth, pred)
    metrics.update(site=args.site, source="ERA5", test_year=args.test_year)

    out_dir = OUT_DIR / args.site
    out_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"date": future_dates, "ground_truth": ground_truth, "prediction": pred}).to_csv(
        out_dir / "predictions_era5.csv", index=False
    )
    with open(out_dir / "metrics_era5.txt", "w") as f:
        for k, v in metrics.items():
            f.write(f"{k}: {v}\n")
    print(f"[{args.site}/ERA5] " + " ".join(f"{k}={v:.4f}" for k, v in metrics.items() if isinstance(v, float)))

    # side-by-side with the existing gridMET zero-shot result, if it exists
    gridmet_metrics_path = cp.OUTPUTS_ROOT / "zero_shot" / args.site / "metrics.txt"
    if gridmet_metrics_path.exists():
        print(f"\n--- comparison: {args.site} ---")
        print(f"gridMET (existing): {gridmet_metrics_path.read_text().strip()}")
        print(f"ERA5 (this run): R2={metrics['R2']:.4f} RMSE={metrics['RMSE']:.4f}")


if __name__ == "__main__":
    main()
