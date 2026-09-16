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

CODE_DIR = Path(__file__).resolve().parents[3] / "Code"
sys.path.insert(0, str(CODE_DIR))
# era5_source (netCDF4/xarray/HDF5) MUST be imported -- and MUST actually
# open a real file -- before run_chronos2 (torch/transformers, which pulls
# in tensorflow's own bundled libhdf5). Confirmed empirically: merely
# importing the netCDF4/xarray *module* first is not enough -- the HDF5
# library only locks in its (correct) bindings once a real file-open call
# happens; without a prior real open, importing tensorflow afterward still
# corrupts every subsequent netCDF4 read in the same process
# ("OSError: NetCDF: HDF error"), even though the files themselves are
# completely fine (verified: base env and an isolated chronos2-env
# subprocess both open them without issue).
import era5_source as es  # noqa: E402
import era5_source_arco as es_arco  # noqa: E402
import xarray as _xr  # noqa: E402
_warm_up_candidates = sorted(es.CACHE_DIR.glob("*.nc"))
if _warm_up_candidates:
    with _xr.open_dataset(_warm_up_candidates[0]):
        pass
import common_pipeline as cp  # noqa: E402
import run_chronos2 as rc2  # noqa: E402

SOURCES = {"cds": es, "cloud": es_arco}

# The full 70-pixel pool's LAI CSVs (including the 4 original core/legacy
# sites, which are byte-identical to their AELSTM copies - verified) live
# here, not in AELSTM/data/processed/sites (which lacks the 66 px0* pixels).
AELSTM_SITES_DIR = Path("/home/deh25003/chronos-forecasting/Chronos2-vegetation-forecasting/data/processed/sites")
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


def build_merged_df(site_name, lat, lon, era5_years, source="cds"):
    lai_df = pd.read_csv(AELSTM_SITES_DIR / f"{site_name}.csv", parse_dates=["date"])[["date", "LAI"]]
    era5_daily = SOURCES[source].build_gridmet_equivalent(lat, lon, era5_years)
    era5_aligned = aggregate_era5_to_lai_windows(era5_daily, lai_df["date"].to_numpy())
    merged = lai_df.merge(era5_aligned, on="date", how="inner")
    return merged


def run_one_pixel(site, lat, lon, era5_years, test_year=cp.TEST_YEAR, source="cds", pipeline=None, verbose=True):
    """Runs the full merge + zero-shot Chronos-2 pipeline for one pixel and
    writes its results, exactly like main() below - factored out so a batch
    driver can call this in a loop while reusing one already-loaded Chronos-2
    `pipeline` (loading it fresh per pixel would be wasteful: it's the same
    zero-shot model every time)."""
    if verbose:
        print(f"Building merged LAI+ERA5 dataframe for {site} ({lat}, {lon}) [source={source}]...")
    df = build_merged_df(site, lat, lon, era5_years, source=source)
    df = df.dropna(subset=cp.FEATURE_COLS + [cp.TARGET_COL])
    if verbose:
        print(f"{len(df)} aligned rows, {df['date'].dt.year.min()}-{df['date'].dt.year.max()}")

    input_dict, prediction_length, future_dates, ground_truth = cp.build_chronos_inputs(df, test_year=test_year)
    if verbose:
        print(f"context={len(input_dict['target'])} steps, prediction_length={prediction_length}")

    if pipeline is None:
        device = "cuda" if __import__("torch").cuda.is_available() else "cpu"
        pipeline = rc2.get_pipeline(device)
    pred = rc2.predict_with_pipeline(pipeline, input_dict, prediction_length)
    metrics = cp.compute_metrics(ground_truth, pred)
    metrics.update(site=site, source=f"ERA5-{source}", test_year=test_year, context_steps=len(input_dict["target"]))

    # "cds" keeps the original, already-published filenames untouched (backward
    # compatible, never silently overwritten by the new cloud path); "cloud"
    # writes to distinctly-suffixed files so it can never collide with them.
    suffix = "" if source == "cds" else f"_{source}"
    out_dir = OUT_DIR / site
    out_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"date": future_dates, "ground_truth": ground_truth, "prediction": pred}).to_csv(
        out_dir / f"predictions_era5{suffix}.csv", index=False
    )
    with open(out_dir / f"metrics_era5{suffix}.txt", "w") as f:
        for k, v in metrics.items():
            f.write(f"{k}: {v}\n")
    if verbose:
        print(f"[{site}/ERA5-{source}] " + " ".join(f"{k}={v:.4f}" for k, v in metrics.items() if isinstance(v, float)))
    return metrics, pipeline


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--lon", type=float, required=True)
    ap.add_argument("--site", type=str, required=True, help="name of an existing AELSTM site CSV for LAI history")
    ap.add_argument("--era5-years", type=int, nargs="+", required=True)
    ap.add_argument("--test-year", type=int, default=cp.TEST_YEAR)
    ap.add_argument("--source", choices=["cds", "cloud"], default="cds",
                     help="cds = original Copernicus CDS API pipeline (era5_source.py); "
                          "cloud = Google ARCO-ERA5 Zarr store (era5_source_arco.py)")
    args = ap.parse_args()

    metrics, _ = run_one_pixel(args.site, args.lat, args.lon, args.era5_years, args.test_year, args.source)

    # side-by-side with the existing gridMET zero-shot result, if it exists
    gridmet_metrics_path = cp.OUTPUTS_ROOT / "zero_shot" / args.site / "metrics.txt"
    if gridmet_metrics_path.exists():
        print(f"\n--- comparison: {args.site} ---")
        print(f"gridMET (existing): {gridmet_metrics_path.read_text().strip()}")
        print(f"ERA5 (this run): R2={metrics['R2']:.4f} RMSE={metrics['RMSE']:.4f}")


if __name__ == "__main__":
    main()
