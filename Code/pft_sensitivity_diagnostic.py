# PFT perturbation/sensitivity diagnostic (user-requested item 4): for a
# FIXED real climate + LAI context, sweep only the fractional-PFT covariate
# through 5 synthetic compositions (100/0, 75/25, 50/50, 25/75, 0/100)
# and check whether Chronos-2's zero-shot prediction responds. These
# synthetic mixes are NOT real ecological observations - purely a
# diagnostic probe of whether the model is sensitive to the PFT channel at
# all.
#
# Run on two contrasting pixels per the user's mixed-vs-pure request:
#   - evergreen: 95% TREES_NE / 5% GRASS_NAT (near-pure) -> sweep TREES_NE
#     vs. GRASS_NAT (its own real axis), TREES_BD fixed at 0.
#   - mixed_forest_grass: 50% TREES_BD / 50% GRASS_NAT (genuinely mixed)
#     -> sweep TREES_BD vs. GRASS_NAT, TREES_NE fixed at 0.
#
# Both past_covariates AND future_covariates for the swept PFT columns are
# overridden to the same constant value per composition (this is still the
# "broadcast constant" mechanism, just with a synthetic constant instead of
# the real one) - climate and target are left completely untouched.
import numpy as np
import pandas as pd

# See pft_ablation_experiment.py: pft_features (netCDF4) must open its
# first file before torch/transformers are imported in this conda env.
import pft_features as pf
pf.site_year_vector(30.0, -90.0, 2010)  # warm-up open, before any torch import

import torch

import common_pipeline as cp
import run_chronos2 as rc2

OUTPUT_DIR = cp.OUTPUTS_ROOT / "pft_ablation" / "sensitivity_diagnostic"

COMPOSITIONS = [
    ("100_forest", 1.00),
    ("75_forest_25_grass", 0.75),
    ("50_forest_50_grass", 0.50),
    ("25_forest_75_grass", 0.25),
    ("100_grass", 0.00),
]

SWEEP_AXIS = {
    "evergreen": "TREES_NE",             # its own real dominant tree class
    "mixed_forest_grass": "TREES_BD",    # its own real dominant tree class
}


def build_perturbed_input(df, forest_col, forest_frac):
    feature_cols = cp.FEATURE_COLS + pf.FRAC_COLS
    input_dict, prediction_length, future_dates, ground_truth = cp.build_chronos_inputs(
        df, feature_cols=feature_cols
    )

    forest_pft_col = f"PFT_{forest_col}"
    grass_pft_col = "PFT_GRASS_NAT"
    other_tree = [c for c in pf.ACTIVE_CLASSES if c not in (forest_col, "GRASS_NAT")][0]
    other_pft_col = f"PFT_{other_tree}"

    n_past = len(input_dict["target"])
    n_future = prediction_length
    input_dict["past_covariates"][forest_pft_col] = np.full(n_past, forest_frac, dtype="float32")
    input_dict["past_covariates"][grass_pft_col] = np.full(n_past, 1.0 - forest_frac, dtype="float32")
    input_dict["past_covariates"][other_pft_col] = np.zeros(n_past, dtype="float32")
    input_dict["future_covariates"][forest_pft_col] = np.full(n_future, forest_frac, dtype="float32")
    input_dict["future_covariates"][grass_pft_col] = np.full(n_future, 1.0 - forest_frac, dtype="float32")
    input_dict["future_covariates"][other_pft_col] = np.zeros(n_future, dtype="float32")

    return input_dict, prediction_length, future_dates, ground_truth


def run_site(pipeline, site):
    raw_df = cp.load_site_df(site)
    lat, lon = raw_df["lat"].iloc[0], raw_df["lon"].iloc[0]
    df = pf.augment_site_dataframe(raw_df, lat, lon)
    forest_col = SWEEP_AXIS[site]

    rows = []
    pred_by_comp = {}
    for label, frac in COMPOSITIONS:
        input_dict, prediction_length, future_dates, ground_truth = build_perturbed_input(df, forest_col, frac)
        pred = rc2.predict_with_pipeline(pipeline, input_dict, prediction_length)
        pred_by_comp[label] = pred
        metrics = cp.compute_metrics(ground_truth, pred)
        rows.append({"site": site, "composition": label, f"frac_{forest_col}": frac,
                     "frac_GRASS_NAT": 1.0 - frac, **metrics})
        print(f"[sensitivity/{site}/{label}] R2={metrics['R2']:.4f} RMSE={metrics['RMSE']:.4f}")

    out_dir = OUTPUT_DIR / site
    out_dir.mkdir(parents=True, exist_ok=True)

    preds_df = pd.DataFrame({"date": future_dates, "ground_truth": ground_truth})
    for label, _ in COMPOSITIONS:
        preds_df[label] = pred_by_comp[label]
    preds_df.to_csv(out_dir / "predictions_by_composition.csv", index=False)

    summary = pd.DataFrame(rows)
    summary.to_csv(out_dir / "sensitivity_summary.csv", index=False)

    # Quantify whether predictions actually changed across compositions.
    stacked = np.stack([pred_by_comp[label] for label, _ in COMPOSITIONS])
    max_abs_diff = float(np.max(np.abs(stacked - stacked[0])))
    max_pct_of_lai_range = max_abs_diff / max(float(np.ptp(ground_truth)), 1e-6) * 100
    with open(out_dir / "sensitivity_verdict.txt", "w") as f:
        f.write(f"site: {site}\n")
        f.write(f"swept_axis: {forest_col} vs GRASS_NAT (other tree class fixed at 0)\n")
        f.write(f"max_abs_prediction_diff_across_5_compositions: {max_abs_diff:.8f}\n")
        f.write(f"as_pct_of_observed_LAI_range: {max_pct_of_lai_range:.4f}%\n")
        f.write(f"verdict: {'NO SENSITIVITY (predictions identical/near-identical)' if max_abs_diff < 1e-4 else 'PREDICTIONS CHANGED'}\n")
    print(f"[{site}] max abs prediction diff across all 5 PFT compositions: {max_abs_diff:.8f} "
          f"({max_pct_of_lai_range:.4f}% of observed LAI range)")
    return summary


def main():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    pipeline = rc2.get_pipeline(device)

    all_summaries = []
    for site in SWEEP_AXIS:
        all_summaries.append(run_site(pipeline, site))

    combined = pd.concat(all_summaries, ignore_index=True)
    combined.to_csv(OUTPUT_DIR / "sensitivity_all_sites.csv", index=False)
    print(f"\nSaved sensitivity diagnostic to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
