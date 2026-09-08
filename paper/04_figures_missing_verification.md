# Deliverables G, H, I — Figure Plan, Missing Experiments, Claim-Evidence Verification

## G. Figure selection / redesign plan

Reuse existing figures wherever a materially equivalent one already exists in the repository
(all generated from the same verified result CSVs); redesign only where the existing figure mixes
in content outside this paper's scope (e.g., full 10-method LOYO panels when the paper wants a
Chronos-2-centered view) or where no figure currently isolates the exact comparison needed.

| # | Content | Source (reuse) | Action |
|---|---|---|---|
| **Fig. 1** | Overall experimental framework: task formulation (context/target/covariates), the 3 core pixels on a CONUS map, and the experiment tree (zero-shot → LOYO-CV → spatial transfer → adaptation methods → PFT conditioning) | none exists in this exact form | **New figure**, schematic, no new data |
| **Fig. 2** | Representative LAI forecasting examples: observed vs. zero-shot Chronos-2 vs. best/worst baseline, one panel per core pixel | `outputs/final_comparison/<pixel>/all_methods_vs_raw_obs.png` | **Reuse**, trimmed to zero-shot + AELSTM + 1 strong baseline (currently shows all 10 methods — visually dense for a main-text figure; keep the full version as supplementary) |
| **Fig. 3** | Zero-shot Chronos-2 vs. supervised baselines, rank consistency across pixels | `outputs/all_models_r2_bars.png` (uses the ⚠️ naive, smoothed-target comparison per README) | **Redesign** — rebuild from `outputs/fair_comparison_vs_raw_observations.csv` (the authoritative source); the existing PNG must not be used directly per the project's own README warning |
| **Fig. 4** | Chronos-2 performance across years (LOYO-CV) | `outputs/loyo_cv/comparison/loyo_r2_distributions.png`, `loyo_year_difficulty_heatmap.png` | **Reuse**, both directly relevant to §6.3 |
| **Fig. 5** | Performance across vegetation/LAI regimes | `outputs/predictor_ablation/comparison/predictor_importance_by_pixel.png` | **Reuse** |
| **Fig. 6** | Zero-shot vs. fine-tuning/adaptation, including the PFT shuffle control | `outputs/advanced_finetuning/r2_by_pixel_all_methods.png` + `outputs/pft_v2/mixed_vs_pure_final.png` | **Combine into one two-panel figure** — panel (a) PEFT sweep, panel (b) real-vs-shuffled PFT scatter; this pairing does not currently exist as a single figure and is the paper's most important negative-result figure |
| **Fig. 7 (supplementary)** | Spatial transfer | `outputs/spatial_transfer/evergreen_to_evergreen_west/spatial_transfer_r2_drop_combined.png` | **Reuse** |
| **Fig. 8 (supplementary)** | Leakage diagnostic mechanism | `outputs/leakage_diagnostic_2012/evergreen/leakage_cross_project_r2_comparison.png` | **Reuse** |

**Figures explicitly excluded**: PFT-multipixel's (Experiment 8) standalone result figures
(`outputs/pft_multipixel/r2_summary_by_experiment.png` etc.) — superseded by PFT-v2's shuffle-control
figure; including both would visually imply two independent positive-leaning results where only one
(the null/shuffle result) is the paper's real finding.

## H. Missing experiments or information

Explicitly not invented or assumed anywhere in the manuscript; listed here as gaps for future work
or required clarification before submission.

1. **3 pre-selected pixels never run through Chronos-2**: `cropland_managed`, `grassland_shrubland`,
   `strong_interannual_variability`. These exist in `AELSTM/outputs/pixel_selection/selected_pixels.csv`
   with full metadata but have no corresponding `outputs/zero_shot/<pixel>/` directory in this
   project. Running them would materially strengthen the "3 pixels is a small sample" limitation.
2. **`western_kansas_eastern_colorado`** (the original AELSTM project pixel) has full baseline
   results but **no Chronos-2 run at all** — not included in any comparison table in this paper.
3. **Global ERA5 generalization study**: infrastructure-complete, zero forecasts produced as of this
   writing (see `00_experiment_audit.md`, Experiment 11). Cannot be cited as a result; may be added
   as a revision once real numbers exist.
4. **Unseeded fine-tuning randomness**: `Chronos2Dataset`'s training-window sampling during `fit()`
   is not seeded across runs. The leakage diagnostic's own rerun of the original-LoRA condition
   reproduced R²=−8.29 vs. the LOYO-CV study's originally recorded −8.52 for the identical condition
   — a real, small (~0.6 ΔR²) source of run-to-run noise that is smaller than every effect this paper
   treats as a finding, but has not been formally quantified (e.g., via repeated seeds) anywhere in
   the project.
5. **No formal significance test for most comparisons.** Only the PFT real-vs-shuffled comparison
   (§6.5) has a paired statistical test (t-test, Wilcoxon). The single-2022-split rankings (Table 2)
   and most LOYO-CV comparisons are descriptive (mean/median/rank), not tested for significance —
   worth flagging explicitly in Limitations if a reviewer requests it, and a natural extension (e.g.
   a paired test across LOYO-CV folds, which the 330-row long-format CSV would support without new
   experiments).
6. **PFT conditioning of covariate rows, not just the target row**, and cross-attention/
   mixture-of-experts-style gating mechanisms were reasoned about in `CHRONOS2_PFT_V2_REPORT.md` §5
   but never run, given the shuffle-control evidence obtained from cheaper variants first. Flagged
   there as "not exhausted," not "ruled out."
7. **Single pretrained checkpoint.** All results use `amazon/chronos-2` as pulled during this
   project; no comparison against a different Chronos-2 checkpoint version or against the original
   Chronos-1 family was conducted.
