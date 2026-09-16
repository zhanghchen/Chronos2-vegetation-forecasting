# Global ERA5 → Chronos-2 Zero-Shot Experiment

*Generated: 2026-09-15*

Zero-shot Chronos-2 LAI forecasting driven by ERA5 climate covariates instead
of gridMET, to test whether the strong zero-shot generalization already
established with gridMET (`reports/CHRONOS2_CONUS70_REPORT.md`, median
R²=0.904 across 70 diverse CONUS pixels) is an artifact of gridMET
specifically or holds with an independent reanalysis product.

**Chronos-2 is used strictly zero-shot throughout this experiment: no
training or fine-tuning, no change to any existing Chronos-2 setting.**

**Result** (full detail in `reports/ERA5_CLOUD_LARGESCALE_REPORT.md`): across
the same 70 pixels and 22-year context as the gridMET study, cloud-ERA5
scores median R²=0.890 (mean 0.716) vs. gridMET's median R²=0.905 (mean
0.766) — comparable central tendency, but a longer negative-R² tail (6/70
vs. 2/70 pixels), concentrated in already-marginal shrub/grassland pixels.
ERA5 beats gridMET on 31/70 pixels and loses on 39/70 — not a uniform
"better" or "worse" result.

## Data pipeline

### 1. Raw ERA5 → 7 gridMET-equivalent variables

Two interchangeable acquisition backends implement the identical contract
`build_gridmet_equivalent(lat, lon, years) -> DataFrame[tmmx, tmmn, pr,
srad, vpd, sph, vs]`:

| | `era5_source.py` (CDS API) | `era5_source_arco.py` (cloud, **primary**) |
|---|---|---|
| Source | Copernicus CDS `derived-era5-single-levels-daily-statistics` | Google ARCO-ERA5 `gs://gcp-public-data-arco-era5/ar/full_37-1h-0p25deg-chunk-1.zarr-v3` |
| Access | Authenticated CDS API, server-side subsetting, 1 request per (variable, year) | Anonymous GCS read, Zarr, client-side aggregation from raw hourly |
| Grid | 0.25°, 721×1440, confirmed identical grid cells for the same lat/lon | 0.25°, 721×1440 |
| Speed | ~1 concurrent request, per-request cost cap → **days** of queue time for one pixel's full history | ~32 simulated-hours/second with a 64-way async concurrency setting and pixel-batched extraction → **~100 minutes for the entire 70-pixel pool's full 2000-2022 history** |
| Status | Kept for reproducibility; no longer the primary path | **Primary acquisition path as of 2026-09-15** |

Both apply **identical** unit conversions and derivations:
- `tmmx`/`tmmn`: `2m_temperature` daily max/min, K (no conversion).
- `pr`: `total_precipitation` daily sum, m → mm (×1000).
- `srad`: `surface_solar_radiation_downwards` daily mean of 24 hourly
  per-hour-increment values, J/m² → W/m² (÷3600).
- `vpd`, `sph`: derived from daily-mean `2m_temperature`,
  `2m_dewpoint_temperature`, `surface_pressure` via the FAO-56
  Penman-Monteith saturation-vapor-pressure formula (see
  `era5_source.py::derive_vpd_sph` for the exact formula).
- `vs`: `sqrt(u10_mean² + v10_mean²)` from daily-mean 10m wind components.

See `reports/ERA5_CLOUD_EQUIVALENCE_REPORT.md` for the empirical validation
of the cloud source against the CDS source (accessed 2026-09-15) before it
was adopted, including a known, diagnosed-but-not-fully-resolved moderate
discrepancy in precipitation (Pearson r=0.95 vs. ≥0.987 for the other 6
variables), and its effect (or lack of one) on the final Chronos-2 metrics.

### 2. LAI alignment

`run_era5_chronos.py::aggregate_era5_to_lai_windows` mirrors AELSTM's
`nc_csv.py::get_climate_mean` exactly: for each LAI 8-day composite starting
at `date`, the climate covariates are the mean of the daily ERA5 values over
`[date, min(date+7 days, year_end)]` — the actual composite window, not a
naive Mon-Sun calendar week.

### 3. Chronos-2 zero-shot protocol

Identical to every other zero-shot run in this project
(`Code/common_pipeline.py::build_chronos_inputs`, reused unmodified):
context = all rows before the test year, forecast = all steps of the test
year, observed test-year climate supplied as `future_covariates`, scored
against raw (unsmoothed) observed LAI. **This large-scale run uses
context = 2000-2021 (~1,000 8-day steps) and test year = 2022**, matching
the gridMET CONUS-70 study's context length exactly (the original ERA5
validation used a much shorter 2020-2021 context; this was an
acknowledged limitation, now fixed for the scaled run).

## Pixel set

The full 70-pixel, 8-vegetation-class, 9-region CONUS pool already selected
and quality-filtered for the `pft_multipixel` studies
(`AELSTM/outputs/pft_multipixel_selection/pft_diverse_pixels.csv`) — the
**same pixels, same LAI data** used by the existing gridMET CONUS-70 study
(`reports/CHRONOS2_CONUS70_REPORT.md`). Reused unchanged: no new pixel
sampling was designed for this experiment, per the explicit instruction to
reuse existing pixel/LAI definitions. Using the full 70 (rather than the
32-pixel purity≥0.75 subset) maximizes the number of pixels with a directly
comparable gridMET result and gives more pixels per vegetation class for
the class-level breakdown.

## Reproducing

