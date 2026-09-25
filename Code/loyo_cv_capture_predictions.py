# Re-runs the SAME zero-shot LOYO-CV folds as loyo_cv_chronos2.py (imports
# and reuses its build_chronos_inputs_loyo/WINDOW_YEARS/FOLD_TEST_YEARS
# unmodified - identical fold construction, identical model), but this
# time ALSO saves the per-timestep (date, ground_truth, prediction) arrays
# for every fold, which the original script does not persist (it only
# saves aggregated per-fold metrics). Needed for Prof. Wang's requested
# analysis: R^2 computed ACROSS the 11 held-out years at each FIXED
# position in the 8-day composite cycle (e.g. "the 1st composite of the
# year, across all 11 years"), which isolates genuine inter-annual
# variability from the (much easier) within-year seasonal-shape match that
# the existing per-fold R^2 mostly reflects.
#
# Writes to a NEW directory (outputs/loyo_cv_predictions/) - never touches
# outputs/loyo_cv/ (the original, already-published fold metrics).
import sys
import time
from pathlib import Path

import pandas as pd
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common_pipeline as cp  # noqa: E402
import run_chronos2 as rc2  # noqa: E402
import loyo_cv_chronos2 as loyo  # noqa: E402 - reuses build_chronos_inputs_loyo, FOLD_TEST_YEARS, WINDOW_YEARS unmodified

OUTPUT_ROOT = cp.OUTPUTS_ROOT / "loyo_cv_predictions"


def main(sites):
    device = "cuda" if torch.cuda.is_available() else "cpu"
    pipeline = rc2.get_pipeline(device)

    t_start = time.time()
    n_done = 0
    for site in sites:
        df = cp.load_site_df(site)
        site_dir = OUTPUT_ROOT / site
        site_dir.mkdir(parents=True, exist_ok=True)

        for test_year in loyo.FOLD_TEST_YEARS:
            out_path = site_dir / f"fold_{test_year}_predictions.csv"
            if out_path.exists():
                continue
            window_start = test_year - loyo.WINDOW_YEARS
            input_dict, prediction_length, future_dates, ground_truth = loyo.build_chronos_inputs_loyo(
                df, test_year, window_start
            )
            pred = rc2.predict_with_pipeline(pipeline, input_dict, prediction_length)
            dates = pd.to_datetime(future_dates)
            out = pd.DataFrame({
                "date": dates, "ground_truth": ground_truth, "prediction": pred,
                "site": site, "test_year": test_year,
                "composite_index": ((dates.dayofyear - 1) // 8 + 1),
            })
            out.to_csv(out_path, index=False)
            n_done += 1
        print(f"[{site}] done ({time.time()-t_start:.0f}s elapsed)")

    print(f"\nSaved predictions for {n_done} new folds across {len(sites)} sites in {time.time()-t_start:.0f}s")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--sites", nargs="+", required=True)
    args = parser.parse_args()
    main(args.sites)
