# Prof. Wang's follow-up on top of the existing LOYO-CV study: rather than
# forecasting raw LAI and only AFTERWARD decomposing out the seasonal cycle
# (as the composite-position R2/Pearson-r analysis and this file's own
# ACC metric already do), feed Chronos-2 the LAI ANOMALY directly - LAI
# minus its per-calendar-position climatology - as both context and
# forecast target. This forces the model to forecast genuine year-to-year
# deviation from normal as its actual task, not as a post-hoc decomposition
# of a raw-LAI forecast that was mostly driven by seasonal-shape matching.
#
# Reuses loyo_cv_chronos2.py's WINDOW_YEARS/FOLD_TEST_YEARS/
# circular_doy_climatology UNCHANGED (same fold structure, same no-leakage
# climatology: always fit on context years only, via
# circular_doy_climatology(context_df, target_dates) - this is exactly
# what compute_acc() already calls, so the anomaly here uses the identical,
# already-reviewed no-leakage baseline). Only run_fold's input construction
# changes: target = LAI - climatology instead of raw LAI.
#
# past_covariates/future_covariates (the weather data) are NOT anomalized -
# Chronos-2 still sees raw climate values, exactly matching the standing
# protocol ("结合过去和未来的天气数据来预测lai的variation" - weather stays
# as-is, only the LAI target becomes an anomaly).
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

OUTPUT_ROOT = cp.OUTPUTS_ROOT / "loyo_cv_anomaly"


def build_anomaly_inputs(df, test_year, window_start_year, target_col=cp.TARGET_COL, feature_cols=cp.FEATURE_COLS):
    years = df["date"].dt.year
    context_df = df[(years >= window_start_year) & (years < test_year)]
    future_df = df[years == test_year]

    # No-leakage climatology: fit on context years only (circular_doy_climatology's
    # train_df argument), then applied to BOTH the context's own dates (to anomalize
    # the model's input) and the held-out test year's dates (to anomalize the target
    # the model is scored against) - identical function/call pattern this project
    # already uses for the ACC metric, just applied to build the model's actual
    # training target instead of a post-hoc diagnostic.
    clim_context = loyo.circular_doy_climatology(context_df, context_df["date"].to_numpy(), target_col=target_col)
    clim_future = loyo.circular_doy_climatology(context_df, future_df["date"].to_numpy(), target_col=target_col)

    context_anomaly = context_df[target_col].to_numpy(dtype="float32") - clim_context.astype("float32")
    future_anomaly_true = future_df[target_col].to_numpy(dtype="float32") - clim_future.astype("float32")

    input_dict = {
        "target": context_anomaly,
        "past_covariates": {c: context_df[c].to_numpy(dtype="float32") for c in feature_cols},
        "future_covariates": {c: future_df[c].to_numpy(dtype="float32") for c in feature_cols},
    }
    prediction_length = len(future_df)
    future_dates = future_df["date"].to_numpy()
    raw_ground_truth = future_df[target_col].to_numpy(dtype="float32")
    return input_dict, prediction_length, future_dates, future_anomaly_true, raw_ground_truth, clim_future


def run_fold(pipeline, df, site, test_year):
    window_start = test_year - loyo.WINDOW_YEARS
    (input_dict, prediction_length, future_dates, future_anomaly_true,
     raw_ground_truth, clim_future) = build_anomaly_inputs(df, test_year, window_start)

    if len(input_dict["target"]) < 20 or prediction_length < 4:
        return None

    t0 = time.time()
    pred_anomaly = rc2.predict_with_pipeline(pipeline, input_dict, prediction_length)
    elapsed = time.time() - t0

    r2_anomaly = r2_score(future_anomaly_true, pred_anomaly)
    pearson_anomaly = (np.corrcoef(future_anomaly_true, pred_anomaly)[0, 1]
                        if future_anomaly_true.std() > 0 and pred_anomaly.std() > 0 else np.nan)

    # Secondary sanity check: reconstruct raw LAI (pred_anomaly + climatology) and
    # compare its R2 to the ALREADY-PUBLISHED raw-LAI LOYO-CV R2 for this exact
    # fold - they should be in a similar ballpark (not reusing the same forecast,
    # but using the same context window/climate/model), confirming the anomaly
    # reformulation isn't silently discarding information Chronos-2 could use.
    pred_raw_reconstructed = pred_anomaly + clim_future
    r2_raw_reconstructed = r2_score(raw_ground_truth, pred_raw_reconstructed)

    row = dict(site=site, test_year=test_year, window_start=window_start, window_years=loyo.WINDOW_YEARS,
               n_context=len(input_dict["target"]), n_test=prediction_length,
               R2_anomaly=r2_anomaly, Pearson_r_anomaly=pearson_anomaly,
               R2_raw_reconstructed=r2_raw_reconstructed, elapsed_sec=round(elapsed, 1))
    print(f"[{site}/{test_year}] R2_anomaly={r2_anomaly:.4f} Pearson_r_anomaly={pearson_anomaly:.4f} "
          f"R2_raw_reconstructed={r2_raw_reconstructed:.4f} ({elapsed:.1f}s)")
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sites", nargs="+", default=cp.SITES)
    parser.add_argument("--test-years", type=int, nargs="+", default=loyo.FOLD_TEST_YEARS)
    args = parser.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    pipeline = rc2.get_pipeline(device)

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    t_start = time.time()
    rows = []
    for site in args.sites:
        df = cp.load_site_df(site)
        # A handful of raw NaN LAI rows (QC-bad retrievals) contaminate the
        # climatology for EVERY year at that calendar position, since
        # circular_doy_climatology pools across all context years within a
        # +/-4-day window: one bad row makes .mean() NaN for every year's
        # value near that day-of-year, not just the bad row itself (found on
        # px007_shrubs_ne: 5 raw NaN rows -> 60 NaN context anomaly points).
        # Dropped up front, same as the physics-guided LAI scripts do.
        n_before = len(df)
        df = df.dropna(subset=[cp.TARGET_COL] + cp.FEATURE_COLS).reset_index(drop=True)
        if len(df) < n_before:
            print(f"[{site}] dropped {n_before - len(df)} NaN rows")
        site_dir = OUTPUT_ROOT / site
        site_dir.mkdir(parents=True, exist_ok=True)
        for test_year in args.test_years:
            out_path = site_dir / f"fold_{test_year}_anomaly_metrics.csv"
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
    all_df.to_csv(OUTPUT_ROOT / "all_folds_anomaly.csv", index=False)
    print(f"\n{len(all_df)} folds across {len(args.sites)} sites in {time.time()-t_start:.0f}s -> "
          f"{OUTPUT_ROOT / 'all_folds_anomaly.csv'}")
    print(f"\nmean R2_anomaly   = {all_df['R2_anomaly'].mean():.4f}   median = {all_df['R2_anomaly'].median():.4f}")
    print(f"mean Pearson_r_anomaly = {all_df['Pearson_r_anomaly'].mean():.4f}   "
          f"median = {all_df['Pearson_r_anomaly'].median():.4f}")
    print(f"mean R2_raw_reconstructed = {all_df['R2_raw_reconstructed'].mean():.4f}   "
          f"median = {all_df['R2_raw_reconstructed'].median():.4f}")


if __name__ == "__main__":
    main()
