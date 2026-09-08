# Deliverable A — Experiment Audit

Audit of the full `Chronos2-vegetation-forecasting` repository (code, configs, result CSVs,
markdown reports, README, presentation decks) as of 2026-09-08. Every number quoted below was
either read directly from a result CSV or cross-checked against one; three anchor files
(`outputs/fair_comparison_vs_raw_observations.csv`, `outputs/loyo_cv/comparison/loyo_summary_mean_std.csv`,
`outputs/advanced_finetuning/final_ranking_table.csv`) were spot-verified against their reports
during this audit and matched exactly. Nothing below is invented; where information is genuinely
absent from the repository it is marked "not recorded" rather than assumed.

**Shared task setup** (applies to every experiment unless noted): LAI target from the **HiQ-LAI**
product (8-day composite, ~1/24° (~4.6 km) native grid, CONUS, 2000–2022); 7 daily **gridMET**
climate covariates (`tmmx, tmmn, pr, srad, vpd, sph, vs`) aligned to each LAI composite's 8-day
window by mean; Chronos-2 consumes historical LAI as `target`, historical climate as
`past_covariates`, and **actual observed future climate** as `future_covariates` (the model is
never asked to forecast the covariates themselves — only LAI, given known future weather).
Metrics: RMSE, MAE, MAPE (`Cal_mape`-style, positive rows only), R², Pearson r — identical
definitions to the sibling AELSTM project so all 10 methods are directly comparable. All
AELSTM-family baselines (RF, SVM, LSTM, BiLSTM, GRU, RNN, CNN, AELSTM) are trained **from scratch
per pixel**, from the separate AELSTM repository, on **past climate only** (no future covariates —
a structurally easier problem for Chronos-2's task framing, an important interpretive caveat
carried through the whole paper) and rescored against the same **raw, unsmoothed** LAI observations
Chronos-2 uses (AELSTM's own pipeline reports metrics against a Savitzky–Golay-smoothed target;
`build_fair_comparison.py` recomputes every baseline against raw observations from already-saved
predictions — no retraining).

---

## Experiment 1 — Zero-shot & LoRA fine-tuning, single 2022 test split

- **Research question**: How does pretrained Chronos-2 (zero-shot and LoRA-fine-tuned) perform on
  single-pixel LAI forecasting, and how does it compare to the AELSTM-family baselines?
- **Dataset / pixels**: 3 pixels — `low_amplitude` (37.53°N, 117.56°W), `high_amplitude_deciduous`
  (36.23°N, 84.48°W), `evergreen` (30.53°N, 82.43°W).
- **Input variables**: LAI + 7 gridMET variables (see above).
- **Context length**: 2000 → 2021 (~1002 8-day steps, ~22 years).
- **Forecast horizon**: 45 steps (all of 2022).
- **Train/val/test split**: train < 2022, test = 2022 (no internal validation split for zero-shot;
  none needed — no trainable weights).
- **Setting**: zero-shot (no trainable weights) and LoRA fine-tuned (`lr=1e-4`, rank 8/α16,
  1000 fixed steps, **no validation-based checkpoint selection** — Amazon quickstart-notebook
  defaults, unmodified).
