# Global-pool counterpart to Code/loyo_cv_anomaly_chronos2.py - see that
# file's module docstring for the full rationale (Prof. Wang's follow-up:
# forecast the LAI ANOMALY directly - LAI minus its per-calendar-position,
# context-years-only climatology - instead of forecasting raw LAI and only
# decomposing out the seasonal cycle afterward).
#
# Reuses run_loyo_cv_global.py's build_full_df/WINDOW_YEARS/FOLD_TEST_YEARS/
# MIN_CONTEXT_OBS/MIN_TEST_OBS and Code/loyo_cv_chronos2.py's
# circular_doy_climatology UNCHANGED - only run_fold's input construction
# changes (target = anomaly instead of raw LAI).
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from sklearn.metrics import r2_score

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "Code"))
import run_loyo_cv_global as glob_loyo  # noqa: E402
import loyo_cv_chronos2 as loyo  # noqa: E402 - reuses circular_doy_climatology unmodified

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT / "outputs/loyo_cv_anomaly"


def build_anomaly_inputs(df, test_year, window_start_year, target_col, feature_cols):
    years = df["date"].dt.year
    context_df = df[(years >= window_start_year) & (years < test_year)]
    future_df = df[years == test_year]

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
    raw_ground_truth = future_df[target_col].to_numpy(dtype="float32")
    return input_dict, prediction_length, context_df, future_df, future_anomaly_true, raw_ground_truth, clim_future


def run_fold(pipeline, df, pixel_id, test_year):
    window_start = test_year - glob_loyo.WINDOW_YEARS
    years = df["date"].dt.year
    context_df = df[(years >= window_start) & (years < test_year)]
    future_df = df[years == test_year]
    if len(context_df) < glob_loyo.MIN_CONTEXT_OBS or len(future_df) < glob_loyo.MIN_TEST_OBS:
        return None

    (input_dict, prediction_length, _, _, future_anomaly_true,
     raw_ground_truth, clim_future) = build_anomaly_inputs(
        df, test_year, window_start, glob_loyo.rec.cp.TARGET_COL, glob_loyo.rec.cp.FEATURE_COLS)

    t0 = time.time()
    pred_anomaly = glob_loyo.rec.rc2.predict_with_pipeline(pipeline, input_dict, prediction_length)
    elapsed = time.time() - t0

    r2_anomaly = r2_score(future_anomaly_true, pred_anomaly)
    pearson_anomaly = (np.corrcoef(future_anomaly_true, pred_anomaly)[0, 1]
                        if future_anomaly_true.std() > 0 and pred_anomaly.std() > 0 else np.nan)
    pred_raw_reconstructed = pred_anomaly + clim_future
    r2_raw_reconstructed = r2_score(raw_ground_truth, pred_raw_reconstructed)

    row = dict(site=pixel_id, test_year=test_year, window_start=window_start, window_years=glob_loyo.WINDOW_YEARS,
               n_context=len(input_dict["target"]), n_test=prediction_length,
               R2_anomaly=r2_anomaly, Pearson_r_anomaly=pearson_anomaly,
               R2_raw_reconstructed=r2_raw_reconstructed, elapsed_sec=round(elapsed, 2))
    print(f"[{pixel_id}/{test_year}] R2_anomaly={r2_anomaly:.4f} Pearson_r_anomaly={pearson_anomaly:.4f} "
          f"R2_raw_reconstructed={r2_raw_reconstructed:.4f} ({elapsed:.2f}s)")
    return row


def main():
    pool = pd.read_csv(glob_loyo.POOL_CSV)
    have_lai = {p.stem for p in glob_loyo.LAI_DIR.glob("*.csv")}
    pool = pool[pool["pixel_id"].isin(have_lai)].reset_index(drop=True)
    print(f"{len(pool)} pixels have usable LAI")

    device = "cuda" if torch.cuda.is_available() else "cpu"
    pipeline = glob_loyo.rec.rc2.get_pipeline(device)

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    t_start = time.time()
    rows = []
    for _, prow in pool.iterrows():
        pixel_id, lat, lon = prow["pixel_id"], prow["lat"], prow["lon"]
        df = glob_loyo.build_full_df(pixel_id, lat, lon).dropna(
            subset=glob_loyo.rec.cp.FEATURE_COLS + [glob_loyo.rec.cp.TARGET_COL])
        site_dir = OUTPUT_ROOT / pixel_id
        site_dir.mkdir(parents=True, exist_ok=True)
        for test_year in glob_loyo.FOLD_TEST_YEARS:
            out_path = site_dir / f"fold_{test_year}_anomaly_metrics.csv"
            if out_path.exists():
                rows.append(pd.read_csv(out_path).iloc[0].to_dict())
                continue
            row = run_fold(pipeline, df, pixel_id, test_year)
            if row is None:
                continue
            pd.DataFrame([row]).to_csv(out_path, index=False)
            rows.append(row)
        print(f"[{pixel_id}] done ({time.time() - t_start:.0f}s elapsed)")

    all_df = pd.DataFrame(rows)
    all_df.to_csv(OUTPUT_ROOT / "all_folds_anomaly.csv", index=False)
    print(f"\n{len(all_df)} folds across {len(pool)} pixels in {time.time()-t_start:.0f}s -> "
          f"{OUTPUT_ROOT / 'all_folds_anomaly.csv'}")
    print(f"\nmean R2_anomaly   = {all_df['R2_anomaly'].mean():.4f}   median = {all_df['R2_anomaly'].median():.4f}")
    print(f"mean Pearson_r_anomaly = {all_df['Pearson_r_anomaly'].mean():.4f}   "
          f"median = {all_df['Pearson_r_anomaly'].median():.4f}")
    print(f"mean R2_raw_reconstructed = {all_df['R2_raw_reconstructed'].mean():.4f}   "
          f"median = {all_df['R2_raw_reconstructed'].median():.4f}")


if __name__ == "__main__":
    main()
