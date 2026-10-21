# Extracts gridMET PET (potential_evapotranspiration, reference grass) at
# the 70 existing CONUS LOYO-CV site coordinates, matching
# data/processed/sites/<site>.csv's existing 8-day composite dates exactly
# (reuses AELSTM/preprocessing/nc_csv.py's extract_pixel_timeseries windowing
# convention - nearest-neighbor pixel, mean over each 8-day composite window
# - but implemented fresh here rather than importing/modifying AELSTM's code,
# since this is a different variable/output target).
#
# PDSI (the professor's literal "SPEI" request) turned out not to be served
# by gridMET's public file distribution at all (pdsi_<year>.nc returns 404 -
# confirmed directly, not assumed; the AELSTM project's own
# "metdata_wget.PDSI_BI.sh" script apparently only ever succeeded for BI,
# its companion variable, which is why only bi_*.nc exists locally despite
# the script's name). PET genuinely exists (verified: pet_2000.nc..pet_2024.nc
# present, variable key "potential_evapotranspiration") and is the standard
# input needed to compute SPEI from scratch (water balance = P - PET), so
# this is extracted instead - see build_phenology_covariates.py for the
# water-balance-based SM/SPEI-proxy computation built from this output.
#
# READ-ONLY from the shared AELSTM data directory - writes nothing there.
import re
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

CLIMATE_DIR = Path("/shared/guw02001/hoq23003/DL4Vegetation/Data/gridMET")
LAI_DIR = Path("/shared/guw02001/hoq23003/DL4Vegetation/Data/HiQ_LAI_regrid_to_gridMET")
ROOT = Path(__file__).resolve().parent.parent
SITES_DIR = ROOT / "data/processed/sites"
OUT_DIR = ROOT / "data/conus_pet"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def extract_pet_for_site(lat, lon, dates):
    """dates: the site's own existing composite start-dates (from its CSV),
    so the output aligns row-for-row with the already-published data - no
    new date grid invented."""
    pet_ds_cache = {}

    def get_pet_mean(start_date):
        year = start_date.year
        if year not in pet_ds_cache:
            pet_ds_cache[year] = xr.open_dataset(CLIMATE_DIR / f"pet_{year}.nc", engine="netcdf4")
        ds = pet_ds_cache[year]
        year_end = pd.Timestamp(year=year, month=12, day=31)
        end_date = min(start_date + pd.Timedelta(days=7), year_end)
        window = ds["potential_evapotranspiration"].sel(lat=lat, lon=lon, method="nearest").sel(
            day=slice(start_date, end_date))
        return float(window.mean(dim="day").values)

    pet_values = [get_pet_mean(pd.Timestamp(d)) for d in dates]
    for ds in pet_ds_cache.values():
        ds.close()
    return pet_values


def main():
    sites = sorted(p.stem for p in SITES_DIR.glob("*.csv"))
    for i, site in enumerate(sites):
        out_path = OUT_DIR / f"{site}.csv"
        if out_path.exists():
            continue
        df = pd.read_csv(SITES_DIR / f"{site}.csv", parse_dates=["date"])
        lat, lon = df["lat"].iloc[0], df["lon"].iloc[0]
        pet = extract_pet_for_site(lat, lon, df["date"].to_numpy())
        out = pd.DataFrame({"date": df["date"], "pet": pet})
        out.to_csv(out_path, index=False)
        print(f"[{i+1}/{len(sites)}] {site}: {len(out)} rows")

    print(f"\nDone -> {OUT_DIR}")


if __name__ == "__main__":
    main()
