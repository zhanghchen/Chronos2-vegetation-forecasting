# Re-runs a handful of SPECIFIC (site, test_year) GPP-anomaly LOYO-CV folds
# (already scored in outputs/loyo_cv_gpp_anomaly/all_folds_gpp_anomaly.csv)
# and this time ALSO saves the per-timestep predicted-vs-true arrays, which
# loyo_cv_gpp_anomaly_chronos2.py does not persist (only aggregated metrics).
# Needed for the deck's Part 3 prediction-curve figure. Mirrors
# Code/loyo_cv_capture_predictions.py's pattern, pointed at the GPP-anomaly
# protocol (Code/loyo_cv_gpp_anomaly_chronos2.py) instead of raw LAI.
import argparse
from pathlib import Path

import pandas as pd
import torch

import common_pipeline as cp
import run_chronos2 as rc2
import loyo_cv_chronos2 as loyo
from loyo_cv_anomaly_chronos2 import build_anomaly_inputs
from loyo_cv_gpp_anomaly_chronos2 import TARGET_COL, load_gpp_site_df

OUTPUT_ROOT = cp.OUTPUTS_ROOT / "loyo_cv_gpp_anomaly_predictions"
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)


def main(pairs):
    device = "cuda" if torch.cuda.is_available() else "cpu"
    pipeline = rc2.get_pipeline(device)

    for site, test_year in pairs:
        df = load_gpp_site_df(site)
        df = df.dropna(subset=[TARGET_COL] + cp.FEATURE_COLS).reset_index(drop=True)
        window_start = test_year - loyo.WINDOW_YEARS
        (input_dict, prediction_length, future_dates, future_anomaly_true,
         raw_ground_truth, clim_future) = build_anomaly_inputs(
            df, test_year, window_start, target_col=TARGET_COL, feature_cols=cp.FEATURE_COLS
        )
        pred_anomaly = rc2.predict_with_pipeline(pipeline, input_dict, prediction_length)
        pred_raw = pred_anomaly + clim_future

        out = pd.DataFrame({
            "date": pd.to_datetime(future_dates),
            "true_anomaly": future_anomaly_true,
            "pred_anomaly": pred_anomaly,
            "true_raw_gpp": raw_ground_truth,
            "pred_raw_gpp_reconstructed": pred_raw,
            "climatology": clim_future,
            "site": site, "test_year": test_year,
        })
        out_path = OUTPUT_ROOT / f"{site}_{test_year}_predictions.csv"
        out.to_csv(out_path, index=False)
        print(f"[{site}/{test_year}] saved {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pairs", nargs="+", required=True,
                         help="site:year pairs, e.g. px007_shrubs_ne:2019")
    args = parser.parse_args()
    pairs = [tuple(p.split(":")) for p in args.pairs]
    pairs = [(s, int(y)) for s, y in pairs]
    main(pairs)