8. **Related-work citations.** Sections 2.1, 2.2, 2.3 (TSFM survey beyond Chronos-2 itself), and 2.4
   require a literature search this project did not perform as part of its experimental work; do not
   submit with the `[CITATION NEEDED]` placeholders in the manuscript draft still in place.

## I. Claim-evidence verification table

Every major numerical/scientific claim in the manuscript, its supporting experiment, exact result
file, the numerical evidence, a confidence rating, and any caveat. Confidence: **High** = directly
verified against a CSV during this audit; **Medium** = taken from a source report not independently
re-verified against raw CSVs in this audit pass, but internally consistent with everything that was
checked; **Low** = inference/interpretation, not a direct measurement.

| Claim | Supporting experiment | Result file | Numerical evidence | Confidence | Caveat |
|---|---|---|---|---|---|
| Zero-shot Chronos-2 is best/tied-best on all 3 core pixels (2022) | Exp. 1 | `outputs/fair_comparison_vs_raw_observations.csv` | R²=0.542/0.965/0.832; mean rank 1.33/10 | **High** (verified during this audit) | Task asymmetry (future-covariate access) is the primary confound — must always be stated alongside this claim |
| Zero-shot Chronos-2 is 2nd-most-dependable method across 330 LOYO-CV folds | Exp. 2 | `outputs/loyo_cv/comparison/loyo_all_folds.csv`, `LOYO_CV_FINDINGS.md` §4 | mean rank 3.70/10 (RF 3.39/10); top-3 rate 21/33 | **High** (summary row verified during this audit) | "Second" only by mean rank; zero-shot has the single highest top-3 rate of any method |
| Chronos-2 has no general robustness advantage on anomalous years | Exp. 2 | `loyo_year_difficulty_heatmap.png`, `LOYO_CV_FINDINGS.md` §3 | 9th/10th on `evergreen`/2012; 1st/10th on `low_amplitude`/2018 | **Medium** | Based on only 2 genuine outlier folds — explicitly flagged in the source report as too few to generalize beyond "fold-dependent, not fixed" |
| Fine-tuning (original LoRA) consistently hurts | Exp. 1 | `outputs/fair_comparison_vs_raw_observations.csv` | ΔR² = −0.163, −0.014, −0.120, all 3 pixels | **High** (verified) | Superseded in interpretation, not number, by Exp. 4 |
| Validated LoRA recovers most (not all) of the gap | Exp. 4 | `outputs/finetuned_lora_improved/comparison/three_way_comparison.csv` | ΔR² vs. zero-shot: −0.042, −0.023, −0.003 | **High** (verified during this audit) | Still never beats zero-shot outright on any of 3 pixels |
| No PEFT method (7 tested) consistently beats zero-shot | Exp. 6 | `outputs/advanced_finetuning/final_ranking_table.csv` | mean R² 0.780 (ZS) vs. 0.683–0.769 (all methods); only 1/27 method×pixel cells beats ZS | **High** (verified during this audit) | The one exception (DoRA/`evergreen`, +0.0026) is explicitly reported as plausibly noise |
| Single-pixel constant PFT is architecturally erased | Exp. 7 | `outputs/pft_ablation/sensitivity_diagnostic/*/sensitivity_summary.csv` | Δprediction = 0.00000000 across 5 synthetic compositions, both pixels tested | **Medium** (mechanistic claim; direct source-code citation given in report, not re-inspected during this audit) | Exact zero is a strong, specific claim — verify the cited source lines (`chronos/chronos2/model.py`) if challenged |
| Real PFT provides no detectable benefit over shuffled PFT | Exp. 9 | `outputs/pft_v2/real_vs_shuffled_ttest.csv`, `final_2022_summary.csv` | ΔR²(real−shuffled) = −0.000166; paired t p=0.2453; Wilcoxon p=0.6628; n=70 (31 real-favoring, 39 shuffled-favoring) | **High** (verified during this audit, exact match to `real_vs_shuffled_ttest.csv`) | This is the paper's single most load-bearing statistical claim; the p-values were read directly from the saved test-result CSV, not recomputed from raw predictions in this audit pass — recommend recomputing from `per_pixel_final_comparison.csv` as a pre-submission sanity check, but the number is not merely "taken from a report" |
| LoRA spatial transfer loses nothing measurable (best of 9 methods) | Exp. 5 | `outputs/spatial_transfer/evergreen_to_evergreen_west/spatial_transfer_summary_chronos2.csv` | R²=0.8228 (transfer) vs. 0.8194 (target-local); Δ=+0.0034 | **High** (verified during this audit) | n=1 pixel pair — a single spatial-transfer test, not a distribution of transfers; "best of 9 methods" (cross-project ranking) not independently re-verified against the AELSTM-side CSV in this audit |
| `evergreen`/2012 failure is distribution shift, not a Chronos-2-specific limitation | Exp. 3 | `outputs/leakage_diagnostic_2012/evergreen/leakage_summary_table_chronos2.csv` | R² −8.29 (unseen) → −0.50 (leaked), ΔR²=+7.79; RMSE −59.9% | **High** (verified during this audit) | The "leaked" condition is invalid as an evaluation result by design — only the *contrast* between conditions is usable evidence, never the leaked R² itself as a forecasting-skill number; "2nd-largest recovery of 9 methods" (cross-project ranking) not independently re-verified against the AELSTM-side CSV in this audit |
| `srad` is the only universally important predictor | Exp. 10 | `outputs/predictor_ablation/comparison/predictor_ablation_all_results.csv` | ΔR² when removed (mean across 9 methods): −0.024/−0.012/−0.028, all 3 pixels | **High** (recomputed the mean-across-9-methods `no_srad` delta directly from the raw CSV during this audit for `low_amplitude`: −0.0241, matching the reported −0.024) | — |
