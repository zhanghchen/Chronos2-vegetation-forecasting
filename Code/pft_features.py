# Time-aligned PFT covariate builder for Chronos-2, mirroring
# AELSTM/Code/pft_features.py (kept as an independent copy, per this
# project's convention of only reusing AELSTM's *data*, never its code).
# PFT fractional cover is annual (ESA CCI, 1992-2020), pre-regridded onto
# the exact HiQ-LAI/gridMET grid (verified byte-identical lat/lon arrays -
# no spatial resampling needed). Each row's YEAR selects that year's PFT
# vector, broadcast constant across all 8-day steps in the year; 2021-2022
# (no PFT file exists) carry the last available year, 2020, forward -
# verified empirically that PFT composition is static (or changes at most
# once) per pixel across 1992-2020, so this is a documented, low-risk
# assumption. Only 3 of 15 ESA CCI classes are ever nonzero across our 4
# sites: TREES_NE, TREES_BD, GRASS_NAT.
from pathlib import Path

import netCDF4 as nc
import numpy as np
import pandas as pd

PFT_DIR = Path("/shared/guw02001/hoq23003/DL4Vegetation/Data/PFTs_regrid_to_gridMET")
LAI_DIR = Path("/shared/guw02001/hoq23003/DL4Vegetation/Data/HiQ_LAI_regrid_to_gridMET")

ALL_PFT_CLASSES = [
    "BARE", "BUILT", "GRASS_MAN", "GRASS_NAT",
    "SHRUBS_BD", "SHRUBS_BE", "SHRUBS_ND", "SHRUBS_NE",
    "SNOWICE", "TREES_BD", "TREES_BE", "TREES_ND", "TREES_NE",
    "WATER_INLAND", "WATER_OCEAN",
]
ACTIVE_CLASSES = ["TREES_NE", "TREES_BD", "GRASS_NAT"]
FRAC_COLS = [f"PFT_{c}" for c in ACTIVE_CLASSES]
DOM_COLS = [f"DOM_{c}" for c in ACTIVE_CLASSES]

PFT_YEAR_MIN, PFT_YEAR_MAX = 1992, 2020

_grid_cache = {}
_year_cache = {}


def _grid_coords():
    if "lat" not in _grid_cache:
        f = sorted(LAI_DIR.rglob("HiQ_LAI_WGS84_5km_8day_*.regrid.nc"))[0]
        with nc.Dataset(f) as ds:
            _grid_cache["lat"] = ds.variables["lat"][:].data.copy()
            _grid_cache["lon"] = ds.variables["lon"][:].data.copy()
    return _grid_cache["lat"], _grid_cache["lon"]


def _load_year(year):
    y = min(max(year, PFT_YEAR_MIN), PFT_YEAR_MAX)
    if y not in _year_cache:
        f = PFT_DIR / f"PFTs_subset_regridded_output.{y}.nc"
        with nc.Dataset(f) as ds:
            # 2010's file is missing WATER_OCEAN (known ~12%-smaller file in
            # this archive); harmless here since none of our sites are
            # coastal, so missing classes are filled with 0.
            shape = ds.variables["lat"].shape + ds.variables["lon"].shape
            _year_cache[y] = {
                c: (ds.variables[c][:] if c in ds.variables else np.zeros(shape))
                for c in ALL_PFT_CLASSES
            }
    return _year_cache[y], y


def site_year_vector(lat, lon, year):
    layers, actual_year = _load_year(year)
    grid_lat, grid_lon = _grid_coords()
    r = int(np.argmin(np.abs(grid_lat - lat)))
    c = int(np.argmin(np.abs(grid_lon - lon)))
    fracs = {cls: float(layers[cls][r, c]) / 100.0 for cls in ACTIVE_CLASSES}
    return fracs, actual_year


def augment_site_dataframe(df, lat, lon):
    """Adds FRAC_COLS (fractional, 0-1) and DOM_COLS (one-hot of the
    per-year argmax) matched by each row's own year."""
    out = df.copy()
    out["date"] = pd.to_datetime(out["date"])
    years = out["date"].dt.year.to_numpy()
    unique_years = sorted(set(years.tolist()))

    frac_by_year = {}
    for y in unique_years:
        fracs, _ = site_year_vector(lat, lon, y)
        frac_by_year[y] = fracs

    for col, cls in zip(FRAC_COLS, ACTIVE_CLASSES):
        out[col] = [frac_by_year[y][cls] for y in years]

    dom_by_year = {y: max(fracs, key=fracs.get) for y, fracs in frac_by_year.items()}
    for col, cls in zip(DOM_COLS, ACTIVE_CLASSES):
        out[col] = [1.0 if dom_by_year[y] == cls else 0.0 for y in years]

    return out
