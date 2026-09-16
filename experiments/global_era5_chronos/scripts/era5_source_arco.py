# Cloud-hosted ERA5 meteorological source: Google ARCO-ERA5 (Analysis-Ready,
# Cloud-Optimized ERA5), replacing the CDS-API source (era5_source.py) as the
# primary data-acquisition path. Implements the SAME public interface
# (`build_gridmet_equivalent(lat, lon, years) -> 7-column daily dataframe`)
# so run_era5_chronos.py can select either source with zero changes to
# downstream LAI-alignment / Chronos-2 code.
#
# Dataset: gs://gcp-public-data-arco-era5/ar/full_37-1h-0p25deg-chunk-1.zarr-v3
#   - Public, unauthenticated (anonymous) Google Cloud Storage bucket, Zarr
#     format, opened directly with xarray+gcsfs (no download of global
#     fields - only the requested point's time series is streamed).
#   - True ERA5 reanalysis (NOT ERA5-Land): confirmed 0.25 deg grid,
#     721 (lat, +90..-90) x 1440 (lon, 0..359.75) - IDENTICAL grid to the
#     CDS `derived-era5-single-levels-daily-statistics` dataset used
#     previously.
#   - Hourly, 1900-01-01 through (at access time) 2026-05-31 - fully covers
#     the 2000-2022 range needed. Accessed 2026-09-15.
#   - All 7 raw variables needed for the 9->7 mapping are present under
#     their standard ERA5 long names (see RAW_VARS below).
#
# Empirically verified (2026-09-15, evergreen pixel 30.525N/-82.433W, this
# session) against the existing CDS-cached data before being trusted:
#   - Nearest-neighbor grid point selection lands on the IDENTICAL grid
#     cell (30.5, -82.5) as the CDS pipeline's own nearest-neighbor pick.
#   - 2m_temperature daily max: ARCO-derived 300.77682 K vs CDS-cached
#     300.77716 K for 2021-01-01 - float32 rounding only.
#   - surface_solar_radiation_downwards: ARCO's raw hourly values are
#     ALREADY per-hour increments (confirmed: rise/fall with the diurnal
#     cycle, not a monotonically-growing within-day accumulator) - so
#     daily_mean = mean(24 hourly J/m^2 values)/3600 reproduces CDS's own
#     "daily_mean" statistic (see full equivalence report for the full
#     2021-2022 comparison and any residual discrepancies, e.g. in
#     convective total_precipitation on individual days).
#   - See reports/ERA5_CLOUD_EQUIVALENCE_REPORT.md for the full
#     evergreen 2021-2022 comparison (all 7 final variables + Chronos-2
#     re-run) before this source was adopted as the primary path.
#
# Requires xarray, zarr, gcsfs, dask - installed ONLY in the isolated
# `era5cloud` conda env (NOT the shared base env, to avoid the numpy/
# protobuf/fsspec version conflicts discovered when these were briefly
# installed into base). Run this module with:
#   /home/deh25003/miniconda3/envs/era5cloud/bin/python3
import time
from pathlib import Path

import numpy as np
import pandas as pd

try:
    import zarr
    zarr.config.set({"async.concurrency": 64})  # default of 10 measured ~7x slower
    import xarray as xr
except ImportError:
    xr = None  # only needed when actually hitting the cloud store (cache miss)

ARCO_URL = "gs://gcp-public-data-arco-era5/ar/full_37-1h-0p25deg-chunk-1.zarr-v3"

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "era5_arco" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ERA5 raw variable name -> short column name used internally below
RAW_VARS = {
    "2m_temperature": "t2m",
    "2m_dewpoint_temperature": "d2m",
    "surface_pressure": "sp",
    "total_precipitation": "tp",
    "surface_solar_radiation_downwards": "ssrd",
    "10m_u_component_of_wind": "u10",
    "10m_v_component_of_wind": "v10",
}

_ds = None  # lazily-opened, process-wide handle to the Zarr store


def _get_store():
    global _ds
    if _ds is None:
        _ds = xr.open_zarr(ARCO_URL, storage_options={"token": "anon"}, chunks=None, consolidated=True)
    return _ds


def _grid_point(lat, lon):
    """Nearest 0.25-degree ARCO grid node - matches the store's own
    `method="nearest"` selection, verified identical to the CDS pipeline's
    nearest-neighbor pick for the evergreen pixel."""
    lat_grid = round(lat * 4) / 4
    lon_grid = round((lon % 360) * 4) / 4
    return lat_grid, lon_grid


