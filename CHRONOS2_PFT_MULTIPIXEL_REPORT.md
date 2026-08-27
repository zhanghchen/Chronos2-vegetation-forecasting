# Multi-Pixel PFT Conditioning: Can Chronos-2 Learn Climate × Vegetation-Composition Interactions?

**Central hypothesis tested:** `LAI response = f(historical LAI, climate, PFT composition)`, where PFT must vary *across* training pixels (not be a constant within one pixel's own record) for the model to have any chance of learning a genuine vegetation-dependent climate response. This is the direct architectural follow-up to `CHRONOS2_PFT_ABLATION_REPORT.md`, which showed a single-pixel constant PFT covariate is provably erased by Chronos-2's InstanceNorm.

All outputs in `outputs/pft_multipixel/` (new; `outputs/pft_ablation/`, `outputs/zero_shot/`, etc. untouched). Code: `Code/pft_multipixel_{dataset,model,train,sensitivity}.py`, `preprocessing/{select,plot,bulk_extract}_pft_diverse_pixels.py` (AELSTM repo), `Code/build_pft_multipixel_comparison.py`.

## 1. Pixel selection (70 pixels)

Farthest-point sampling in a 10-class fractional-composition space plus a geographic minimum-separation constraint. **A real bug was found and fixed while building this**: the first selection included 24/70 pixels (34%) with 100% NaN gridMET climate data despite passing every LAI-quality filter — gridMET (US-only) leaves ~40% of the nominal CONUS bounding box uncovered (ocean, Canada/Mexico border strips), concentrated near the pixels with the most extreme ("purest") compositions, which tended to sit near the grid's northern edge. Fixed by adding a 3-year/3-variable gridMET coverage mask to the selection filters and re-running; final 70 pixels verified to have zero climate or LAI gaps.

Final set: purity 0.46–1.00, 8 dominant classes (GRASS_NAT ×19, GRASS_MAN/cropland ×12, SHRUBS_NE/BD/ND ×7/7/6, TREES_BD/NE/ND ×7/6/6), 9 US regions. Table + diversity figures: `AELSTM/outputs/pft_multipixel_selection/`.

## 2. Architecture: verified that pooling is not sufficient, and why

Re-inspecting `src/chronos/chronos2/model.py`/`chronos_bolt.py`/`layers.py` directly (not assumed from the earlier report) confirmed: every covariate row's InstanceNorm statistics come from that row's own time values, independent of what else is batched with it — pooling many pixels changes nothing about a single row's own zero variance. `GroupSelfAttention` additionally has no positional or per-row-type encoding ("no natural ordering along the batch axis"), so there is no secondary channel through which an erased covariate's identity could be recovered.

**Fix**: `Chronos2PFTModel` (subclass of `Chronos2Model`) adds a small PFT-encoder MLP (10→64→1536, 100,544 params, 0.084% of the model) producing FiLM (scale, shift), applied to the target row's forecast-patch hidden states immediately before `output_patch_embedding`. Base model (119.5M params) frozen entirely; only the FiLM head trains. Zero-initialized final layer ⇒ byte-identical to the unmodified pretrained model at initialization (verified: max diff = 1.2e-4, floating-point-scale).

## 3. Smoke test (16 pixels, 30 steps) — mechanism confirmed working

All 6 checks passed: identity at init, gradients confined to the new head, loss decreases, embeddings non-zero after training, **and a large, clearly structured perturbation response** (100%-forest vs. 100%-grass median forecast differed by 0.43 LAI units, with a plausible forest>mix>grass ordering) — the architecture is unambiguously *capable* of learning and expressing a PFT-dependent response. Full details in the prior turn's report to the user.

## 4. Full experiment: leak-free protocol

Rolling one-year-ahead training windows (context≤2018→2019, context≤2019→2020) provide gradient signal; a genuinely held-out validation window (context≤2020→2021, forward-pass only) selects the best (LR, step) via early stopping across `LR ∈ {1e-3, 3e-3, 1e-2}`, 150 steps each; the final refit adds the validation window as a legitimate training target (now that its selection role is done) and trains for the selected step count; a single, ungraded evaluation uses context≤2021→**2022**, which never appears in any gradient step in any configuration.

- **Experiment A (temporal holdout)**: train + evaluate on all 70 pixels' own 2022.
- **Experiment B (spatial holdout)**: train on 55 pixels (stratified split, 15 held out entirely, including `low_amplitude`), evaluate only on the 15 unseen pixels' 2022.

## 5. Result: validation consistently selected ~1 training step, for every condition

| Experiment | PFT mode | Selected LR | best_step | Final refit steps | Result |
|---|---|---|---|---|---|
| A (temporal) | dominant | 1e-3 | 0 | 1 | — |
| A (temporal) | fractional | 1e-3 | 0 | 1 | — |
| B (spatial) | dominant | 1e-3 | 0 | 1 | — |
| B (spatial) | fractional | 1e-3 | 0 | 1 | — |

This is not a bug — the search curves (`outputs/pft_multipixel/expA_temporal/dominant/search_curve.csv`, etc.) show **train loss decreasing steadily while validation loss increases almost monotonically from step 0, at every one of the 3 learning rates tested, in every one of the 4 (experiment × PFT-mode) configurations.** With only 2 real rolling training-year transitions available, the 100K-parameter FiLM head overfits to those 2 specific years almost immediately; a properly validated stopping rule correctly rejects further training, leaving the final model statistically indistinguishable from an untrained (≈zero-shot) one.

## 6. Final metrics: no measurable benefit, exactly as the 1-step finding predicts

| Experiment | Condition | Mean R² | ΔR² vs. baseline | Mean RMSE | N |
|---|---|---|---|---|---|
| A (temporal, 70px) | baseline | 0.7655 | — | 0.2050 | 70 |
| A (temporal, 70px) | dominant | 0.7658 | **+0.0003** | 0.2048 | 70 |
| A (temporal, 70px) | fractional | 0.7653 | **−0.0002** | 0.2048 | 70 |
| B (spatial, 15 unseen px) | baseline | 0.8305 | — | 0.2206 | 15 |
| B (spatial, 15 unseen px) | dominant | 0.8294 | **−0.0012** | 0.2208 | 15 |
| B (spatial, 15 unseen px) | fractional | 0.8288 | **−0.0017** | 0.2209 | 15 |

Every ΔR² is within ±0.002 — an order of magnitude smaller than any effect that would be scientifically interesting, and fully consistent with "the validated model trained for essentially 1 gradient step." **Mixed-vs-pure**: correlation between PFT entropy and (R²(fractional) − R²(dominant)) is −0.05 (n=85 pixel×experiment rows) — no relationship, because there is no real fractional-vs-dominant difference to correlate with anything at this training budget.

## 7. Sensitivity diagnostics: the architecture can do it, the validated model chose not to

To distinguish "PFT can't reach the model" (the single-pixel finding) from "the model reached a validated conclusion not to use it" (this experiment), the perturbation sweep was run on **two** models per condition:

| Pixel | Validated (1-step) max Δprediction | Deliberately-overfit (150-step) max Δprediction |
|---|---|---|
| evergreen (near-pure forest) | 0.011 | **0.547** |
| mixed_forest_grass (50/50) | 0.011 | **0.629** |
| low_amplitude (near-pure grass) | 0.001 | **0.042** |

`outputs/pft_multipixel/sensitivity/perturbation_sweep_all_pixels.png`: the validated model's 5 composition curves are visually indistinguishable (confirming ≈0 sensitivity); the overfit model's curves visibly separate, tracking a smooth, physically plausible seasonal shape rather than an erratic one — direct evidence the architecture retains real capacity to express a PFT-dependent response, exactly matching the smoke test, but only once validation is bypassed.

**Climate × PFT response curves** (`climate_pft_response_curves.png`, overfit model, illustrative only): mean 2022 LAI vs. a ±50% precipitation anomaly, for 3 fixed compositions. Unlike the pure-PFT sweep, these curves are **not smooth or monotonic** — they zigzag across the anomaly range for all 3 pixels and all 3 compositions. Per the user's own interpretation guide, this is the "large or erratic change → possible overfitting / out-of-distribution behavior" case, not "smooth/systematic dependence" — the joint climate×PFT interaction is evidently much less constrained by the available training data than the PFT main effect alone.

## 8. Conservative interpretation

- **Predictive improvement**: none (|ΔR²| ≤ 0.002 in both experiments).
- **Sensitivity to PFT composition (validated model)**: negligible (max Δ ≤ 0.011).
- **Sensitivity to PFT composition (architecture capacity, unvalidated)**: large and smooth for direct PFT perturbation; erratic for joint climate×PFT perturbation.
- **Biological interpretability**: not established — the validated model doesn't use PFT enough to interrogate, and the overfit model's climate-interaction behavior is too erratic to trust as a "learned response" rather than noise fit to 2 particular years.

**This is a genuinely different conclusion from the single-pixel study**, and worth stating precisely: PFT information *can* reach Chronos-2 through this architecture (proven), but **this particular pooled-training protocol does not yet provide enough genuine temporal supervision (only 2 real rolling year-transitions) for a properly validated model to learn a PFT-dependent response that survives held-out validation.** The bottleneck has moved from "architecturally impossible" to "data-starved," which is a solvable, well-understood problem.

## 9. Answering the central question

**"Does a PFT-diverse multi-pixel framework let Chronos-2 learn useful vegetation-specific information?"** Not yet, with this training protocol — but not because the mechanism failed. It is because 2 rolling training-year transitions is too little real signal for a proper validation criterion to justify learning past step 1. The architecture-level question (can PFT reach the model, can it express a PFT-dependent response) is answered **yes**, unambiguously, by the smoke test and the overfit-model diagnostic.

## 10. Recommendation for a next iteration (not run — flagging only, per the instruction not to proceed further without approval)

The natural fix is **more genuine training-year diversity, not more pixels**: build many more rolling (context, future-year) windows per pixel (e.g., every year 2010–2020, not just 2), so the FiLM head sees enough distinct year-transitions that a real, generalizing signal is separable from single-year noise. This is a data/protocol change, not an architecture change — `Chronos2PFTModel` itself would be reused unmodified.

## Files

- Selection: `AELSTM/outputs/pft_multipixel_selection/{pft_diverse_pixels.csv, pft_diverse_pixels_diversity.png}`
- Data: `data/processed/sites_pft_multipixel/*.csv` (70 pixels), `data/processed/pft_diverse_pixels.csv`, `pft_multipixel_spatial_{train,holdout}.csv`
- Training: `outputs/pft_multipixel/{baseline, expA_temporal, expB_spatial}/` (search curves, configs, checkpoints, per-pixel predictions, metrics)
- Comparison: `outputs/pft_multipixel/{summary_table.csv, per_pixel_r2_pivot.csv, by_dominant_pft.csv, mixed_vs_pure_correlation.csv, r2_summary_by_experiment.png, mixed_vs_pure_scatter.png}`
- Sensitivity: `outputs/pft_multipixel/sensitivity/{perturbation_summary.csv, perturbation_sweep_all_pixels.png, climate_pft_response_curves.{csv,png}}`
