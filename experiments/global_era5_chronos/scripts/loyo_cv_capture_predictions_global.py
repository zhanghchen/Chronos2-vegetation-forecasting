# Same purpose as Code/loyo_cv_capture_predictions.py, for the global pool:
# re-runs the SAME folds as run_loyo_cv_global.py (imports and reuses its
# build_full_df/FOLD_TEST_YEARS/WINDOW_YEARS/MIN_CONTEXT_OBS/MIN_TEST_OBS
# unmodified - identical fold construction), additionally saving the
# per-timestep (date, ground_truth, prediction, composite_index) arrays,
# needed for Prof. Wang's requested across-year, fixed-composite-position
# R^2 analysis. Writes to a NEW directory
# (experiments/global_era5_chronos/outputs/loyo_cv_predictions/) - never
# touches outputs/loyo_cv/ (the original per-fold metrics).
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_loyo_cv_global as loyo  # noqa: E402 - reuses build_full_df, FOLD_TEST_YEARS, WINDOW_YEARS, MIN_* unmodified

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT / "outputs/loyo_cv_predictions"
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)


def main():
    pool = pd.read_csv(loyo.POOL_CSV)
    have_lai = {p.stem for p in loyo.LAI_DIR.glob("*.csv")}
    pool = pool[pool["pixel_id"].isin(have_lai)].reset_index(drop=True)
    print(f"{len(pool)} pixels have usable LAI")

    device = "cuda" if __import__("torch").cuda.is_available() else "cpu"
    pipeline = loyo.rec.rc2.get_pipeline(device)

    t_start = time.time()
    n_done, n_skipped = 0, 0
    for _, prow in pool.iterrows():
        pixel_id, lat, lon = prow["pixel_id"], prow["lat"], prow["lon"]
        site_dir = OUTPUT_ROOT / pixel_id
        site_dir.mkdir(parents=True, exist_ok=True)
        df = loyo.build_full_df(pixel_id, lat, lon).dropna(
            subset=loyo.rec.cp.FEATURE_COLS + [loyo.rec.cp.TARGET_COL])

        for test_year in loyo.FOLD_TEST_YEARS:
            out_path = site_dir / f"fold_{test_year}_predictions.csv"
            if out_path.exists():
                continue
            window_start = test_year - loyo.WINDOW_YEARS
            years = df["date"].dt.year
            context_df = df[(years >= window_start) & (years < test_year)]
            future_df = df[years == test_year]
            if len(context_df) < loyo.MIN_CONTEXT_OBS or len(future_df) < loyo.MIN_TEST_OBS:
                n_skipped += 1
                continue

            input_dict = {
                "target": context_df[loyo.rec.cp.TARGET_COL].to_numpy(dtype="float32"),
                "past_covariates": {c: context_df[c].to_numpy(dtype="float32") for c in loyo.rec.cp.FEATURE_COLS},
                "future_covariates": {c: future_df[c].to_numpy(dtype="float32") for c in loyo.rec.cp.FEATURE_COLS},
            }
            prediction_length = len(future_df)
            ground_truth = future_df[loyo.rec.cp.TARGET_COL].to_numpy(dtype="float32")
            pred = loyo.rec.rc2.predict_with_pipeline(pipeline, input_dict, prediction_length)

            dates = pd.to_datetime(future_df["date"].to_numpy())
            out = pd.DataFrame({
                "date": dates, "ground_truth": ground_truth, "prediction": pred,
                "site": pixel_id, "test_year": test_year,
                "composite_index": ((dates.dayofyear - 1) // 8 + 1),
            })
            out.to_csv(out_path, index=False)
            n_done += 1
        print(f"[{pixel_id}] done ({time.time()-t_start:.0f}s elapsed)")

    print(f"\nSaved predictions for {n_done} new folds ({n_skipped} skipped, insufficient coverage) "
          f"across {len(pool)} pixels in {time.time()-t_start:.0f}s")


if __name__ == "__main__":
    main()