- **Baselines**: RF, SVM, LSTM, BiLSTM, GRU, RNN, CNN, AELSTM (all from the AELSTM project).
- **Metrics**: RMSE, MAE, MAPE, R², Pearson r, vs. raw observed LAI.
- **Result files**: `outputs/zero_shot/<pixel>/{predictions.csv,metrics.txt}`,
  `outputs/finetuned_lora/<pixel>/{predictions.csv,metrics.txt}`,
  `outputs/fair_comparison_vs_raw_observations.csv` (✅ authoritative comparison table),
  `outputs/fair_comparison_rank_consistency.csv`. Superseded/non-authoritative:
  `outputs/chronos2_vs_aelstm.csv` (naively merges AELSTM's own smoothed-target metrics — kept only
  to show what AELSTM's pipeline reports internally, explicitly flagged "not for cross-model
  ranking" in the project's own README).
- **Classification: FINAL.** This is the project's foundational, most-cited result; verified
  directly against `fair_comparison_vs_raw_observations.csv` during this audit (exact match).

## Experiment 2 — Leave-One-Year-Out Cross-Validation (LOYO-CV)

- **Research question**: Does the single-2022-split result hold up across many years and hide
  year-specific failure? Is Chronos-2 (zero-shot / LoRA) more or less robust to anomalous years
  than the baselines?
- **Dataset / pixels**: same 3 pixels as Experiment 1.
- **Context length**: fixed 12-year rolling window immediately preceding each held-out year (not
  classic all-other-years LOYO — would leak future years into a forecaster; not an expanding
  window — would confound "hard year" with "how much training data this fold got").
- **Forecast horizon**: 1 held-out year (45 steps) per fold.
- **Held-out years**: 2012–2022 (11 folds).
- **Setting**: both zero-shot and LoRA fine-tuned, every fold (no validation-based checkpoint
  selection within LOYO-CV folds — same fixed-1000-step LoRA protocol as Experiment 1).
- **Baselines**: same 8 AELSTM-family models, same fold design.
- **Total fold results**: 3 pixels × 11 years × 10 methods = 330.
- **Result files**: `outputs/loyo_cv/<pixel>/fold_<year>_metrics.csv` (33 files),
  `outputs/loyo_cv/comparison/loyo_all_folds.csv` (330 rows, long format — primary source),
  `loyo_summary_mean_std.csv`, `loyo_rank_consistency_<pixel>.csv`. Verified: `zero_shot`/`evergreen`
  row (R²_mean=−0.134, R²_median=0.583, R²_std=2.495) matches `LOYO_CV_FINDINGS.md` exactly.
- **Classification: FINAL.** The project's most statistically substantial robustness evidence
  (330 fold results); one implementation bug (`build_chronos_inputs()`'s `future = df.iloc[split_idx:]`
  silently including all subsequent years, not just the target year, when looped across years other
  than the final one) was identified and fixed with a dedicated `build_chronos_inputs_loyo()` before
  this was run — documented in the project README, not a live caveat on the current results.

## Experiment 3 — Leakage diagnostic: `evergreen`/2012

- **Research question**: Is the catastrophic `evergreen`/2012 LOYO-CV failure (R² as low as −8.29)
  distribution shift (the model never saw a comparable drought) or a Chronos-2-specific
  representational limitation?
- **Dataset / pixel**: `evergreen` only.
- **Setting**: three conditions — zero-shot (reference only), LoRA fit on 2000–2011 (2012 unseen,
  reproduces the LOYO-CV fold-2012 condition), LoRA fit on 2000–2012 (2012 **included** in the
  training pool — **deliberate data leakage**, explicitly and repeatedly flagged in the source
  report as *not a valid evaluation protocol*).
- **Result files**: `outputs/leakage_diagnostic_2012/evergreen/{leakage_diagnostic_metrics.csv,
  leakage_diagnostic_predictions.csv, leakage_summary_table_chronos2.csv}`.
- **Classification: FINAL, diagnostic-only.** Valid and complete as a mechanistic diagnostic; the
  "leakage" condition's numbers (R²=−0.50) must **never** be cited as a forecasting-skill result in
  the manuscript — only the contrast between conditions (ΔR²=+7.79 recovery) is scientifically
  usable, and only to support the distribution-shift interpretation, exactly as the source report
  itself insists.

## Experiment 4 — Improved (validation-selected) LoRA fine-tuning

- **Research question**: Does the original fine-tuning result's apparent uniform harm come from a
  real ceiling, or from the absence of validation-based checkpoint selection?
- **Dataset / pixels**: same 3 pixels.
- **Setting**: chronological validation (context 2000–2019→2020, 2000–2020→2021), small grid search
  (`lr∈{1e-5,1e-4}×rank∈{4,8,16}`, 6 configs/pixel), early stopping, two-stage refit on full
  pre-2022 data at the winning config, single ungraded 2022 evaluation.
- **Result files**: `outputs/finetuned_lora_improved/<pixel>/{search_summary.csv,predictions.csv,
  metrics.txt}`, `outputs/finetuned_lora_improved/comparison/three_way_comparison.csv`.
- **Classification: FINAL.** Supersedes the *interpretation* of Experiment 1's fine-tuning result
  ("consistently harmful" → "harmful mainly because unvalidated, and most of that damage is
  avoidable") without invalidating Experiment 1's numbers, which remain a legitimate "naive
  fine-tuning" condition kept for comparison, not an error to be discarded.

## Experiment 5 — Spatial transfer (`evergreen` → `evergreen_west`)

- **Research question**: Does a Chronos-2 LoRA adapter fit on one pixel generalize to a different,
  distant pixel of the same vegetation type without any target-specific fine-tuning?
- **Dataset / pixels**: `evergreen` (source, GA) and `evergreen_west` (target, Klamath Mountains,
  N. CA/S. OR border, ~3,700 km away), both needleleaf evergreen forest.
- **Setting**: LoRA fit on `evergreen`'s full 2000–2022 series, evaluated using `evergreen_west`'s
  own context and real 2022 climate — no retraining on the target. Reference-only zero-shot at the
  target pixel is also reported.
- **Result file**: `outputs/spatial_transfer/evergreen_to_evergreen_west/spatial_transfer_summary_chronos2.csv`.
- **Classification: FINAL.**

## Experiment 6 — Advanced PEFT methods (6 methods beyond LoRA)

- **Research question**: Does a broader set of modern parameter-efficient fine-tuning methods beat
  zero-shot where standard LoRA did not?
- **Dataset / pixels**: same 3 pixels.
- **Methods**: DoRA, VeRA, IA3, LN-Tuning, BitFit, partial (last-block) fine-tuning — plus the
  existing zero-shot / original LoRA / improved LoRA as reference rows (not rerun).
- **Setting**: identical validated protocol to Experiment 4 (chronological validation, early
  stopping, test never touches selection); equal-sized 4-config search budget per method; 90
  fine-tuning runs total (~85 min, single A100).
- **Result file**: `outputs/advanced_finetuning/final_ranking_table.csv` — verified exactly against
  `CHRONOS2_ADVANCED_FINETUNING_REPORT.md` during this audit.
- **Classification: FINAL.**

## Experiment 7 — PFT ablation (single-pixel, constant covariate)

- **Research question**: Does feeding ESA CCI Plant Functional Type (PFT) fractional cover as a
  covariate change Chronos-2's zero-shot forecast?
- **Dataset / pixels**: `low_amplitude`, `high_amplitude_deciduous`, `evergreen`, +
  `mixed_forest_grass` (new, IL, 50% broadleaf-deciduous forest / 50% natural grassland).
- **Setting**: zero-shot only; PFT broadcast as a per-year constant across every 8-day step, in both
  fractional and dominant-class representations; direct 5-composition perturbation-sensitivity
  sweep at 2 pixels.
- **Result files**: `outputs/pft_ablation/pft_ablation_comparison_table.csv`,
  `sensitivity_diagnostic/{evergreen,mixed_forest_grass}/sensitivity_summary.csv`.
- **Classification: FINAL — architectural, not merely a null result.** Direct source inspection
  (`chronos/chronos2/model.py`'s InstanceNorm) plus an exact-zero (0.00000000) empirical
  perturbation result together establish *why* this design cannot work, not just that it didn't.

## Experiment 8 — Multi-pixel PFT conditioning (FiLM, 70 pixels)

- **Research question**: If PFT is made to genuinely vary across training rows (architecture fix:
  a FiLM-conditioning head), can Chronos-2 learn a PFT-dependent LAI-climate response?
- **Dataset / pixels**: 70 pooled pixels (farthest-point-sampled in 10-class PFT-composition space
  + geographic separation), Experiment A (temporal holdout, train+test on all 70), Experiment B
  (spatial holdout, train on 55, test on 15 unseen).
- **Setting**: FiLM head (100,544 params, 0.084% of model) on target-row forecast hidden states,
  base model frozen; only 2 genuine rolling training-year transitions available; validation-selected
  step count.
- **Result files**: `outputs/pft_multipixel/{summary_table.csv,per_pixel_r2_pivot.csv,
  mixed_vs_pure_correlation.csv}`.
- **Classification: PRELIMINARY, superseded in part by Experiment 9.** The architecture-verification
  findings (identity-at-init, gradient confinement, smoke-test sensitivity) remain valid and are
  reused unmodified by Experiment 9. The *substantive conclusion* ("too little data, more windows
  should fix it") is the hypothesis Experiment 9 was designed to test — and falsifies for 3 of 4
  architectures. Do not cite Experiment 8's "not enough data yet" framing as the paper's final word
  on PFT; Experiment 9 is the final word.

## Experiment 9 — PFT-v2 (4 architectures + shuffled-PFT control)

- **Research question**: Is there *any* architecturally distinct way to make PFT improve Chronos-2
  LAI forecasting, or can this be ruled out with a decisive control?
- **Dataset / pixels**: same 70-pixel pool, 8 rolling training windows (2010→2018) + 3 held-out
  pre-2022 validation windows.
- **Architectures**: `deep_mlp` (Experiment 8's design, more data), `deep_mlp_reg` (regularized),
  `linear_mixture` (biologically-structured, per-class response vectors), `low_rank` (rank-8
  bottleneck).
- **Critical control**: `low_rank` (the only architecture that trained past step 0) retrained on
  **randomly shuffled PFT-to-pixel assignments**.
- **Result files**: `outputs/pft_v2/final_2022_summary.csv`, `real_vs_shuffled_ttest.csv`,
  `per_pixel_final_comparison.csv`, `seasonal_phase_rmse.csv`, `by_dominant_pft_final.csv`.
- **Classification: FINAL — the project's decisive PFT result.** Paired t-test p=0.245 (n=70,
  Wilcoxon p=0.663) between real and shuffled PFT is a genuine negative control, not merely "no
  improvement found."

## Experiment 10 — Predictor sensitivity / ablation

- **Research question**: Which of the 7 climate predictors matter, for which models, at which
  pixels — and does a leaner predictor set help?
- **Dataset / pixels**: same 3 pixels; 9 methods (8 AELSTM-family + Chronos-2 zero-shot only —
  LoRA excluded, would need its own per-subset hyperparameter search to stay fair).
- **Setting**: Phase 1, leave-one-predictor-out (7 configs); Phase 2, 4 pre-registered grouped
  ablations chosen from Phase 1's ranking.
- **Result files**: `outputs/predictor_ablation/comparison/predictor_ablation_all_results.csv`,
  `reduced_sets_summary.csv`.
- **Classification: FINAL.**

## Experiment 11 — Global ERA5 generalization study (in progress)

- **Research question**: How well does zero-shot Chronos-2 generalize to LAI forecasting outside
  the U.S., using ERA5 as a common global meteorological input?
- **Status as of 2026-09-08**: infrastructure complete (variable mapping, unit conversions, 45-pixel
  non-U.S. site selection, Chronos-2 integration script), ERA5 download for a single CONUS
  validation pixel still in progress (rate-limited by the Copernicus Climate Data Store), **zero
  Chronos-2 forecasts have been produced from ERA5 data**. No global LAI source has been acquired
  yet for the 45 non-U.S. pixels.
- **Classification: DEBUGGING / IN PROGRESS — excluded from the paper's evidence base.** Mention
  only in Discussion/Future Work as an ongoing generalization test; do not cite any ERA5-derived
  number as a result, because none exists yet.

---

## Summary classification table

| # | Experiment | Classification | Use in paper |
|---|---|---|---|
| 1 | Zero-shot / LoRA, single split | **FINAL** | Table 2, §6.1–6.2 |
| 2 | LOYO-CV (11y × 3px) | **FINAL** | Table 3, §6.3 |
| 3 | Leakage diagnostic (2012) | **FINAL (diagnostic only)** | §6.6, mechanistic evidence only |
| 4 | Improved LoRA | **FINAL** | Table 4, §6.5 |
| 5 | Spatial transfer | **FINAL** | §6.3 / §6.6 |
| 6 | Advanced PEFT (6 methods) | **FINAL** | Table 4, §6.5 |
| 7 | PFT ablation (single-pixel) | **FINAL** | §6.5 (mechanistic) |
| 8 | PFT multi-pixel (FiLM, 70px) | **PRELIMINARY (superseded by #9)** | §6.5, brief, framed as motivating #9 |
| 9 | PFT-v2 (shuffle control) | **FINAL** | §6.5, primary PFT evidence |
| 10 | Predictor ablation | **FINAL** | Discussion / supplementary |
| 11 | Global ERA5 | **IN PROGRESS** | Future Work only, no results cited |
