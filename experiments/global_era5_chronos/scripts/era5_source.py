# ERA5 meteorological-source module for the global Chronos-2 LAI
# experiment. Implements the "meteorological source" interface described
# in the project plan (Part 24): given a location and date range, returns
# the same 7 standardized climate features (tmmx, tmmn, pr, srad, vpd,
# sph, vs) the existing gridMET-based pipeline already uses - so
# downstream Chronos-2 input code needs zero changes to switch sources.
#
# Verified empirically against real CDS API calls before writing this
# (not assumed from documentation):
#   - CDS dataset: derived-era5-single-levels-daily-statistics (ERA5,
#     0.25 deg global grid, confirmed: 721x1440, lat +90->-90,
#     lon 0-360; server-side spatial subsetting via `area` works and
#     keeps downloads tiny).
#   - Multi-variable requests return a ZIP of per-variable NetCDFs, not
#     one file - handled below.
#   - "daily_maximum"/"daily_minimum" on 2m_temperature: confirmed
#     working, returns K.
#   - "daily_sum" on total_precipitation: confirmed the CDS tool
#     correctly de-accumulates hourly steps before summing (checked:
#     result is a plausible 0-16.6 mm/day for a CONUS summer day, not an
#     absurd multi-hundred-mm value) - native unit meters, x1000 -> mm.
#   - "daily_mean" on surface_solar_radiation_downwards: native unit is
#     J/m^2 (mean of the 24 hourly-accumulated values, INCLUDING zero
#     nighttime hours - not a daily total). Dividing by 3600 s/hour
#     converts this to a plausible average W/m^2 (checked: 183-363 W/m^2
#     for a CONUS test box, matching gridMET's own srad range of
#     11-448 W/m^2) - this is the documented conversion used below.
#   - No native ERA5 single-level output for VPD or specific humidity;
#     both are derived from 2m_dewpoint_temperature (+ 2m_temperature for
#     VPD, + surface_pressure for specific humidity) using the FAO-56
#     Penman-Monteith saturation-vapor-pressure formula - see
#     derive_vpd_sph() below for the exact formula and computation order.
#   - Wind speed: derived from the DAILY-MEAN u/v components, then
#     magnitude (sqrt(u^2+v^2)), not the mean of instantaneous
#     magnitudes - a standard, documented simplification (see module
#     docstring caveat).
import json
import time
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

try:
    import cdsapi
except ImportError:
    cdsapi = None

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "era5" / "cache"
RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "era5" / "raw"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
RAW_DIR.mkdir(parents=True, exist_ok=True)

CDS_DATASET = "derived-era5-single-levels-daily-statistics"
# Found empirically, the hard way: 1 variable x 1 year succeeds; 1 variable
# x 2 years is rejected with "cost limits exceeded". The safe, PROVEN
# configuration is 1 year and 1 variable per request - both YEAR_CHUNK and
# variable-batching are disabled below in favor of correctness over
# request-count efficiency, since the alternative (guessing at a size
# threshold) produced repeated failures.
YEAR_CHUNK = 1

# gridMET-equivalent variable -> (ERA5 CDS variable name, daily_statistic)
DIRECT_VARS = {
    "tmmx": ("2m_temperature", "daily_maximum"),
    "tmmn": ("2m_temperature", "daily_minimum"),
    "pr": ("total_precipitation", "daily_sum"),
    "srad": ("surface_solar_radiation_downwards", "daily_mean"),
}
# extra raw variables needed only to DERIVE vpd/sph/vs (not gridMET-named themselves)
DERIVED_INPUT_VARS = {
    "t2m_mean": ("2m_temperature", "daily_mean"),
    "d2m_mean": ("2m_dewpoint_temperature", "daily_mean"),
    "sp_mean": ("surface_pressure", "daily_mean"),
    "u10_mean": ("10m_u_component_of_wind", "daily_mean"),
    "v10_mean": ("10m_v_component_of_wind", "daily_mean"),
}


def _bbox_for_pixel(lat, lon, half_width_deg=0.30):
    """A small bounding box around one pixel - big enough to guarantee at
    least one ERA5 0.25-degree grid node regardless of exact alignment,
    small enough to keep every request tiny (server-side subsetting,
    verified working)."""
    return [lat + half_width_deg, lon - half_width_deg, lat - half_width_deg, lon + half_width_deg]  # N,W,S,E


def _cache_path(var_name, stat, lat, lon, year):
    tag = f"{var_name}_{stat}_{lat:.3f}_{lon:.3f}_{year}"
    return CACHE_DIR / f"{tag}.nc"


