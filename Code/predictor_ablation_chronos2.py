# Predictor sensitivity/ablation experiment for Chronos-2 zero-shot, using
# the exact same PREDICTOR_SETS as AELSTM/Code/predictor_ablation_experiment.py
# (see that file's header / the project README for the full design). Only
# zero-shot is tested here, not LoRA fine-tuned - fine-tuning would need its
# own hyperparameter re-search per predictor subset to stay fair (the
# improved-fine-tuning experiment's 6-config search x 8 subsets x 3 pixels),
# which is outside a "computationally manageable" scope; zero-shot also
# isolates the pure predictor-set effect without training-noise confound.
#
# common_pipeline.build_chronos_inputs() already accepts an arbitrary
# feature_cols list and uses it for BOTH past_covariates and
# future_covariates, so a dropped predictor is removed from both
# consistently by construction - no extra code path needed.
#
# The "full" (all 7) baseline is not rerun - read from the already-computed
# outputs/zero_shot/<site>/metrics.txt.
import argparse

import pandas as pd
import torch

import common_pipeline as cp
import run_chronos2 as rc2

ALL_PREDICTORS = ["tmmx", "tmmn", "pr", "srad", "vpd", "sph", "vs"]
PREDICTOR_SETS = {f"no_{p}": [c for c in ALL_PREDICTORS if c != p] for p in ALL_PREDICTORS}

# Phase 2 (added after Phase 1's importance ranking; same 4 configs and same
# selection rule as AELSTM/Code/predictor_ablation_experiment.py - see that
# file's header / the project README).
PREDICTOR_SETS["top3_essential"] = ["tmmx", "tmmn", "srad"]
PREDICTOR_SETS["drop_least_important_pair"] = ["tmmx", "tmmn", "srad", "vpd", "sph"]
PREDICTOR_SETS["no_temperature"] = ["pr", "srad", "vpd", "sph", "vs"]
PREDICTOR_SETS["no_moisture"] = ["tmmx", "tmmn", "pr", "srad", "vs"]

OUTPUT_DIR = cp.OUTPUTS_ROOT / "predictor_ablation"


def run_config(pipeline, df, site, config_name, feature_cols):
    input_dict, prediction_length, future_dates, ground_truth = cp.build_chronos_inputs(
        df, feature_cols=feature_cols
    )
    pred = rc2.predict_with_pipeline(pipeline, input_dict, prediction_length)
    metrics = cp.compute_metrics(ground_truth, pred)
    metrics.update(site=site, model="zero_shot", predictor_set=config_name,
                    n_predictors=len(feature_cols), predictors=",".join(feature_cols))
    print(f"[{site}/{config_name}] RMSE={metrics['RMSE']:.4f} R2={metrics['R2']:.4f}")
    return metrics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sites", nargs="+", default=cp.SITES)
    parser.add_argument("--configs", nargs="+", default=list(PREDICTOR_SETS.keys()))
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    pipeline = rc2.get_pipeline(args.device)

    for site in args.sites:
        df = cp.load_site_df(site)
        site_dir = OUTPUT_DIR / site
        site_dir.mkdir(parents=True, exist_ok=True)

        for config_name in args.configs:
            out_path = site_dir / f"{config_name}_metrics.csv"
            if out_path.exists():
                print(f"[{site}/{config_name}] already done, skipping")
                continue
            feature_cols = PREDICTOR_SETS[config_name]
            print(f"\n--- {site} / {config_name} (predictors: {feature_cols}) ---")
            metrics = run_config(pipeline, df, site, config_name, feature_cols)
            pd.DataFrame([metrics]).to_csv(out_path, index=False)

    all_results = []
    for site in args.sites:
        for f in sorted((OUTPUT_DIR / site).glob("*_metrics.csv")):
            all_results.append(pd.read_csv(f))
    combined = pd.concat(all_results, ignore_index=True)
    combined.to_csv(OUTPUT_DIR / "all_ablation_results.csv", index=False)
    print(f"\nSaved all_ablation_results.csv ({len(combined)} rows) to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
