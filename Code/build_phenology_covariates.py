# Builds the covariates Prof. Wang's logistic-growth-mortality equation
# needs - dV/dt = r(T,PAR).V.(1-V/K(P,SM,VPD)) - m(SPEI,T_freeze).V - for
# the 70 CONUS sites, from what's actually available (see
# Code/extract_conus_pet.py's module docstring for the full data-
# availability investigation: GPP/PAR/SM/SPEI are ALL absent from every
# existing dataset in this project; T/P/VPD are already present).
#
# Approximations, each disclosed rather than silently assumed exact:
#   - PAR = 0.45 * srad - the standard ecology/remote-sensing approximation
#     (photosynthetically active radiation is conventionally ~45-50% of
#     total shortwave), not a direct PAR measurement (no PAR product is
#     fetched anywhere in this project).
#   - T_freeze = max(0, 273.15 - tmmn) - a simple "degrees below freezing"
#     indicator from the daily min temperature already in hand, not a
#     frost-day COUNT or a more sophisticated phenology chilling model.
#   - SM and SPEI PROXIES (true soil moisture needs TerraClimate, a
#     monthly product with a different temporal-alignment story than this
#     project's 8-day composites - confirmed absent by direct
#     investigation, not assumed; true SPEI needs a log-logistic
#     distribution fit, no such library is installed here) - both derived
#     instead from the water balance WB = pr - pet (pet newly extracted,
#     see extract_conus_pet.py; pr already in hand), a standard simplified
#     "bucket model" substitute when dedicated SM/drought products aren't
#     available:
#       - SM_proxy: trailing 3-period (~24-day) mean water balance -
#         short-timescale moisture status.
#       - SPEI_proxy: trailing 11-period (~88-day, close to the standard
#         SPEI-3's 3-month window) mean water balance, z-scored using
#         EACH SITE'S OWN full-history mean/std at that window length -
#         the "standardized" part of SPEI's name, without the log-
#         logistic fit real SPEI uses.
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SITES_DIR = ROOT / "data/processed/sites"
PET_DIR = ROOT / "data/conus_pet"
OUT_DIR = ROOT / "data/processed/sites_phenology"
OUT_DIR.mkdir(parents=True, exist_ok=True)

SM_WINDOW = 3    # ~24 days
SPEI_WINDOW = 11  # ~88 days, approximates SPEI-3 (3 calendar months)


def main():
    sites = sorted(p.stem for p in SITES_DIR.glob("*.csv"))
    for i, site in enumerate(sites):
        pet_path = PET_DIR / f"{site}.csv"
        if not pet_path.exists():
            print(f"[{site}] SKIPPED - no PET extracted yet")
            continue
        df = pd.read_csv(SITES_DIR / f"{site}.csv", parse_dates=["date"])
        pet_df = pd.read_csv(pet_path, parse_dates=["date"])
        df = df.merge(pet_df, on="date", how="left")

        df["PAR"] = 0.45 * df["srad"]
        df["T_freeze"] = (273.15 - df["tmmn"]).clip(lower=0)
        df["water_balance"] = df["pr"] - df["pet"]
        df["SM_proxy"] = df["water_balance"].rolling(SM_WINDOW, min_periods=1).mean()
        spei_raw = df["water_balance"].rolling(SPEI_WINDOW, min_periods=max(3, SPEI_WINDOW // 2)).mean()
        df["SPEI_proxy"] = (spei_raw - spei_raw.mean()) / (spei_raw.std() + 1e-8)

        out_path = OUT_DIR / f"{site}.csv"
        df.to_csv(out_path, index=False)
        if i < 3 or i == len(sites) - 1:
            print(f"[{i+1}/{len(sites)}] {site}: {len(df)} rows, "
                  f"PAR range=[{df['PAR'].min():.1f},{df['PAR'].max():.1f}] "
                  f"SM_proxy range=[{df['SM_proxy'].min():.2f},{df['SM_proxy'].max():.2f}] "
                  f"SPEI_proxy range=[{df['SPEI_proxy'].min():.2f},{df['SPEI_proxy'].max():.2f}]")

    print(f"\nDone -> {OUT_DIR}")


if __name__ == "__main__":
    main()
