# Global ERA5 + Chronos-2 LAI Evaluation

**Status: Part 7 (pipeline validation on one existing CONUS pixel) complete — first real
result obtained 2026-09-14. Full 45-pixel global evaluation not yet started (see "Next
steps").**

**Goal**: evaluate zero-shot Chronos-2's LAI-forecasting generalization outside the United
States, using ERA5 as a common, global meteorological input in place of the existing
project's gridMET (CONUS-only).

## What's done and verified

1. **Existing pipeline inspected** (not redesigned) — confirmed HiQ-LAI (CONUS-only, 8-day,
   ~4.6km), gridMET (7 variables, daily→8-day mean aggregation), and the Chronos-2
   `common_pipeline.build_chronos_inputs()` function, which is fully generic over
   `feature_cols` and needed zero changes to accept ERA5-derived columns instead of gridMET.
2. **ERA5 variable mapping verified empirically** (real CDS downloads, not documentation):
   see `scripts/era5_source.py`'s module docstring for the exact formulas, units, and the
   order of computation for every one of the 7 gridMET-equivalent variables, including the
   two that must be derived (VPD via FAO-56 Penman-Monteith from temperature+dewpoint;
   specific humidity from dewpoint+surface pressure) and the two with non-obvious unit
   conversions found only by checking real downloaded values (solar radiation: J/m² → W/m²
   via ÷3600, verified against gridMET's own value range; precipitation: confirmed the CDS
   tool correctly de-accumulates hourly steps before summing).
3. **Product selected**: `derived-era5-single-levels-daily-statistics` (CDS) — global 0.25°,
   server-side daily aggregation (avoids downloading raw hourly data).
4. **Global, non-U.S. pixel selection completed**: `data_selection/global_candidate_pixels.csv`
   — 45 pixels, farthest-point-sampled in a 10-class PFT fractional-composition space (using
   the ALREADY AVAILABLE global ESA CCI PFT product at `/shared/.../Global_PFTs/`, not
   just the project's existing CONUS-regridded copy), with a minimum 800km geographic
   separation, explicitly excluding CONUS/Alaska/Hawaii. Purity range 0.44–1.00, all 10 PFT
   classes represented, 13 world regions covered (Siberia, Canada, East Asia, Western/
   Eastern Europe, Amazon, Central/Southern Africa, East Africa/Sahel, South/Southeast
   Asia, Australia, Southern S. America, plus some unclassified "Other" points).
5. **Chronos-2 integration built**: `scripts/run_era5_chronos.py` reuses
   `Code/common_pipeline.py` and `Code/run_chronos2.py` UNCHANGED — it only builds a
   dataframe with ERA5-sourced climate columns aligned to each LAI 8-day window (mirroring
   `AELSTM/preprocessing/nc_csv.py`'s exact windowed-mean convention, not a naive calendar
   aggregation), then calls the existing `build_chronos_inputs()`/zero-shot prediction path.

## Part 7 validation result (evergreen pixel, ERA5 vs. gridMET, both zero-shot)

`results/evergreen/{predictions_era5.csv,metrics_era5.txt}`, produced by
`run_era5_chronos.py --lat 30.525 --lon -82.4333 --site evergreen --era5-years 2021 2022 --test-year 2022`:

| Source | Context | RMSE | MAE | MAPE | R² | Pearson r |
|---|---|---|---|---|---|---|
| gridMET (existing, `outputs/zero_shot/evergreen/metrics.txt`) | 2000–2021 (~1,002 steps) | 0.485 | 0.426 | 14.02 | 0.832 | 0.930 |
| **ERA5 (this experiment)** | 2021 only (46 steps) | 0.534 | 0.446 | 14.60 | 0.797 | 0.902 |

**Read this as a diagnostic, not a horse race (Part 22's own framing):** the ERA5 run used a
**much shorter context** (1 year vs. gridMET's 22 years) because only 2021–2022 ERA5 data was
fetched for this validation — the two rows are not an apples-to-apples comparison of the met
source itself. The finding that matters here is that ERA5-forced Chronos-2 produces sane,
physically reasonable predictions in the same ballpark as the established gridMET baseline
(no wildly wrong units, no sign errors, no order-of-magnitude mismatch) despite 22× less
context — a real, positive validation signal that the ERA5 variable mapping, unit
conversions, and temporal alignment (§ below) are correct.

**Three real bugs were found and fixed while producing this first result** (not data issues):
1. `run_era5_chronos.py`'s `CODE_DIR` used `parents[2]` instead of `parents[3]`, resolving to
   a nonexistent `experiments/Code` instead of the project's actual `Code/` directory.
2. The `chronos2` conda environment (required for `run_chronos2`'s `BaseChronosPipeline` —
   confirmed the *base* env's `chronos` package is a different, incompatible package) did not
   have `cdsapi` installed, even though `era5_source.py` imports it unconditionally at
   call-time regardless of whether any network fetch is actually needed. Fixed by installing
   `cdsapi` into the `chronos2` env (lightweight, no dependency conflicts).
3. **A same-process HDF5 library conflict**: importing `run_chronos2` (which pulls in
   `transformers`/`tensorflow`, bundling its own `libhdf5`) before actually *opening* a real
   netCDF4 file corrupts every subsequent `netCDF4`/`xarray` file read in that process
   (`OSError: [Errno -101] NetCDF: HDF error`), even though the cached files themselves are
   completely fine (verified: both the base conda env and an isolated `chronos2`-env
   subprocess open them without issue). Root cause: HDF5 only locks in its correct library
   bindings on the *first real file-open call*, not merely on module import. Fixed in
   `run_era5_chronos.py` by forcing one real netCDF4 open/close (any cached file) immediately
   after `import era5_source`, before `import run_chronos2`.

## Known constraints (found only by running real requests - not documented anywhere)

- **This CDS account allows exactly ONE request in flight at a time.** Submitting several
  concurrently is rejected outright with `403 Forbidden`, not queued.
- **CDS enforces a tight per-request "cost" cap.** Empirically: 1 variable × 1 year succeeds;
  1 variable × 2 years is rejected ("cost limits exceeded"). This means a full pixel-history
  fetch needs roughly **9 variables × N years = 9N strictly sequential requests**.
- **Observed queue latency is highly variable and often large** — individual requests have
  taken anywhere from ~30 seconds to ~19 minutes, seemingly dominated by CDS's own
  system-wide load rather than our request size. This is the dominant cost of this
  experiment and is not something client-side engineering can fix.
- **Practical implication**: a single pixel with a few years of history is a realistic
  background job (tens of minutes to a few hours); the full 45-pixel global evaluation at
  a useful history length is realistically an **unattended, multi-hour-to-multi-day**
  background undertaking at the currently observed queue speed.

## How to resume / extend

```bash
# Fetch (or resume - cached per variable/year/location, safe to re-run) ERA5 for one pixel:
cd scripts
python -u era5_source.py  # see build_gridmet_equivalent(lat, lon, years) for direct use

# Run the existing Chronos-2 zero-shot pipeline with ERA5 covariates for one pixel
# (MUST use the chronos2 conda env -- base env's `chronos` package lacks BaseChronosPipeline):
/home/deh25003/miniconda3/envs/chronos2/bin/python3 run_era5_chronos.py \
    --lat 30.525 --lon -82.4333 --site evergreen --era5-years 2021 2022 --test-year 2022

# Re-run/expand the global pixel selection (independent of ERA5, fast - ~5-10 min):
python select_global_pixels.py
```

`data/era5/cache/` holds every successfully downloaded (variable, statistic, location, year)
NetCDF permanently - re-running any fetch for already-cached data makes no network call and
is instant. **Never run two ERA5-fetching processes at the same time** (violates the
1-concurrent-request limit above).

## Directory structure

```
experiments/global_era5_chronos/
    scripts/
        era5_source.py         # ERA5 download + unit conversion + derivation (the "meteorological source" module)
        select_global_pixels.py # global PFT-diverse, non-U.S. pixel selection
        run_era5_chronos.py     # Chronos-2 zero-shot with ERA5 covariates, reusing the existing pipeline
    data/era5/{raw,cache,processed,aligned}/  # ERA5 downloads (cache/ is the durable, reusable store)
    data_selection/
        global_candidate_pixels.csv  # 45 non-U.S. pixels
    results/    # per-pixel ERA5-based predictions/metrics, once available
    figures/    # (not yet populated)
    logs/       # (not yet populated)
```

## Next steps (not yet done)

- Extend Part 7 validation to 1-2 more existing CONUS pixels (`low_amplitude`,
  `high_amplitude_deciduous`) for a less single-pixel-dependent sanity check.
- Decide on a practical years-of-history budget per pixel (shorter history = fewer sequential
  CDS requests = faster) and launch the 45-pixel global fetch as a long background job.
- Run zero-shot Chronos-2 across the 45 pixels once ERA5 + a global LAI source (MODIS
  MOD15A2H via NASA Earthdata, credentials already confirmed working, or GIMMS LAI4g) are
  both available; build the regional/vegetation-group/U.S.-vs-non-U.S. analysis and figures
  described in the original request.