def _cache_path(lat, lon, year):
    tag = f"arco_daily_{lat:.3f}_{lon:.3f}_{year}"
    return CACHE_DIR / f"{tag}.csv"


def _fetch_and_aggregate_year(lat_grid, lon_grid, year, max_retries=4):
    """Pulls one full year of hourly data for one grid point directly from
    the cloud store and aggregates to the 9 raw daily columns (identical
    aggregation rules to era5_source.py's CDS daily-statistics equivalents:
    max/min/mean for instantaneous variables, sum for precipitation,
    mean for solar radiation - see module docstring for the empirical
    justification)."""
    ds = _get_store()
    last_err = None
    for attempt in range(max_retries):
        try:
            sub = ds[list(RAW_VARS.keys())].sel(latitude=lat_grid, longitude=lon_grid, method="nearest").sel(
                time=slice(f"{year}-01-01T00:00", f"{year}-12-31T23:00")
            ).load()
            break
        except Exception as e:  # noqa - transient GCS read errors, retry
            last_err = e
            wait = 10 * (attempt + 1)
            print(f"  [retry {attempt+1}/{max_retries}] ARCO fetch {lat_grid},{lon_grid},{year} failed: {e} - waiting {wait}s")
            time.sleep(wait)
    else:
        raise RuntimeError(f"Failed to fetch ARCO data for {lat_grid},{lon_grid},{year}: {last_err}")

    hourly = sub.to_dataframe()[list(RAW_VARS.keys())].rename(columns=RAW_VARS)
    hourly.index = pd.to_datetime(hourly.index)
    hourly["day"] = hourly.index.date

    daily = hourly.groupby("day").agg(
        tmmx=("t2m", "max"), tmmn=("t2m", "min"), t2m_mean=("t2m", "mean"),
        d2m_mean=("d2m", "mean"), sp_mean=("sp", "mean"),
        pr=("tp", "sum"), srad=("ssrd", "mean"),
        u10_mean=("u10", "mean"), v10_mean=("v10", "mean"),
    )
    daily.index = pd.to_datetime(daily.index)
    daily["pr"] = daily["pr"] * 1000.0        # m -> mm (identical conversion to era5_source.py)
    daily["srad"] = daily["srad"] / 3600.0    # J/m^2 (per-hour mean) -> W/m^2
    return daily


def _fetch_and_aggregate_year_batch(pixel_names, lat_grids, lon_grids, year, max_retries=4):
    """Vectorized multi-pixel version of _fetch_and_aggregate_year: reads
    ALL pixels' hourly series for one year in a SINGLE Zarr read pass,
    using xarray's pointwise ("vectorized") indexing (passing DataArrays
    sharing one `pixel` dimension). This is the scaling-critical
    optimization - the underlying store is chunked by time (each chunk
    spans many hours x the WHOLE global grid), so a chunk already
    contains every pixel's data once it's fetched; looping single-pixel
    fetches would re-download the same time-chunks once per pixel (N x
    the necessary network I/O for N pixels), while this reads each
    chunk once and extracts all N pixels' points from it in memory.
    Returns {pixel_name: daily_dataframe}."""
    ds = _get_store()
    lat_da = xr.DataArray(lat_grids, dims="pixel", coords={"pixel": pixel_names})
    lon_da = xr.DataArray(lon_grids, dims="pixel", coords={"pixel": pixel_names})
    last_err = None
    for attempt in range(max_retries):
        try:
            sub = ds[list(RAW_VARS.keys())].sel(latitude=lat_da, longitude=lon_da, method="nearest").sel(
                time=slice(f"{year}-01-01T00:00", f"{year}-12-31T23:00")
            ).load()
            break
        except Exception as e:  # noqa - transient GCS read errors, retry
            last_err = e
            wait = 10 * (attempt + 1)
            print(f"  [retry {attempt+1}/{max_retries}] ARCO batch fetch {year} failed: {e} - waiting {wait}s")
            time.sleep(wait)
    else:
        raise RuntimeError(f"Failed to fetch ARCO batch data for {year}: {last_err}")

    out = {}
    for name in pixel_names:
        hourly = sub.sel(pixel=name).to_dataframe()[list(RAW_VARS.keys())].rename(columns=RAW_VARS)
        hourly.index = pd.to_datetime(hourly.index)
        hourly["day"] = hourly.index.date
        daily = hourly.groupby("day").agg(
            tmmx=("t2m", "max"), tmmn=("t2m", "min"), t2m_mean=("t2m", "mean"),
            d2m_mean=("d2m", "mean"), sp_mean=("sp", "mean"),
            pr=("tp", "sum"), srad=("ssrd", "mean"),
            u10_mean=("u10", "mean"), v10_mean=("v10", "mean"),
        )
        daily.index = pd.to_datetime(daily.index)
        daily["pr"] = daily["pr"] * 1000.0
        daily["srad"] = daily["srad"] / 3600.0
        out[name] = daily
    return out


