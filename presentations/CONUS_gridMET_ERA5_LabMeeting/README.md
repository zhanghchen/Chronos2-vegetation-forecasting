# CONUS gridMET + ERA5 Lab Meeting Deck

*Generated: 2026-09-16*

12-slide summary of the two most recently completed large-scale Chronos-2
zero-shot experiments: the 32-pixel purity-filtered gridMET expansion and
the 70-pixel cloud-ERA5 experiment. No new Chronos-2 experiments were run
to build this deck — every number is read directly from already-saved
result files (see `build_deck.py`'s header comment and inline source
comments for the exact CSV/txt file each number comes from).

## Files

- `CONUS_gridMET_ERA5_LabMeeting.pptx` — the deck (12 slides).
- `build_deck.py` — editable slide source. Re-run with
  `/home/deh25003/miniconda3/bin/python3 build_deck.py` to regenerate the
  .pptx after editing.
- `make_figures.py` — builds the 4 NEW figures below. Re-run with the same
  interpreter to regenerate.
- `figures/` — all figures embedded in the deck:
  - **New, built by `make_figures.py`**: `map_32pixel_conus.png`,
    `map_70pixel_conus.png` (CONUS pixel maps colored by dominant
    vegetation class, each with a small world-context inset making clear
    the pixels are CONUS-only), `era5_vs_gridmet_winloss.png` (sorted
    per-pixel R² difference, ERA5 vs. gridMET), `era5_vs_gridmet_byclass.png`
    (mean R² by vegetation class, ERA5 vs. gridMET).
  - **Reused, copied unmodified from existing experiment outputs**:
    `exp1_r2_by_pixel_and_class.png` (from
    `outputs/purity32_pixel_study/r2_by_pixel_and_class.png`),
    `exp2_r2_by_pixel_and_class.png` and `exp2_vs_gridmet_scatter.png`
    (from `experiments/global_era5_chronos/outputs/`).

## Data sources for every number on the deck

- Experiment 1 (32-pixel gridMET): `outputs/purity32_pixel_study/
  {zero_shot_32pixels,summary_overall,summary_by_class}.csv`.
- Experiment 2 (70-pixel cloud ERA5): `experiments/global_era5_chronos/
  outputs/{era5_cloud_70pixels_clean,era5_cloud_summary_overall,
  era5_cloud_summary_by_class,era5_cloud_vs_gridmet_matched}.csv`.
- Pixel coordinates/vegetation class: `AELSTM/outputs/
  pft_multipixel_selection/pft_diverse_pixels.csv`.
- ERA5 equivalence-validation table (slide 8): the CDS row is read live
  from `experiments/global_era5_chronos/results/evergreen/metrics_era5.txt`;
  the raw-variable Pearson-r row and the cloud-ERA5 short-context row are
  taken from the already-written, already-verified text of
  `experiments/global_era5_chronos/reports/ERA5_CLOUD_EQUIVALENCE_REPORT.md`
  rather than re-read from `results/evergreen/metrics_era5_cloud.txt` — see
  the note below.

## Known data-hygiene note (disclosed, not hidden)

`results/evergreen/metrics_era5_cloud.txt` was originally written by the
short-context (2020–2021) equivalence-validation run (R²=0.8741) but was
**later overwritten** by the large-scale batch run's evergreen row (same
site, same filename, 22-year context, R²=0.8082) when
`run_era5_chronos_batch.py` was run afterward. Both numbers are individually
correct for their own (different-context) run; the file on disk now only
reflects the large-scale one. The equivalence report's prose already
recorded the short-context number correctly at the time, so slide 8 (which
quotes the equivalence validation specifically) uses that report's text
rather than re-reading the now-overwritten file, and slide 9 (large-scale
results) uses the large-scale batch CSV, which is unaffected. No numbers
here are wrong; this note exists so the discrepancy between the two
evergreen R² values seen across slides 8 and 9 is understood, not mistaken
for an error.