def _download_batch(client, var_names, stat, lat, lon, years, max_retries=4):
    """Downloads every variable in `var_names` that shares one `stat`,
    across ALL of `years`, in a SINGLE CDS request - this is the critical
    optimization found necessary during validation: submitting one
    request per YEAR made a full multi-decade pixel take 12+ hours of
    queue time (each request queued independently, 5-10 min each,
    regardless of how much data it carries); the CDS `year` parameter
    accepts a LIST, so requesting e.g. 23 years in one call costs the
    same ~1 queue wait as requesting 1 year. Combined with the
    stat-grouping in fetch_era5_point_daily, one pixel's ENTIRE history
    now costs 4 queue submissions total, not 4 x n_years.
    The multi-year response is split back into per-year cache files
    (by the embedded valid_time coordinate) so per-year incremental
    caching still works exactly as before."""
    missing_years = [y for y in years if not _cache_path(var_names[0], stat, lat, lon, y).exists()
                      or any(not _cache_path(v, stat, lat, lon, y).exists() for v in var_names)]
    if not missing_years:
        return

    bbox = _bbox_for_pixel(lat, lon)
    request = {
        "product_type": "reanalysis",
        "variable": var_names,
        "year": [str(y) for y in missing_years],
        "month": [f"{m:02d}" for m in range(1, 13)],
        "day": [f"{d:02d}" for d in range(1, 32)],
        "daily_statistic": stat,
        "time_zone": "utc+00:00",
        "frequency": "1_hourly",
        "area": bbox,
    }
    tag = f"{stat}_{lat:.3f}_{lon:.3f}_{min(missing_years)}-{max(missing_years)}"
    tmp_path = RAW_DIR / f"_tmp_{tag}.download"
    last_err = None
    for attempt in range(max_retries):
        try:
            result = client.retrieve(CDS_DATASET, request)
            result.download(str(tmp_path))
            break
        except Exception as e:  # noqa - CDS transient errors are common, retry
            last_err = e
            wait = 15 * (attempt + 1)
            print(f"  [retry {attempt+1}/{max_retries}] {tag} failed: {e} - waiting {wait}s")
            time.sleep(wait)
    else:
        raise RuntimeError(f"Failed to download {tag} after {max_retries} attempts: {last_err}")

    extracted_paths = {}
    if zipfile.is_zipfile(tmp_path):
        with zipfile.ZipFile(tmp_path) as zf:
            for name in zf.namelist():
                zf.extract(name, RAW_DIR)
                matched = next((v for v in var_names if name.startswith(v)), None)
                if matched is not None:
                    extracted_paths[matched] = RAW_DIR / name
        tmp_path.unlink()
    else:
        assert len(var_names) == 1
        extracted_paths[var_names[0]] = tmp_path

    # split each multi-year file into per-year cache files
    for var_name, path in extracted_paths.items():
        ds = xr.open_dataset(path)
        years_in_file = pd.to_datetime(ds["valid_time"].values).year
        for y in sorted(set(years_in_file)):
            out_path = _cache_path(var_name, stat, lat, lon, y)
            if out_path.exists():
                continue
            ds.isel(valid_time=(years_in_file == y)).to_netcdf(out_path)
        ds.close()
        if path != tmp_path:
            path.unlink()
        elif path.exists():
            path.unlink()


def _extract_point(nc_path, lat, lon):
    ds = xr.open_dataset(nc_path)
    main_var = [v for v in ds.data_vars if v not in ("number",)][0]
    point = ds[main_var].sel(latitude=lat, longitude=lon % 360, method="nearest")
    dates = pd.to_datetime(ds["valid_time"].values)
    values = point.values
    ds.close()
    return pd.Series(values, index=dates, name=main_var)


