# Climatology-only and persistence baselines for the 3 core paper sites,
# requested as a reviewer check: "does Chronos-2's R^2 reflect genuine skill
# beyond the seasonal cycle, or mostly seasonal-shape matching?" Reuses the
# SAME no-leakage climatology machinery already used for this project's ACC
# metric (loyo_cv_chronos2.circular_doy_climatology, fit on each fold's
# training years ONLY - identical protocol, just scored directly as a
# standalone forecast instead of as an anomaly-correlation diagnostic).
# No model calls - pure data computation.
#
# Persistence = prior year's value at the nearest matching day-of-year
# (not leakage: only year Y-1, never the test year itself).
#
# Covers all 33 LOYO-CV hindcast folds (3 sites x 11 years, 2012-2022), not
# just the single 2022 holdout, since the single-year comparison alone
# understates how it varies across years (see README.md in this output dir).
import glob
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import r2_score

import common_pipeline as cp
import loyo_cv_chronos2 as loyo

OUT_DIR = cp.OUTPUTS_ROOT / "climatology_persistence_baseline"
OUT_DIR.mkdir(parents=True, exist_ok=True)

SITES = ["low_amplitude", "high_amplitude_deciduous", "evergreen"]


def main():
    rows = []
    for site in SITES:
        df = cp.load_site_df(site)
        years = df["date"].dt.year
        for test_year in loyo.FOLD_TEST_YEARS:
            window_start = test_year - loyo.WINDOW_YEARS
            context_df = df[(years >= window_start) & (years < test_year)]
            future_df = df[years == test_year]
            if len(future_df) < 4:
                continue
            clim = loyo.circular_doy_climatology(context_df, future_df["date"].to_numpy(), target_col=cp.TARGET_COL)
            true = future_df[cp.TARGET_COL].to_numpy()

            r2_clim = r2_score(true, clim)
            rmse_clim = float(np.sqrt(np.mean((true - clim) ** 2)))
            pear_clim = float(np.corrcoef(true, clim)[0, 1]) if np.std(clim) > 0 else np.nan

            prior_df = df[years == test_year - 1][["date", cp.TARGET_COL]].copy()
            if len(prior_df) == 0:
                r2_pers = rmse_pers = np.nan
            else:
                prior_df["doy"] = prior_df["date"].dt.dayofyear
                future_doy = pd.DatetimeIndex(future_df["date"]).dayofyear
                pers = np.array([
                    prior_df.loc[(prior_df["doy"] - d).abs().idxmin(), cp.TARGET_COL]
                    for d in future_doy
                ])
                r2_pers = r2_score(true, pers)
                rmse_pers = float(np.sqrt(np.mean((true - pers) ** 2)))

            rows.append(dict(site=site, test_year=test_year, n_test=len(true),
                              R2_climatology=r2_clim, RMSE_climatology=rmse_clim, Pearson_r_climatology=pear_clim,
                              R2_persistence=r2_pers, RMSE_persistence=rmse_pers))

    base = pd.DataFrame(rows)

    cz_rows = []
    for site in SITES:
        for f in sorted(glob.glob(str(cp.OUTPUTS_ROOT / f"loyo_cv/{site}/fold_*_metrics.csv"))):
            d = pd.read_csv(f)
            d = d[d["mode"] == "zero_shot"]
            if len(d):
                cz_rows.append(d[["site", "test_year", "R2", "RMSE", "ACC"]].iloc[0])
    cz = pd.DataFrame(cz_rows)
    cz.columns = ["site", "test_year", "R2_chronos2_zeroshot", "RMSE_chronos2_zeroshot", "ACC_chronos2_zeroshot"]

    merged = base.merge(cz, on=["site", "test_year"], how="left")
    merged["climatology_wins_R2"] = merged["R2_climatology"] >= merged["R2_chronos2_zeroshot"]
    merged.to_csv(OUT_DIR / "all_folds_baseline_comparison.csv", index=False)

    print(f"climatology wins {merged['climatology_wins_R2'].sum()}/{len(merged)} folds on R2")
    print("\nPer-site mean R2 (climatology vs. zero-shot Chronos-2):")
    print(merged.groupby("site")[["R2_climatology", "R2_chronos2_zeroshot"]].mean())
    print(f"\nOverall mean R2:   climatology={merged['R2_climatology'].mean():.3f}  "
          f"chronos2={merged['R2_chronos2_zeroshot'].mean():.3f}")
    print(f"Overall median R2: climatology={merged['R2_climatology'].median():.3f}  "
          f"chronos2={merged['R2_chronos2_zeroshot'].median():.3f}")
    print(f"\nSaved {OUT_DIR / 'all_folds_baseline_comparison.csv'}")


if __name__ == "__main__":
    main()
