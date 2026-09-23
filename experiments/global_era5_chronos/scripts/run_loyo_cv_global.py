# Leave-One-Year-Out Cross-Validation (LOYO-CV), zero-shot only, for the
# global (non-CONUS) ERA5+MODIS pixel pool. Mirrors Code/loyo_cv_chronos2.py's
# design EXACTLY (same fixed 12-year rolling window, same FOLD_TEST_YEARS,
# same metrics via common_pipeline.compute_metrics) so the two pools are
# directly comparable - the only difference is the data source (this pool's
# merged LAI+ERA5 dataframe comes from run_era5_chronos.build_merged_df,
# not Code/common_pipeline.load_site_df) and the addition of minimum-
# coverage-per-fold checks, since MODIS LAI here is irregular/gapped (not a
# clean daily series like gridMET) - a fold is skipped, not silently run on
# too little data, if it doesn't meet MIN_CONTEXT_OBS / MIN_TEST_OBS.
#
# Does NOT compute ACC (anomaly correlation vs. day-of-year climatology,
# which loyo_cv_chronos2.py does for the CONUS pool) - omitted here since
# building a reliable climatology from an already-sparse, irregular record
# is a separate methodological question not addressed in this pass;
# disclosed as a limitation in the report, not silently dropped.
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_era5_chronos as rec  # noqa: E402 - provides build_merged_df, cp, rc2, HDF5 warm-up

ROOT = Path(__file__).resolve().parents[1]
POOL_CSV = ROOT / "data_selection/global_candidate_pixels_70.csv"
LAI_DIR = ROOT / "data/global_lai/processed"
OUTPUT_ROOT = ROOT / "outputs/loyo_cv"
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

WINDOW_YEARS = 12
FOLD_TEST_YEARS = list(range(2012, 2023))  # identical to Code/loyo_cv_chronos2.py
ALL_YEARS = list(range(2000, 2023))
MIN_CONTEXT_OBS = 20  # need a real amount of context signal, not just a handful of points
MIN_TEST_OBS = 4      # need enough held-out points for R2/Pearson r to mean anything


def build_full_df(pixel_id, lat, lon):
    return rec.build_merged_df(pixel_id, lat, lon, ALL_YEARS, source="cloud", lai_dir=LAI_DIR)


def run_fold(pipeline, df, pixel_id, test_year):
    window_start = test_year - WINDOW_YEARS
    years = df["date"].dt.year
    context_df = df[(years >= window_start) & (years < test_year)]
    future_df = df[years == test_year]
    if len(context_df) < MIN_CONTEXT_OBS or len(future_df) < MIN_TEST_OBS:
        return None

    input_dict = {
        "target": context_df[rec.cp.TARGET_COL].to_numpy(dtype="float32"),
        "past_covariates": {c: context_df[c].to_numpy(dtype="float32") for c in rec.cp.FEATURE_COLS},
        "future_covariates": {c: future_df[c].to_numpy(dtype="float32") for c in rec.cp.FEATURE_COLS},
    }
    prediction_length = len(future_df)
    ground_truth = future_df[rec.cp.TARGET_COL].to_numpy(dtype="float32")

    t0 = time.time()
    pred = rec.rc2.predict_with_pipeline(pipeline, input_dict, prediction_length)
    elapsed = time.time() - t0

    m = rec.cp.compute_metrics(ground_truth, pred)
    m.update(site=pixel_id, mode="zero_shot", test_year=test_year, window_start=window_start,
              window_years=WINDOW_YEARS, n_context=len(context_df), n_test=prediction_length,
              elapsed_sec=round(elapsed, 2))
    return m


def main():
    pool = pd.read_csv(POOL_CSV)
    have_lai = {p.stem for p in LAI_DIR.glob("*.csv")}
    pool = pool[pool["pixel_id"].isin(have_lai)].reset_index(drop=True)
    print(f"{len(pool)}/70 pixels have usable LAI - running LOYO-CV (zero-shot) on all of them")

    device = "cuda" if __import__("torch").cuda.is_available() else "cpu"
    pipeline = rec.rc2.get_pipeline(device)

    n_folds_done = 0
    n_folds_skipped_insufficient = 0
    t_start = time.time()
    for _, prow in pool.iterrows():
        pixel_id, lat, lon = prow["pixel_id"], prow["lat"], prow["lon"]
        site_dir = OUTPUT_ROOT / pixel_id
        site_dir.mkdir(parents=True, exist_ok=True)
        df = build_full_df(pixel_id, lat, lon).dropna(subset=rec.cp.FEATURE_COLS + [rec.cp.TARGET_COL])

        for test_year in FOLD_TEST_YEARS:
            fold_path = site_dir / f"fold_{test_year}_metrics.csv"
            if fold_path.exists():
                continue
            m = run_fold(pipeline, df, pixel_id, test_year)
            if m is None:
                n_folds_skipped_insufficient += 1
                continue
            pd.DataFrame([m]).to_csv(fold_path, index=False)
            n_folds_done += 1
            print(f"[{pixel_id}/{test_year}] R2={m['R2']:.4f} RMSE={m['RMSE']:.4f} "
                  f"n_context={m['n_context']} n_test={m['n_test']} ({time.time()-t_start:.0f}s elapsed)")

    print(f"\nDone: {n_folds_done} folds computed, {n_folds_skipped_insufficient} skipped "
          f"(insufficient context/test coverage) in {time.time()-t_start:.0f}s")


if __name__ == "__main__":
    main()