def fetch_era5_point_daily(lat, lon, years, cache_only_check=False):
    """Returns a daily dataframe (date index) with columns tmmx, tmmn, pr,
    srad (gridMET-equivalent, already unit-converted) plus the raw inputs
    needed to derive vpd/sph/vs, for one point across the given years.
    Cached per (variable, stat, location, year) - re-running for an
    already-cached year/variable/location is instant and makes no network
    call (Part 4's incremental-download requirement)."""
    if cdsapi is None:
        raise RuntimeError("cdsapi is not installed - run `pip install cdsapi` first")

    all_vars = {**DIRECT_VARS, **DERIVED_INPUT_VARS}
    # group by (stat, era5 var name) so variables sharing a statistic are
    # downloaded together in one CDS request covering ALL years
    by_stat = {}
    for out_name, (var_name, stat) in all_vars.items():
        by_stat.setdefault(stat, set()).add(var_name)

    if not cache_only_check:
        # Two hard limits found empirically (not documented, discovered by
        # running real requests):
        #   1. This CDS account allows only ONE request in flight at a
        #      time - several at once are rejected with "403 Forbidden",
        #      not queued. Requests must be strictly sequential, across
        #      the whole process (the caller must never run two
        #      fetch_era5_point_daily calls concurrently).
        #   2. CDS enforces a per-request "cost limit" - a single request
        #      for up to 5 variables x 8 years x a tiny bbox was rejected
        #      with "cost limits exceeded / request too large"; the same
        #      shape for 1 year succeeded. YEAR_CHUNK below caps how many
        #      years go in one request; kept conservative (2) since the
        #      exact threshold (which depends on how many variables are
        #      in the same stat-group) wasn't fully characterized.
        client = cdsapi.Client()
        year_list = sorted(years)
        for stat, var_names in by_stat.items():
            for var_name in sorted(var_names):  # 1 variable per request - proven safe
                for i in range(0, len(year_list), YEAR_CHUNK):
                    chunk = year_list[i:i + YEAR_CHUNK]
                    _download_batch(client, [var_name], stat, lat, lon, chunk)
    else:
        for out_name, (var_name, stat) in all_vars.items():
            for year in years:
                if not _cache_path(var_name, stat, lat, lon, year).exists():
                    return None

    series = {}
    for out_name, (var_name, stat) in all_vars.items():
        yearly = [_extract_point(_cache_path(var_name, stat, lat, lon, year), lat, lon) for year in years]
        series[out_name] = pd.concat(yearly).sort_index()

    df = pd.DataFrame(series)
    # unit conversions verified above
    df["tmmx"] = df["tmmx"]  # already K, gridMET-native unit - no conversion
    df["tmmn"] = df["tmmn"]
    df["pr"] = df["pr"] * 1000.0          # m -> mm
    df["srad"] = df["srad"] / 3600.0      # J/m^2 (per-hour, mean-of-24) -> W/m^2
    return df


def saturation_vapor_pressure_kpa(temp_k):
    """FAO-56 Penman-Monteith formula (Allen et al. 1998, Eq. 11):
    es = 0.6108 * exp(17.27*T / (T+237.3)), T in degrees Celsius, es in kPa."""
    t_c = temp_k - 273.15
    return 0.6108 * np.exp(17.27 * t_c / (t_c + 237.3))


def derive_vpd_sph(df):
    """Derives VPD (kPa) and specific humidity (kg/kg) from ERA5's mean
    2m temperature, mean 2m dewpoint temperature, and mean surface
    pressure - computed from DAILY-MEAN inputs (a documented
    simplification vs. computing at hourly resolution and then
    averaging, which would avoid Jensen's-inequality bias from VPD's
    nonlinearity in T but requires 24x more data volume - not pursued in
    this first version per the project's "don't overcomplicate the first
    version" guidance).

    Order of computation:
      1. es(T)  = saturation vapor pressure at mean air temperature [kPa]
      2. ea     = saturation vapor pressure at mean DEWPOINT temperature
                  [kPa] = actual vapor pressure (dewpoint is defined as
                  the temperature at which air becomes saturated)
      3. VPD    = es(T) - ea                                   [kPa]
      4. q (specific humidity) = 0.622*ea / (p - 0.378*ea)      [kg/kg]
         (p = surface pressure in kPa; standard humidity-from-vapor-
         pressure formula, e.g. Bolton 1980 / standard met textbooks)
    """
    es = saturation_vapor_pressure_kpa(df["t2m_mean"])
    ea = saturation_vapor_pressure_kpa(df["d2m_mean"])
    vpd = (es - ea).clip(lower=0)
    p_kpa = df["sp_mean"] / 1000.0
    sph = 0.622 * ea / (p_kpa - 0.378 * ea)
    return vpd, sph


def derive_wind_speed(df):
    """vs = sqrt(u^2 + v^2) using the DAILY-MEAN u/v components (not the
    mean of instantaneous magnitudes - a standard simplification when
    only mean components are available; documented, not hidden)."""
    return np.sqrt(df["u10_mean"] ** 2 + df["v10_mean"] ** 2)


def build_gridmet_equivalent(lat, lon, years):
    """Full pipeline: download/cache ERA5, derive vpd/sph/vs, return a
    daily dataframe with exactly the 7 gridMET-equivalent columns."""
    df = fetch_era5_point_daily(lat, lon, years)
    vpd, sph = derive_vpd_sph(df)
    vs = derive_wind_speed(df)
    out = pd.DataFrame({
        "tmmx": df["tmmx"], "tmmn": df["tmmn"], "pr": df["pr"], "srad": df["srad"],
        "vpd": vpd, "sph": sph, "vs": vs,
    })
    return out
