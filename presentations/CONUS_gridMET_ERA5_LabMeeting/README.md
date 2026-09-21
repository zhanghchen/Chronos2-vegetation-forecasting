# Zero-Shot Chronos-2: CONUS gridMET + Global ERA5/MODIS Lab Meeting Deck

*Generated: 2026-09-16 · Updated: 2026-09-20 (Part 2 replaced: CONUS
cloud-ERA5 → global non-CONUS ERA5+MODIS experiment)*

12-slide deck integrating two large-scale Chronos-2 zero-shot experiments:

- **Part 1** (unchanged since the original version): the 32-pixel
  purity-filtered gridMET CONUS expansion.
- **Part 2** (new, replaces the original CONUS cloud-ERA5 Part 2): a
  genuinely global, non-CONUS experiment — 70 pixels across 14 world
  regions, cloud ERA5 climate + MODIS MOD15A2H LAI (via NASA AppEEARS)
  instead of gridMET/HiQ-LAI (both CONUS-only).

No new Chronos-2 experiments were run to build the *slides themselves* —
every number is read directly from already-saved result files at build
time. The underlying global experiment (pixel selection, LAI/climate
fetch, zero-shot runs) *was* newly run for this update; see
`experiments/global_era5_chronos/reports/ERA5_GLOBAL70_REPORT.md` for its
own full writeup.

## Files

- `CONUS_gridMET_ERA5_LabMeeting.pptx` — the deck (12 slides).
- `build_deck.py` — editable slide source. Re-run with
  `/home/deh25003/miniconda3/bin/python3 build_deck.py` to regenerate the
  .pptx after editing.
- `make_figures.py` — Part 1's figures (unchanged).
- `make_global_figures.py` — the new CONUS-vs-global comparison figure
  (`conus_vs_global_r2_boxplot.png`).
- `experiments/global_era5_chronos/scripts/build_global70_comparison.py` —
  Part 2's summary tables/map/figures (lives with the experiment, not here).
- `experiments/global_era5_chronos/scripts/plot_cds_vs_cloud_diff.py` — the
  CDS-vs-cloud ERA5 time-series comparison figure (both the full 7-variable
  version and the 3-variable slide version), built per explicit request to
  visualize the actual data rather than only a correlation coefficient.
- `figures/` — every figure embedded in the current deck:
  - **Part 1** (unchanged): `map_32pixel_conus.png`, `exp1_r2_by_pixel_and_class.png`.
  - **Part 2** (new): `global70_map.png` (world map, all 70 pixels, colored
    by vegetation class, CONUS explicitly excluded), `global70_r2_by_pixel_and_class.png`,
    `global70_context_vs_r2.png` (per-pixel context length vs. R², supplementary).
  - **Shared**: `cds_vs_cloud_era5_timeseries_slide.png` (3-variable version,
    embedded in the deck) and `cds_vs_cloud_era5_timeseries.png` (full
    7-variable version, supplementary reference only).
  - **Integration**: `conus_vs_global_r2_boxplot.png` (Part 1 vs. Part 2
    R² distributions, side by side — the disjoint pixel sets mean this is a
    distributional comparison, not a matched-pixel scatter).

## Data sources for every number on the deck

- Part 1 (32-pixel gridMET): `outputs/purity32_pixel_study/
  {zero_shot_32pixels,summary_overall,summary_by_class}.csv`.
- Part 2 (70-pixel global ERA5+MODIS): `experiments/global_era5_chronos/
  outputs/era5_global70{_clean,_summary_overall,_summary_by_class,_summary_by_region}.csv`,
  `experiments/global_era5_chronos/data_selection/global_candidate_pixels_70.csv`.
- ERA5 equivalence figure (slide 8): built from the same evergreen-pixel
  2021–2022 comparison data as the original validation
  (`reports/ERA5_CLOUD_EQUIVALENCE_REPORT.md`), now shown as an actual
  time-series plot rather than only a correlation table, per explicit
  request.

## What changed from the original version of this deck (2026-09-16)

The original Part 2 (70-pixel CONUS cloud-ERA5 vs. gridMET head-to-head)
is **not deleted** — it remains fully documented in
`experiments/global_era5_chronos/reports/ERA5_CLOUD_LARGESCALE_REPORT.md`
and its own figures still exist under
`experiments/global_era5_chronos/outputs/`. It was removed from *this deck*
specifically because the user asked to replace Part 2 with the new global
experiment, not because the CONUS-ERA5 result was wrong or superseded
scientifically — the two are complementary findings (CONUS-ERA5 vs.
CONUS-gridMET; CONUS-gridMET vs. global-ERA5) documented separately.

## Known data-hygiene note (disclosed, not hidden, still applies)

`experiments/global_era5_chronos/results/evergreen/metrics_era5_cloud.txt`
was originally written by a short-context (2020–2021) equivalence-validation
run, then later overwritten by the CONUS large-scale batch run's evergreen
row (same filename, longer context). Both numbers were individually correct
for their own run; this file no longer reflects the short-context one. Not
relevant to any number shown in the current version of this deck (the
equivalence slide now shows the visual time-series comparison rather than
that specific R² figure), but noted here for continuity with the deck's
git history.
