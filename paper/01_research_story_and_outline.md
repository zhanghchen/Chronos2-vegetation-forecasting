# Deliverables B, C, D — Research Story, Title, and Detailed Outline

## B. Proposed research story

The project's evidence base tells a coherent, non-obvious story if organized around Chronos-2
rather than chronologically:

1. **Zero-shot Chronos-2, with no training on this data at all, is competitive with — and often the
   best of — 8 supervised, from-scratch-trained baselines** on single-pixel LAI forecasting (mean
   rank 1.33/10 across 3 pixels; 3.70/10 across 330 LOYO-CV folds, second only to Random Forest).
   This is the paper's central, strongest claim, and it is genuinely surprising: a general-purpose
   time-series foundation model, pretrained on none of this domain's data, rivals models purpose-built
   and trained specifically for it.
2. **That strength is partly, honestly, attributable to task asymmetry** — Chronos-2 receives the
   actual future climate as a known covariate; the baselines do not, by architecture. The paper must
   not hide this; it is the single most important caveat and the source of the paper's most
   interesting reframing: the finding is not "Chronos-2's architecture is better," it is "a
   foundation model that natively consumes known future forcings is a strong practical choice
   whenever such forcings are available" (seasonal forecasts, climate scenarios, what-if analysis).
3. **Robustness is real but not unconditional.** Across 330 LOYO-CV folds spanning 11 years and 3
   very different vegetation regimes, zero-shot Chronos-2 is the second-most dependable method
   (after RF) by both mean rank and top-3 rate. But on the one severe, sustained climate anomaly in
   the dataset (the `evergreen`/2012 drought), it is one of the two *worst* methods of ten — while on
   a different pixel's noisiest, most erratic year, it is the single *best*. The honest reading —
   and the paper's most scientifically interesting nuance — is that Chronos-2 has no general
   "robustness bonus" for anomalous years; its edge comes from normal years, and it fails in the
   specific, identifiable way every model here fails: it has never seen a comparable stress event
   in its evaluation context.
4. **Task-specific adaptation is where the story gets genuinely interesting, not merely negative.**
   Standard LoRA fine-tuning, PEFT variants (6 more methods), and PFT-vegetation-composition
   conditioning (4 architecturally distinct mechanisms, escalating from a single pixel to 70 pooled
   pixels) were all tried, systematically and fairly. **None of it beats zero-shot.** But the paper's
   sharpest, most publishable finding is not that adaptation "failed" — it is the mechanism, proven
   by a randomized-control experiment: a `low_rank` PFT-conditioning head trained on real vegetation
   composition improves 2022 R² by +0.0022 over zero-shot, but the *identical* architecture trained
   on **randomly shuffled, scientifically meaningless PFT assignments** improves by +0.0024 —
   statistically indistinguishable (paired t-test p=0.245, n=70). This is not "we couldn't find a
   working method"; it is direct evidence that *any* small amount of gradient-trained conditioning
   capacity added to an already-strong pretrained model, on data this limited, produces a generic
   nudge independent of what information drives it. That is a much stronger and more general claim
   than "PFT didn't help," and it is corroborated independently by the PEFT sweep (6 diverse
   adaptation mechanisms, 8K–13M parameters, none beat zero-shot either).
5. **Where adaptation *does* transfer cleanly is spatial, not temporal.** A LoRA adapter fit on one
   evergreen-forest pixel deploys, with zero target-specific fine-tuning, at a different evergreen
   pixel 3,700 km away and loses nothing measurable (R²=0.823 vs. 0.819 trained locally) — the best
   spatial generalization of any of 9 methods compared, in sharp contrast to the AELSTM baselines'
   collapse under the same test. Read together with the leakage diagnostic (partial but real
   recovery once a genuinely out-of-distribution year is fit directly, matching mid-pack AELSTM
   performance rather than failing uniquely), the emerging picture is that LoRA-adapted Chronos-2
   weights encode something closer to a *generic seasonal-forecasting adjustment* than a
   location-bound fit — useful evidence for *why* fine-tuning struggles to specialize usefully on
   one short series, while illuminating a different, real strength (spatial portability).

**The throughline**: this is not a "Chronos-2 vs. everything" bake-off. It is a systematic
characterization of one specific, actionable property of general-purpose time-series foundation
models — that their pretrained zero-shot representation is already strong enough that limited-data,
single-domain adaptation struggles to improve it, and can be shown, via a randomized control, to
add noise rather than signal — with vegetation LAI forecasting as the concrete test case.

## C. Recommended title

> **"Zero-Shot Time-Series Foundation Models for Vegetation Forecasting: A Systematic Evaluation of
> Chronos-2 for Leaf Area Index Prediction, Its Robustness, and the Limits of Adaptation"**