```bash
cd experiments/global_era5_chronos/scripts

# 1. One-time cloud prefetch (era5cloud env: gcsfs+zarr+dask, isolated from
#    both `base` and `chronos2` envs to avoid dependency conflicts):
/home/deh25003/miniconda3/envs/era5cloud/bin/python3 prefetch_arco_pool.py

# 2. Zero-shot Chronos-2 on all 70 pixels (chronos2 env: torch+transformers):
/home/deh25003/miniconda3/envs/chronos2/bin/python3 run_era5_chronos_batch.py

# 3. Summary tables, figures, gridMET comparison:
/home/deh25003/miniconda3/envs/era5cloud/bin/python3 build_era5_cloud_comparison.py
```

Single-pixel reproduction (either source):
```bash
/home/deh25003/miniconda3/envs/chronos2/bin/python3 run_era5_chronos.py \
  --lat 30.525 --lon -82.4333 --site evergreen \
  --era5-years 2000 2001 ... 2022 --test-year 2022 --source cloud
```

## Environment notes

- `era5cloud` conda env (Python 3.11, xarray/zarr/gcsfs/dask): used ONLY for
  cloud ERA5 access. Kept isolated from `base` after installing these
  packages directly into `base` was found to bump numpy/fsspec/protobuf/
  opentelemetry-api to versions conflicting with other tools already
  relying on `base` (albumentations, lightning, mlflow, wandb) — reverted,
  and this dedicated env created instead.
- `chronos2` conda env: unchanged, used for anything importing
  `run_chronos2`/`BaseChronosPipeline` (torch/transformers/chronos).
  Already has `xarray` (needed to read the small local ARCO daily-CSV
  cache) but intentionally does NOT have zarr/gcsfs — the cloud-fetch step
  and the Chronos-2 step are fully decoupled: the batch driver only ever
  reads the small pre-populated local cache
  (`data/era5_arco/cache/*.csv`, a handful of KB per pixel-year), never the
  cloud store directly.

## Files

- `scripts/era5_source.py` — original CDS pipeline (kept for reproducibility).
- `scripts/era5_source_arco.py` — cloud ERA5 pipeline (primary).
- `scripts/run_era5_chronos.py` — single-pixel merge + zero-shot run,
  `--source {cds,cloud}`.
- `scripts/run_era5_chronos_batch.py` — 70-pixel batch driver (cloud only).
- `scripts/prefetch_arco_pool.py` — one-time batched cloud fetch for the
  full pixel pool.
- `scripts/build_era5_cloud_comparison.py` — summary tables/figures/gridMET
  comparison.
- `data/era5/cache/` — CDS per-(variable,stat,lat,lon,year) raw netCDF cache.
- `data/era5_arco/cache/` — cloud per-(grid-point,year) daily-aggregated CSV
  cache.
- `results/<site>/metrics_era5[_cloud].txt`,
  `predictions_era5[_cloud].csv` — per-pixel outputs (CDS vs. cloud kept in
  separate files, never overwriting each other).
- `outputs/era5_cloud_70pixels.csv` — full batch result table.
- `outputs/era5_cloud_summary_{overall,by_class,by_region}.csv`,
  `era5_cloud_vs_gridmet_matched.csv` — summary/comparison tables.
- `outputs/era5_cloud_r2_by_pixel_and_class.png`,
  `era5_cloud_vs_gridmet_scatter.png` — figures.
- `reports/ERA5_CLOUD_EQUIVALENCE_REPORT.md` — CDS-vs-cloud validation.
- `reports/ERA5_CLOUD_LARGESCALE_REPORT.md` — full 70-pixel results and
  gridMET comparison.

## History: the original CDS-only, 45-pixel-global plan (superseded)

This experiment originally targeted 45 *non-U.S.* pixels (global PFT-diverse
sampling, `data_selection/global_candidate_pixels.csv`) using only the CDS
API, before the CDS queue-time bottleneck below made that impractical and
the project pivoted to reusing the existing 70-pixel *CONUS* pool with the
cloud source instead. Kept here since it documents real, hard-won findings
that remain true of the CDS path (still available via `--source cds`):

- **This CDS account allows exactly ONE request in flight at a time.**
  Submitting several concurrently is rejected outright with `403 Forbidden`,
  not queued.
- **CDS enforces a tight per-request "cost" cap.** Empirically: 1 variable ×
  1 year succeeds; 1 variable × 2 years is rejected ("cost limits
  exceeded"). A full pixel-history fetch needs roughly **9 variables × N
  years = 9N strictly sequential requests**.
- **Observed queue latency is highly variable and often large** — individual
  requests took anywhere from ~30 seconds to ~19 minutes, seemingly
  dominated by CDS's own system-wide load rather than request size. This
  (not raw bandwidth) was the actual motivation for the cloud-ERA5 switch.
- The first real Chronos-2+ERA5 result (evergreen pixel, CDS, short
  2020-2021 context) uncovered three real bugs while it was produced: a
  `CODE_DIR` path miscalculation (`parents[2]` vs. the correct `parents[3]`),
  a missing `cdsapi` install in the `chronos2` env, and a same-process HDF5
  library conflict between `netCDF4`/`xarray` and `transformers`'s bundled
  `libhdf5` (fixed by forcing a real netCDF4 file-open before importing
  `run_chronos2` — see `run_era5_chronos.py`'s own comments). All three
  fixes are still in place and apply equally to the cloud path.
- `data_selection/global_candidate_pixels.csv` (45 non-U.S. pixels, 10 PFT
  classes, 13 world regions, min. 800km separation) remains a valid,
  ready-to-use pixel set if a genuinely non-CONUS/global generalization
  study is done in the future — it was not used for the 70-pixel CONUS
  results in this README because the user explicitly asked to reuse the
  existing CONUS pixel pool for direct comparability with the gridMET study.