def fetch_many_pixels_arco_daily(pixels, years):
    """pixels: dict {name: (lat, lon)}. Fetches/caches the 9-column raw
    daily dataframe for every pixel across `years`, using the batched
    multi-pixel read above for any (year) not already fully cached for
    every pixel - so a partially-cached pool only re-fetches the missing
    years, and every pixel within a fetched year is cached individually
    (identical cache file layout/format to the single-pixel path, so
    build_gridmet_equivalent() transparently reuses whatever this
    prefetch already populated). Returns {name: 9-column daily df}."""
    grid = {name: _grid_point(lat, lon) for name, (lat, lon) in pixels.items()}
    result = {name: [] for name in pixels}
    for year in sorted(years):
        names = list(pixels.keys())
        missing = [n for n in names if not _cache_path(*grid[n], year).exists()]
        if missing:
            t0 = time.time()
            print(f"  fetching {year}: {len(missing)}/{len(names)} pixels missing from cache...", flush=True)
            lat_grids = [grid[n][0] for n in missing]
            lon_grids = [grid[n][1] for n in missing]
            fetched = _fetch_and_aggregate_year_batch(missing, lat_grids, lon_grids, year)
            for n in missing:
                fetched[n].to_csv(_cache_path(*grid[n], year))
            print(f"  {year} done in {time.time()-t0:.0f}s", flush=True)
        for n in names:
            result[n].append(pd.read_csv(_cache_path(*grid[n], year), index_col=0, parse_dates=True))
    return {n: pd.concat(frames).sort_index() for n, frames in result.items()}


def fetch_era5_arco_point_daily(lat, lon, years):
    """Returns the 9-column raw/derived-input daily dataframe (same
    columns as era5_source.fetch_era5_point_daily's DataFrame) for one
    point, across `years`. Caches per (grid point, year) as a small CSV -
    repeated calls make no cloud request for already-cached years (the
    "cache extracted subsets locally" requirement)."""
    lat_grid, lon_grid = _grid_point(lat, lon)
    frames = []
    for year in sorted(years):
        cpath = _cache_path(lat_grid, lon_grid, year)
        if cpath.exists():
            frames.append(pd.read_csv(cpath, index_col=0, parse_dates=True))
            continue
        daily = _fetch_and_aggregate_year(lat_grid, lon_grid, year)
        daily.to_csv(cpath)
        frames.append(daily)
    return pd.concat(frames).sort_index()


def saturation_vapor_pressure_kpa(temp_k):
    """FAO-56 Penman-Monteith formula - identical to era5_source.py."""
    t_c = temp_k - 273.15
    return 0.6108 * np.exp(17.27 * t_c / (t_c + 237.3))


def derive_vpd_sph(df):
    """Identical formula/derivation order to era5_source.derive_vpd_sph."""
    es = saturation_vapor_pressure_kpa(df["t2m_mean"])
    ea = saturation_vapor_pressure_kpa(df["d2m_mean"])
    vpd = (es - ea).clip(lower=0)
    p_kpa = df["sp_mean"] / 1000.0
    sph = 0.622 * ea / (p_kpa - 0.378 * ea)
    return vpd, sph


def derive_wind_speed(df):
    """Identical to era5_source.derive_wind_speed."""
    return np.sqrt(df["u10_mean"] ** 2 + df["v10_mean"] ** 2)


def build_gridmet_equivalent(lat, lon, years):
    """Drop-in replacement for era5_source.build_gridmet_equivalent: same
    signature, same 7-column output contract (tmmx, tmmn, pr, srad, vpd,
    sph, vs), sourced from the ARCO-ERA5 cloud Zarr store instead of CDS."""
    df = fetch_era5_arco_point_daily(lat, lon, years)
    vpd, sph = derive_vpd_sph(df)
    vs = derive_wind_speed(df)
    out = pd.DataFrame({
        "tmmx": df["tmmx"], "tmmn": df["tmmn"], "pr": df["pr"], "srad": df["srad"],
        "vpd": vpd, "sph": sph, "vs": vs,
    })
    return out