Shorter alternative, if length-constrained:

> **"Does Fine-Tuning Help a Strong Pretrained Forecaster? A Chronos-2 Case Study in Vegetation LAI
> Forecasting"**

Both keep Chronos-2 as the explicit subject and foreground the paper's most distinctive
contribution (the adaptation-limits finding) rather than "we compared some models."

## D. Detailed outline (mapped to completed experiments only)

**Title, Abstract**

**1. Introduction**
　1.1 Vegetation LAI forecasting: importance and existing approaches (statistical, ML, deep
　　　sequence models — cite AELSTM-family precedent)
　1.2 The rise of time-series foundation models (TSFMs); Chronos-2's native support for known
　　　future covariates as the specific architectural feature under test
　1.3 Research gap: TSFMs evaluated extensively on generic forecasting benchmarks, rarely on
　　　vegetation/Earth-system tasks with domain covariates and adaptation questions
　1.4 Research questions (RQ1–RQ6, §below)
　1.5 Contributions (§Deliverable J below)

**2. Related Work**
　2.1 Vegetation and LAI forecasting (statistical, ML, LSTM/attention — AELSTM as direct precedent)
　2.2 Classical and deep-learning time-series forecasting
　2.3 Time-series foundation models (Chronos, Chronos-2, TimesFM, Moirai — [CITATION NEEDED] for
　　　each; do not fabricate)
　2.4 Foundation models for environmental / Earth-system applications [CITATION NEEDED]
　2.5 Parameter-efficient adaptation of pretrained models (LoRA and PEFT family; prior evidence on
　　　fine-tuning TSFMs on small data — [CITATION NEEDED where the project's own literature review
　　　in `CHRONOS2_ADVANCED_FINETUNING_REPORT.md` cites real arXiv IDs already found)

**3. Data and Study Design**
　3.1 LAI dataset (HiQ-LAI, 8-day, ~4.6 km, CONUS, 2000–2022)
　3.2 Meteorological covariates (gridMET, 7 variables, temporal alignment convention)
　3.3 Study pixels: 3 primary (contrasting seasonal amplitude/vegetation type) + spatial-transfer
　　　pixel + PFT-ablation pixel + 70-pixel pooled PFT set — Table 1
　3.4 Forecasting formulation: context/target/covariate structure, train/test boundary, LOYO-CV
　　　design and why (fixed rolling window, not classic LOYO or expanding window)

**4. Methods**
　4.1 Chronos-2 architecture (T5-style encoder, patch embedding, InstanceNorm, native covariate
　　　support) — only what's needed to explain later mechanistic findings
　4.2 Zero-shot forecasting setup
　4.3 Baseline models (RF, SVM, LSTM/BiLSTM/GRU/RNN/CNN, AELSTM) — brief, pointers to AELSTM project
　4.4 Parameter adaptation methods: LoRA (original + validated), 6 PEFT methods, PFT-conditioning
　　　architectures (FiLM family + shuffled-PFT control)
　4.5 Evaluation metrics (RMSE, MAE, MAPE, R², Pearson r, ACC for LOYO-CV)

**5. Experimental Design**
　5.1 Single-split (2022) evaluation and fairness (raw-observation rescoring)
　5.2 LOYO-CV design
　5.3 Spatial-transfer design
　5.4 Adaptation search protocols (chronological validation, early stopping, test isolation)
　5.5 The PFT shuffled-assignment control (why it is the decisive experiment, not just another
　　　ablation)

**6. Results**
　6.1 Zero-shot LAI forecasting performance (per-pixel tables, prediction curves)
　6.2 Comparison with supervised baselines (fair-comparison table, rank consistency)
　6.3 Temporal and spatial robustness (LOYO-CV distributions, outlier folds, spatial transfer)
　6.4 Performance across vegetation/LAI regimes (amplitude, predictor sensitivity by pixel)
　6.5 Can adaptation improve Chronos-2? (LoRA original/improved, 6 PEFT methods, PFT-conditioning
　　　+ shuffle control)
　6.6 Failure cases and challenging conditions (2012 drought, low-amplitude noisy year, leakage
　　　diagnostic mechanism)

**7. Discussion** (RESULT / INTERPRETATION / HYPOTHESIS discipline throughout — §Deliverable I)

**8. Limitations** (3-pixel core sample; task asymmetry vs. baselines; CONUS-only; ERA5/global
generalization incomplete; single-pretrained-checkpoint; unseeded fine-tuning stochasticity)

**9. Conclusion**

**Appendix**: claim-evidence verification table (Deliverable I), reproducibility commands (already
documented per-experiment in the repository's own reports).
