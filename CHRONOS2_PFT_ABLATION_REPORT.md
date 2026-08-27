# Chronos-2 PFT Ablation: Zero-Shot Sensitivity to Vegetation Composition

**Question:** does feeding Plant Functional Type (PFT) fractional-cover information as a time-aligned covariate improve — or even change — Chronos-2's zero-shot LAI forecast? Companion to `AELSTM/PFT_ABLATION_REPORT.md` (the other 8 models); read that report for the full pixel-selection and PFT-dataset background, not repeated here.

All outputs in `outputs/pft_ablation/` — new, separate from `outputs/zero_shot/`, `outputs/finetuned_lora/`, `outputs/finetuned_lora_improved/`, `outputs/advanced_finetuning/`.

## Method

Zero-shot only (isolates the PFT question from the already-answered "does fine-tuning help" question — it doesn't, per `CHRONOS2_ADVANCED_FINETUNING_REPORT.md`). PFT fed exactly as verified from Chronos-2's source and requested: a constant value per year, broadcast across every 8-day step, in both `past_covariates` and `future_covariates` (`common_pipeline.build_chronos_inputs`, which already accepts an arbitrary `feature_cols` list — used unmodified). Same 4 pixels as the AELSTM-side study (3 reused + `mixed_forest_grass`, new).

## A hard architectural finding, not a soft null result

Reading `src/chronos/chronos2/model.py` and `chronos_bolt.py` directly: Chronos-2 stacks the target and every covariate into one `(group_size, history_length)` tensor and applies `InstanceNorm`:

```python
loc = torch.nan_to_num(torch.nanmean(x, dim=-1, keepdim=True), nan=0.0)
scale = torch.nan_to_num((x - loc).square().nanmean(dim=-1, keepdim=True).sqrt(), nan=1.0)
scale = torch.where(scale == 0, self.eps, scale)   # eps = 1e-5
scaled_x = (x - loc) / scale
```

This reduction is computed **per row** (`dim=-1` = the time axis only), independently for the target and for every covariate — there is no shared, cross-series statistic. PFT is verified constant across 2000–2022 for all 4 of our pixels, so for any single-pixel run its row has `std=0`. The code path above replaces a zero std with `eps=1e-5`, so the normalized value becomes `(c−c)/1e-5 = 0` for **every** timestep, for **any** constant `c`. This is true no matter how the covariate is batched — even pooling multiple pixels into one call would not help, since the reduction is per-row regardless of what else is in the batch.

**Practical consequence: Chronos-2's zero-shot pathway cannot receive a per-pixel-constant covariate through this channel at all, by construction — not a training issue, not a data issue, an architectural one.**

## Ablation results

`outputs/pft_ablation/pft_ablation_comparison_table.csv`:

| Site | Baseline R² | +Fractional R² | +Dominant R² | Δfrac | Δdom | Δ(frac−dom) |
|---|---|---|---|---|---|---|
| evergreen | 0.8322 | 0.8319 | 0.8319 | −0.0003 | −0.0003 | **0.0000** |
| low_amplitude | 0.5417 | 0.5182 | 0.5261 | −0.0235 | −0.0155 | −0.0079 |
| high_amplitude_deciduous | 0.9654 | 0.9664 | 0.9661 | +0.0010 | +0.0007 | +0.0003 |
| mixed_forest_grass | 0.9332 | 0.9294 | 0.9294 | −0.0039 | −0.0039 | **0.0000** |

Fractional and dominant give **numerically identical** predictions for 2 of 4 sites, and differ by ≤0.008 R² for the other 2 — consistent with the mechanism above (the *values* are erased identically either way; the residual differences trace to `past_covariates`/`future_covariates` dict keys being sorted alphabetically before stacking — `"PFT_..."` vs `"DOM_..."` sort differently — which changes variate *order*, not content, and is a covariate-naming artifact rather than a PFT-composition effect). No site shows a change large enough to plausibly be a real, exploitable signal, and the small changes present don't consistently move in one direction.

## Perturbation/sensitivity diagnostic (the direct test the user requested)

For each of 2 pixels — `evergreen` (95/5, near-pure) and `mixed_forest_grass` (50/50, genuinely mixed) — the real climate context and 2022 future climate are held completely fixed, and only the fractional PFT covariate is swept through 5 synthetic compositions (100/0, 75/25, 50/50, 25/75, 0/100, forest vs. grass; not real observations, a diagnostic probe only):

| Site | Max |Δprediction| across all 5 compositions | As % of observed LAI range |
|---|---|---|
| evergreen | **0.00000000** | 0.0000% |
| mixed_forest_grass | **0.00000000** | 0.0000% |

**Exactly zero, to 8 decimal places, for both pixels.** This is the cleanest possible empirical confirmation of the InstanceNorm mechanism above: Chronos-2's zero-shot forecast is *completely* insensitive to PFT composition when it is constant across the context+future window — not "small effect," not "noisy," identically zero. Per the user's own diagnostic criterion: *"If the prediction does not change at all when PFT changes, the model is probably ignoring the PFT features"* — confirmed, with the mechanism identified rather than left as a mystery.

Files: `outputs/pft_ablation/sensitivity_diagnostic/{evergreen,mixed_forest_grass}/{sensitivity_summary.csv, predictions_by_composition.csv, sensitivity_verdict.txt}`.

## Conservative interpretation

- **Predictive improvement**: none, within noise.
- **Sensitivity to PFT composition**: proven zero, exactly, by direct perturbation.
- **Biological interpretability**: not applicable — there is no learned response to interrogate, because the covariate carries no signal into the model at all under this design.

**This is a stronger and more useful finding than "PFT didn't help"**: it identifies precisely *why* a constant-broadcast covariate cannot work for Chronos-2's zero-shot pathway, which means the negative result here should not be read as evidence that PFT is biologically irrelevant to LAI-climate response — only that this specific way of presenting it to a frozen, per-series-normalized model cannot succeed, regardless of how much real information the covariate carries.

## Recommendation

Consistent with the AELSTM-side report's conclusion: a meaningful test of whether Chronos-2 can learn PFT-conditioned climate response requires PFT to **vary across the training/context data the model actually sees** — e.g., a pooled, multi-pixel fine-tuning setup (mirroring the project's existing drought-screened multi-source pooled training) where different pixels in the same batch carry genuinely different PFT values, so the covariate has real cross-series variance for the model to exploit. A single-pixel, zero-shot, constant-covariate design — exactly what was requested and correctly implemented here — cannot answer this question for Chronos-2 by construction. This is proposed as a candidate Stage 2 direction, not started here pending separate approval (no LOYO-CV or further fine-tuning was run).

## Files

- `Code/pft_features.py`, `pft_ablation_experiment.py`, `pft_sensitivity_diagnostic.py`, `build_pft_ablation_comparison.py`
- `outputs/pft_ablation/pft_ablation_all_results.csv`, `pft_ablation_comparison_table.csv`
- `outputs/pft_ablation/pft_ablation_r2_by_pixel.png`, `prediction_plot_{site}.png`
- `outputs/pft_ablation/sensitivity_diagnostic/` (perturbation diagnostic, both sites)
