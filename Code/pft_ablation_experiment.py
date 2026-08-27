# PFT ablation for Chronos-2: baseline (LAI+climate, zero-shot) vs.
# +fractional-PFT vs. +dominant-PFT covariates, across the 4 sites (3
# reused representative pixels + 1 new genuinely-mixed pixel). Zero-shot
# only (no fine-tuning) - isolates the PFT question from the
# already-answered "does fine-tuning help" question (it doesn't, per
# CHRONOS2_ADVANCED_FINETUNING_REPORT.md).
#
# PFT is fed exactly as verified from Chronos-2's source: a constant value
# per year, broadcast across every 8-day step in both past_covariates and
# future_covariates (Chronos-2 has no native static-covariate slot - see
# common_pipeline.build_chronos_inputs, which already accepts an arbitrary
# feature_cols list, used here unmodified).
#
# IMPORTANT CAVEAT (found while implementing): Chronos-2's own
# InstanceNorm (src/chronos/chronos2/model.py + chronos_bolt.py) computes
# each covariate's loc/scale from THAT covariate's own values across the
# given context+future window (per-row, dim=-1 reduction) - not a
# shared/global statistic. PFT is exactly constant across 2000-2022 for
# every one of our 4 sites (verified), so its per-row std is 0. Chronos-2's
# InstanceNorm substitutes scale=eps for a zero-variance row, so the
# normalized covariate becomes (c-c)/eps = 0 for EVERY step, regardless of
# what constant c actually was. This means a single-pixel zero-shot run
# structurally cannot receive any PFT signal through this covariate
# channel - not a bug in our implementation, an architectural property of
# Chronos-2's per-series normalization. We run the experiment anyway (cheap,
# zero-shot) as the literal, verified implementation of the user's request,
# and the perturbation diagnostic (pft_sensitivity_diagnostic.py) directly
# demonstrates this mechanism empirically.
from pathlib import Path

import pandas as pd

# pft_features (netCDF4) MUST be imported, and open its first file, before
# torch/transformers are imported - this conda env's HDF5 library otherwise
# fails on netCDF4's first Dataset open with "HDF error" if torch has
# already been loaded first (a one-time library-init ordering conflict,
# found while testing this script; harmless once the first open succeeds).
import pft_features as pf
pf.site_year_vector(30.0, -90.0, 2010)  # warm-up open, before any torch import

import torch

import common_pipeline as cp
import run_chronos2 as rc2

OUTPUT_DIR = cp.OUTPUTS_ROOT / "pft_ablation"
SITES = ["evergreen", "low_amplitude", "high_amplitude_deciduous", "mixed_forest_grass"]
CONDITIONS = ["baseline", "fractional", "dominant"]


def condition_feature_cols(condition):
    if condition == "baseline":
        return cp.FEATURE_COLS
    if condition == "fractional":
        return cp.FEATURE_COLS + pf.FRAC_COLS
    if condition == "dominant":
        return cp.FEATURE_COLS + pf.DOM_COLS
    raise ValueError(condition)


def load_augmented_df(site):
    df = cp.load_site_df(site)
    lat, lon = df["lat"].iloc[0], df["lon"].iloc[0]
    return pf.augment_site_dataframe(df, lat, lon)


def run_one(pipeline, site, condition, df):
    feature_cols = condition_feature_cols(condition)
    input_dict, prediction_length, future_dates, ground_truth = cp.build_chronos_inputs(
        df, feature_cols=feature_cols
    )
    pred = rc2.predict_with_pipeline(pipeline, input_dict, prediction_length)
    metrics = cp.compute_metrics(ground_truth, pred)
    metrics.update(site=site, condition=condition, n_pft_cols=len(feature_cols) - len(cp.FEATURE_COLS))

    out_dir = OUTPUT_DIR / site / condition
    out_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"date": future_dates, "ground_truth": ground_truth, "prediction": pred}).to_csv(
        out_dir / "predictions.csv", index=False
    )
    with open(out_dir / "metrics.txt", "w") as f:
        for k, v in metrics.items():
            f.write(f"{k}: {v}\n")
    print(f"[{site}/{condition}] " + " ".join(f"{k}={v:.4f}" for k, v in metrics.items() if isinstance(v, float)))
    return metrics


def main():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    pipeline = rc2.get_pipeline(device)

    all_path = OUTPUT_DIR / "pft_ablation_all_results.csv"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    results = pd.read_csv(all_path).to_dict("records") if all_path.exists() else []
    done = {(r["site"], r["condition"]) for r in results}

    for site in SITES:
        df = load_augmented_df(site)
        for condition in CONDITIONS:
            if (site, condition) in done:
                print(f"[skip] {site}/{condition} already done")
                continue
            metrics = run_one(pipeline, site, condition, df)
            results.append(metrics)
            pd.DataFrame(results).to_csv(all_path, index=False)

    print(f"\nSaved {len(results)} rows to {all_path}")


if __name__ == "__main__":
    main()
