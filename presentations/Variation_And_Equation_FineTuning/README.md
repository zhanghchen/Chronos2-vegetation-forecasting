# Variation-Based Forecasting + Physics-Equation Fine-Tuning Deck

*Generated: 2026-10-21 · Updated: 2026-10-21 (expanded 5->8 slides: both
parts now show actual prediction curves, not just evaluation metrics)*

8-slide deck, deliberately concise - assumes the reader already has the
background from the earlier decks (LOYO-CV protocol, the composite-position
analysis, the first ad hoc physics equation attempt). Only new material and
final results are shown here.

## Part 1 (slides 2-4): forecasting the LAI variation directly

Builds on `Code/loyo_cv_anomaly_chronos2.py` / `experiments/global_era5_chronos/scripts/loyo_cv_anomaly_global.py`
(already committed earlier): Chronos-2 forecasts the LAI anomaly (value
minus its context-years-only, per-calendar-position climatology) directly,
rather than forecasting raw LAI and decomposing the seasonal cycle out
afterward. R² and Pearson r are computed on the anomaly itself - the
current, correct standard.

Slide 3 shows the actual predicted-vs-true variation curves for 5 example
CONUS pixels, deliberately spanning the full range from the pool's best
fit (Pearson r=0.94) to its worst (r=-0.72) - not cherry-picked. Slide 4
is the aggregate: mean Pearson r = 0.296 (CONUS, 770 folds) / 0.178
(Global, 748 folds) - modest, and the reason this follow-up (Part 2) was
pursued.

## Part 2 (slides 5-7): fine-tuning Chronos-2 with the exact equation

Uses `Code/physics_guided_phenology_equation.py`'s Stage 1 fit (the exact
logistic growth-mortality equation Prof. Wang proposed, not the earlier ad
hoc linear-term library) as a physics-consistency loss when LoRA
fine-tuning Chronos-2 - see `Code/physics_guided_chronos2_finetune_phenology.py`.

Validation: 3 project sites (evergreen, high_amplitude_deciduous,
low_amplitude) x all 11 LOYO-CV years (2012-2022) = 33 folds, comparing
zero-shot / plain fine-tune (no physics) / physics-guided fine-tune.
Physics weight (BETA_PHYSICS=0.001) was calibrated via a smoke test on one
fold BEFORE the full run, not tuned per-fold afterward.

**Result** (`outputs/physics_guided_chronos2_finetune_phenology/validation_results.csv`):

| | mean R² | median R² |
|---|---|---|
| Zero-shot (raw Chronos-2) | 0.380 | 0.644 |
| Plain fine-tune (no physics) | 0.287 | 0.590 |
| **Physics-guided fine-tune** | **0.424** | **0.674** |

Physics-guided fine-tuning beats zero-shot in 15/33 folds by count, but
wins on BOTH aggregate mean and median R² - its improvements are
concentrated on folds where zero-shot was weak (recovers most of the
evergreen/2012 drought-year loss: -7.64 -> -6.41), while its "losses" vs.
zero-shot are tiny ceiling-effect differences on the already-excellent
high_amplitude_deciduous site (R²~0.96). Plain fine-tuning alone actually
hurts on average (small-sample overfitting) - the physics term both fixes
that and pushes past zero-shot. Physics-guided beats plain fine-tuning in
22/33 folds (67%).

Slide 6 shows actual predicted-vs-observed LAI curves for 3 example folds
(evergreen/2013, low_amplitude/2014, high_amplitude_deciduous/2020),
re-running the fine-tuning fresh to generate them. This surfaced a real
finding worth keeping on record: re-running low_amplitude/2014
independently gave physics R²=0.058, not the 0.283 in the original
33-fold table above - fine-tuning has genuine run-to-run variance at
this sample size (different LoRA init + training-window sampling even
with the same seed, since the random-draw sequence differs when a fold
is run in isolation vs. as part of the full 33-fold loop). Disclosed
directly on slide 6 rather than re-rolling for a better-looking number -
the 33-fold aggregate above is the number to trust, not any single
illustrative fold.

## Files

- `Variation_And_Equation_FineTuning.pptx` - the deck (8 slides).
- `build_deck.py` - editable slide source. Re-run with
  `/home/deh25003/miniconda3/bin/python3 build_deck.py` to regenerate.
- `figures/` - all embedded figures, copied from their source locations.
