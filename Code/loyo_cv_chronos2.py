# Leave-One-Year-Out Cross-Validation (LOYO-CV) for Chronos-2 (zero-shot and
# LoRA fine-tuned): rolling-origin CV with a FIXED 12-year training window,
# matching AELSTM/Code/loyo_cv_experiment.py's design exactly (see that
# file's header for the full rationale - fixed window, not expanding, to
# avoid confounding "hard year" with "how much training data this fold
# happened to get"; not classic all-other-years LOYO, which would leak
# future years into a forecasting model). For each held-out test year Y,
# context = years Y-12..Y-1, future_covariates/target = year Y only.
#
# IMPORTANT FIX vs. common_pipeline.build_chronos_inputs(): that function
# computes `future = df.iloc[split_idx:]`, i.e. everything from the split
# point to the END of the dataframe. That's only correct because the
# existing single-split experiments always use test_year=2022, the last
# year in the file. Looped over earlier fold years, it would silently
# include every subsequent year too (e.g. test_year=2012 would evaluate
# against 2012-2022 concatenated, not just 2012). build_chronos_inputs_loyo()
# below restricts `future` to exactly the target test year and `context` to
# exactly the fixed 12-year window before it.
#
# Reuses run_chronos2.py's get_pipeline/predict_with_pipeline/
# finetune_pipeline unmodified. Every prediction is scored against RAW
# observed LAI (which is what this project's data already is - no smoothing
# step, unlike AELSTM), plus an anomaly correlation coefficient (ACC)
# against a per-fold day-of-year climatology built only from that fold's
# training years (duplicated from AELSTM's loyo_cv_experiment.py rather than
# imported, per this project's established independence from AELSTM's code).
#
# Loads the pretrained model once and reuses it across every fold/site/mode
# to avoid repeated model-load cost. Saves results incrementally, one file
# per (site, test_year, mode), so a crash partway through doesn't lose
# already-computed folds.
import argparse
import time

import numpy as np
import pandas as pd
import torch

import common_pipeline as cp
import run_chronos2 as rc2

WINDOW_YEARS = 12
FOLD_TEST_YEARS = list(range(2012, 2023))  # 2012..2022 inclusive -> 11 folds
CLIMATOLOGY_TOL_DAYS = 4

OUTPUT_ROOT = cp.OUTPUTS_ROOT / "loyo_cv"


def build_chronos_inputs_loyo(df, test_year, window_start_year,
                               target_col=cp.TARGET_COL, feature_cols=cp.FEATURE_COLS):
    years = df["date"].dt.year
    context_df = df[(years >= window_start_year) & (years < test_year)]
    future_df = df[years == test_year]

    input_dict = {
        "target": context_df[target_col].to_numpy(dtype="float32"),
        "past_covariates": {c: context_df[c].to_numpy(dtype="float32") for c in feature_cols},
        "future_covariates": {c: future_df[c].to_numpy(dtype="float32") for c in feature_cols},
    }
    prediction_length = len(future_df)
    future_dates = future_df["date"].to_numpy()
    ground_truth = future_df[target_col].to_numpy(dtype="float32")
    return input_dict, prediction_length, future_dates, ground_truth


def circular_doy_climatology(train_df, target_dates, target_col=cp.TARGET_COL, tol_days=CLIMATOLOGY_TOL_DAYS):
    train_doy = train_df["date"].dt.dayofyear.to_numpy()
    train_lai = train_df[target_col].to_numpy()
    target_doy = pd.DatetimeIndex(target_dates).dayofyear.to_numpy()

    clim = np.empty(len(target_doy))
    for i, d in enumerate(target_doy):
        delta = np.abs(train_doy - d)
        circ_dist = np.minimum(delta, 365 - delta)
        match = circ_dist <= tol_days
        clim[i] = train_lai[match].mean() if match.any() else train_lai.mean()
    return clim


def compute_acc(obs, pred, climatology):
    obs_anom = np.asarray(obs) - climatology
    pred_anom = np.asarray(pred) - climatology
    if np.std(obs_anom) == 0 or np.std(pred_anom) == 0:
        return np.nan
    return float(np.corrcoef(obs_anom, pred_anom)[0, 1])


def run_fold(pipeline, df, site, test_year, modes):
    window_start = test_year - WINDOW_YEARS
    input_dict, prediction_length, future_dates, ground_truth = build_chronos_inputs_loyo(
        df, test_year, window_start
    )
    years = df["date"].dt.year
    train_df = df[(years >= window_start) & (years < test_year)]
    climatology = circular_doy_climatology(train_df, future_dates)

    rows = []
    for mode in modes:
        t0 = time.time()
        if mode == "zero_shot":
            pred = rc2.predict_with_pipeline(pipeline, input_dict, prediction_length)
        else:
            finetuned = rc2.finetune_pipeline(pipeline, input_dict, prediction_length, f"{site}_loyo_{test_year}")
            pred = rc2.predict_with_pipeline(finetuned, input_dict, prediction_length)
        elapsed = time.time() - t0

        m = cp.compute_metrics(ground_truth, pred)
        m["ACC"] = compute_acc(ground_truth, pred, climatology)
        m.update(
            site=site, mode=mode, test_year=test_year, window_start=window_start,
            window_years=WINDOW_YEARS, n_context=len(input_dict["target"]),
            n_test=prediction_length, elapsed_sec=round(elapsed, 1),
        )
        rows.append(m)
        print(f"[{site}/{test_year}/{mode}] RMSE={m['RMSE']:.4f} R2={m['R2']:.4f} "
              f"ACC={m['ACC']:.4f} ({elapsed:.1f}s)")

    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sites", nargs="+", default=cp.SITES)
    parser.add_argument("--test-years", type=int, nargs="+", default=FOLD_TEST_YEARS)
    parser.add_argument("--modes", nargs="+", default=["zero_shot", "finetuned_lora"],
                         choices=["zero_shot", "finetuned_lora"])
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    args = parser.parse_args()

    pipeline = rc2.get_pipeline(args.device)

    for site in args.sites:
        df = cp.load_site_df(site)
        site_dir = OUTPUT_ROOT / site
        site_dir.mkdir(parents=True, exist_ok=True)

        for test_year in args.test_years:
            fold_path = site_dir / f"fold_{test_year}_metrics.csv"
            if fold_path.exists():
                existing = pd.read_csv(fold_path)
                if set(args.modes).issubset(set(existing["mode"])):
                    print(f"[{site}/{test_year}] already done, skipping (delete {fold_path} to rerun)")
                    continue
            print(f"\n########## {site} / test_year={test_year} "
                  f"(context {test_year - WINDOW_YEARS}-{test_year - 1}) ##########")
            fold_df = run_fold(pipeline, df, site, test_year, args.modes)
            fold_df.to_csv(fold_path, index=False)

        fold_files = [site_dir / f"fold_{y}_metrics.csv" for y in args.test_years if (site_dir / f"fold_{y}_metrics.csv").exists()]
        all_folds = pd.concat([pd.read_csv(f) for f in fold_files], ignore_index=True)
        all_folds.to_csv(site_dir / "all_folds_metrics.csv", index=False)
        print(f"Saved all_folds_metrics.csv ({len(all_folds)} rows) to {site_dir}")


if __name__ == "__main__":
    main()
