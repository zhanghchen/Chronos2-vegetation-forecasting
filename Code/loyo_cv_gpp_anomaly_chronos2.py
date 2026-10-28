# Zero-shot Chronos-2 LOYO-CV on GPP ANOMALY, mirroring
# loyo_cv_anomaly_chronos2.py's LAI-anomaly protocol EXACTLY (same
# WINDOW_YEARS/FOLD_TEST_YEARS/circular_doy_climatology/build_anomaly_inputs,
# reused unmodified, just target_col="GPP" instead of "LAI" and reading
# from data/processed/sites_gpp/ instead of data/processed/sites/) - so the
# two pools' R2_anomaly/Pearson_r_anomaly numbers are directly comparable,
# per Prof. Wang's request to contrast GPP vs. LAI forecasting performance.
#
# This is the INITIAL/preliminary experiment (zero-shot only, no physics
# guidance yet) - physics-guided fine-tuning on GPP is a deliberate later
# step, not done here (data/processed/sites_gpp/ + this script's results
# are exactly what that later step will need).
import argparse
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from sklearn.metrics import r2_score

import common_pipeline as cp
import run_chronos2 as rc2
import loyo_cv_chronos2 as loyo  # reuses WINDOW_YEARS, FOLD_TEST_YEARS, circular_doy_climatology unmodified
from loyo_cv_anomaly_chronos2 import build_anomaly_inputs  # reused unmodified, called with target_col="GPP"

TARGET_COL = "GPP"
SITES_DIR = cp.DATA_DIR / "data" / "processed" / "sites_gpp"
OUTPUT_ROOT = cp.OUTPUTS_ROOT / "loyo_cv_gpp_anomaly"


def load_gpp_site_df(site):
    path = SITES_DIR / f"{site}.csv"
    if not path.exists():
        return None
    return pd.read_csv(path, parse_dates=["date"])


def available_sites():
    return sorted(p.stem for p in SITES_DIR.glob("*.csv"))


def run_fold(pipeline, df, site, test_year):
    window_start = test_year - loyo.WINDOW_YEARS
    (input_dict, prediction_length, future_dates, future_anomaly_true,
     raw_ground_truth, clim_future) = build_anomaly_inputs(
        df, test_year, window_start, target_col=TARGET_COL, feature_cols=cp.FEATURE_COLS
    )

    if len(input_dict["target"]) < 20 or prediction_length < 4:
        return None

    t0 = time.time()
    pred_anomaly = rc2.predict_with_pipeline(pipeline, input_dict, prediction_length)
    elapsed = time.time() - t0

    r2_anomaly = r2_score(future_anomaly_true, pred_anomaly)
    pearson_anomaly = (np.corrcoef(future_anomaly_true, pred_anomaly)[0, 1]
                        if future_anomaly_true.std() > 0 and pred_anomaly.std() > 0 else np.nan)

    pred_raw_reconstructed = pred_anomaly + clim_future
    r2_raw_reconstructed = r2_score(raw_ground_truth, pred_raw_reconstructed)

    row = dict(site=site, test_year=test_year, window_start=window_start, window_years=loyo.WINDOW_YEARS,
               n_context=len(input_dict["target"]), n_test=prediction_length,
               R2_anomaly=r2_anomaly, Pearson_r_anomaly=pearson_anomaly,
               R2_raw_reconstructed=r2_raw_reconstructed, elapsed_sec=round(elapsed, 1))
    print(f"[{site}/{test_year}] GPP R2_anomaly={r2_anomaly:.4f} Pearson_r_anomaly={pearson_anomaly:.4f} "
          f"R2_raw_reconstructed={r2_raw_reconstructed:.4f} ({elapsed:.1f}s)")
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sites", nargs="+", default=None,
                         help="defaults to every site with a data/processed/sites_gpp/<site>.csv")
    parser.add_argument("--test-years", type=int, nargs="+", default=loyo.FOLD_TEST_YEARS)
    args = parser.parse_args()
    sites = args.sites if args.sites is not None else available_sites()
    if not sites:
        raise RuntimeError(f"No site CSVs found in {SITES_DIR} - run Code/build_conus_gpp_sites.py first")
    print(f"Running {len(sites)} sites x {len(args.test_years)} test years")

    device = "cuda" if torch.cuda.is_available() else "cpu"
    pipeline = rc2.get_pipeline(device)

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    t_start = time.time()
    rows = []
    for site in sites:
        df = load_gpp_site_df(site)
        if df is None:
            print(f"[{site}] no GPP site CSV, skipping")
            continue
        n_before = len(df)
        df = df.dropna(subset=[TARGET_COL] + cp.FEATURE_COLS).reset_index(drop=True)
        if len(df) < n_before:
            print(f"[{site}] dropped {n_before - len(df)} NaN rows")
        site_dir = OUTPUT_ROOT / site
        site_dir.mkdir(parents=True, exist_ok=True)
        for test_year in args.test_years:
            out_path = site_dir / f"fold_{test_year}_gpp_anomaly_metrics.csv"
            if out_path.exists():
                rows.append(pd.read_csv(out_path).iloc[0].to_dict())
                continue
            row = run_fold(pipeline, df, site, test_year)
            if row is None:
                continue
            pd.DataFrame([row]).to_csv(out_path, index=False)
            rows.append(row)
        print(f"[{site}] done ({time.time() - t_start:.0f}s elapsed)")

    all_df = pd.DataFrame(rows)
    all_df.to_csv(OUTPUT_ROOT / "all_folds_gpp_anomaly.csv", index=False)
    print(f"\n{len(all_df)} folds across {len(sites)} sites in {time.time()-t_start:.0f}s -> "
          f"{OUTPUT_ROOT / 'all_folds_gpp_anomaly.csv'}")
    print(f"\nmean R2_anomaly   = {all_df['R2_anomaly'].mean():.4f}   median = {all_df['R2_anomaly'].median():.4f}")
    print(f"mean Pearson_r_anomaly = {all_df['Pearson_r_anomaly'].mean():.4f}   "
          f"median = {all_df['Pearson_r_anomaly'].median():.4f}")


if __name__ == "__main__":
    main()
