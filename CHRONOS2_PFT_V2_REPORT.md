# PFT-v2: An Open Search for a Scientifically Defensible PFT Improvement to Chronos-2

**Goal restated by the user**: not to defend a specific PFT-integration design, but to find *any* effective, reproducible way to use PFT information to improve Chronos-2 LAI forecasting — or to accumulate strong evidence that none exists under the available data, and to identify precisely why.

**Bottom line up front: the evidence supports conclusion B.** Across 4 architecturally distinct conditioning mechanisms, both PFT representations, and a rigorous pre-2022 validation protocol, no method produced an improvement that survives the real-vs-shuffled-PFT control. The one architecture that beat the others on pre-2022 validation (`low_rank`) also improved 2022 R² by +0.0022 over zero-shot — but a model trained identically on **randomly shuffled PFT-to-pixel assignments** improved by +0.0024, statistically indistinguishable from the real-PFT result (paired t-test p=0.245, Wilcoxon p=0.663, 70 pixels). The bottleneck is not PFT representation, injection location, or regularization — it is that **any small amount of gradient-based conditioning capacity added to a near-optimal pretrained model, on this amount of data, produces a small generic effect independent of what information feeds it.**

All outputs in `outputs/pft_v2/` (new; `outputs/pft_multipixel/`, `outputs/pft_ablation/` untouched). Code: `Code/pft_v2_{dataset,model,train,main,analysis}.py`. Full run log: `outputs/pft_v2/experiment_log.md`.

---

## 1. Deep diagnosis of the prior (`pft_multipixel`) failure

Re-inspected the prior experiment's actual search curves (`outputs/pft_multipixel/expA_temporal/*/search_curve.csv`) rather than assuming the earlier explanation was complete. Confirmed: with only 2 rolling training windows, train loss fell steadily (0.354→0.266 at lr=0.01) while validation loss rose steadily (0.355→0.405) from step 0, at every learning rate — real overfitting, not measurement noise. But **this diagnosis alone turned out to be incomplete**, as Stage 1 below shows: expanding to 8 training windows did not fix it for 3 of 4 architectures tested. The dominant explanation that survived evidence is presented in §11.

## 2. Expanded temporal supervision

`pft_v2_dataset.py`: 8 rolling one-year-ahead training windows (2010→2011 … 2017→2018), 3 held-out validation windows (2018→2019, 2019→2020, 2020→2021), never touching 2022 until the single final check. Each training step randomly samples 2 of the 8 windows (stochastic-window SGD, not one fixed full-batch gradient every step) — both to give more effective passes over the expanded window set per unit compute and because pure full-batch repetition on a small fixed set is itself a memorization risk.

## 3–5. Architectures explored

| Architecture | Design | Trainable params | Rationale |
|---|---|---|---|
| `deep_mlp` | Original design: MLP(PFT)→FiLM on target row | 100,544 | Control — same as the prior study, now with 4x more training windows |
| `deep_mlp_reg` | Smaller hidden dim (32) + dropout (0.3) + weight decay (1e-3) | 51,040 | Tests whether regularization alone fixes overfitting |
| `linear_mixture` | **Section 5's proposal, implemented literally**: one learned (γ,β) vector *per PFT class*, linearly combined by the pixel's own fractional weights — `gamma = Σ_c p_c · gamma_c`. A direct, no-hidden-layer implementation of `Response = Σ p_c · response_c(...)` | 15,360 | Biologically structured, maximally interpretable (each class's modulation vector is directly inspectable), much lower capacity |
| `low_rank` | Small MLP → rank-8 bottleneck → linear expansion to (γ,β) | 12,600 | Confines the FiLM vectors to an 8-dimensional subspace of the 768-dim hidden space — a different kind of regularization than dropout/weight-decay (structural, not stochastic) |

All four share the exact injection point established previously (FiLM on the target row's forecast-patch hidden states, immediately before `output_patch_embedding`; base model's 119.5M params completely frozen; zero-initialized conditioner ⇒ byte-identical to pretrained Chronos-2 at init).

**Section 4's proposal (PFT conditions climate representation, not just the readout)** was implemented at the code level (`condition_rows` is decoupled from `is_target_row` in `Chronos2PFTModelV2`, so conditioning all 8 rows of a pixel's group — target + 7 climate covariates — requires no new code) but was **not screened**, for a concrete reason discovered in Stage 1: since even the simplest, lowest-capacity single-row conditioner (`linear_mixture`) showed the identical failure mode as the most expressive one (`deep_mlp`), and since the shuffle control later proved the entire injection mechanism (regardless of architecture) does not carry real information, extending the same non-functional mechanism to more rows was not expected to change the qualitative conclusion, and was not worth the added compute given the evidence in hand. This is flagged explicitly as an idea not exhausted, not one ruled out by direct evidence — see §17.

## 6. Literature consulted

- Perez et al., "FiLM: Visual Reasoning with a General Conditioning Layer" (AAAI 2018) — the FiLM mechanism itself; used here per its original design (feature-wise affine modulation from a side-information encoder).
- "Context Matters: Leveraging Contextual Features for Time Series Forecasting" (arXiv:2410.12672, 2024) — surveys contextual/static-feature conditioning in modern TS forecasters; corroborates that static-covariate integration remains an open, architecture-sensitive problem, consistent with what was found here.
- Attention-enhanced LSTM for continental-scale LAI forecasting (*Int. J. Digital Earth*, 2024, doi:10.1080/17538947.2024.2372317) — directly comparable domain (LAI + climate deep learning), used to sanity-check that the general LAI-forecasting task setup here is reasonable.
- Spatio-Temporal Fusion Mixture-of-Experts (STF-MoE) for heterogeneous agricultural remote sensing (PMC12318938, 2024/2025) — grounded the `linear_mixture` architecture's soft-expert-decomposition framing (fractional PFT weights ≈ soft gating weights over per-class "experts").
- Hu et al., LoRA (ICLR 2022) — grounded the `low_rank` architecture's rank-bottleneck regularization principle, already established as directly relevant to Chronos-2 in this project's own `CHRONOS2_ADVANCED_FINETUNING_REPORT.md`.

No paper described PFT-conditioned Chronos-2 or an exact analog; ideas were adapted, not transplanted wholesale, and evaluated on their own merits via the screening protocol below rather than assumed to work because they're established elsewhere.

## 7–8. Protocol: strict pre-2022 model selection

Screening (architecture, LR, PFT-mode, real-vs-shuffled) used **only** the 3 pre-2022 validation windows. 2022 was evaluated exactly once per finalized method, after every selection decision was already locked in. Fixed seed (42) throughout for reproducibility.

## Stage 1 results: architecture screening (fractional PFT, pre-2022 validation)

| Architecture | n_params | Best val_loss | Best val_R² | Selected LR | Selected step |
|---|---|---|---|---|---|
| deep_mlp | 100,544 | 0.34664 | 0.8323 | 1e-3 | **0** |
| deep_mlp_reg | 51,040 | 0.34667 | 0.8325 | 3e-3 | **0** |
| linear_mixture | 15,360 | 0.34695 | 0.8317 | 1e-3 | **0** |
| **low_rank** | 12,600 | **0.34653** | 0.8321 | 1e-3 | **20** |

Three of four architectures — spanning an 8x range in parameter count, with and without dropout/weight-decay — reproduced the exact same failure mode as the original 2-window study: validation loss lowest at step 0, rising thereafter. **This directly falsifies "too few temporal windows" as a sufficient explanation** — 8 real, distinct year-transitions did not fix it for `deep_mlp`, `deep_mlp_reg`, or `linear_mixture`.

`low_rank` was the exception, selecting step=20. Inspecting its full search curve (`outputs/pft_v2/screen_fractional/low_rank/search_curve.csv`) shows why this should not be over-read: val_loss oscillates noisily in a narrow 0.3465–0.3483 band with no clear monotonic trend in either direction — the step-20 selection looks like it landed on a favorable noise fluctuation from the stochastic 2-window sampling, not a stable, generalizing improvement. This suspicion is confirmed decisively in Stage 3.

## Stage 2: dominant PFT (winning architecture)

val_loss=0.34655, val_R²=0.8321, same selected step (20) — **statistically indistinguishable from fractional's own 0.34653.** No representation-level difference is visible at this training budget.

## Stage 3: the decisive control — real vs. shuffled PFT

Same `low_rank` architecture, same protocol, but PFT fraction vectors **randomly permuted across the 70 pixels** (`pft_v2_dataset.shuffled_pft_table`) before training — breaking the true pixel↔composition link while preserving the marginal distribution of PFT values the model sees.

| | val_loss | val_R² |
|---|---|---|
| Real fractional PFT | 0.34653 | 0.8321 |
| Real dominant PFT | 0.34655 | 0.8321 |
| **Shuffled PFT (control)** | **0.34647** | 0.8321 |

**The shuffled control has the *lowest* validation loss of the three.** This is the single most important number in this study.

## Final, single 2022 evaluation

| Method | Mean R² | ΔR² vs. baseline | Mean RMSE |
|---|---|---|---|
| Baseline (zero-shot, no PFT) | 0.76549 | — | 0.20500 |
| `low_rank` + real fractional PFT | 0.76771 | **+0.00222** | 0.20456 |
| `low_rank` + real dominant PFT | 0.76777 | +0.00228 | 0.20455 |
| `low_rank` + **shuffled PFT (control)** | **0.76788** | **+0.00239** | 0.20465 |

All three PFT-conditioned variants beat zero-shot by a similar small margin — **including the one with scientifically meaningless input.** The shuffled control's improvement is numerically the largest of the three.

**Paired statistical test, real-fractional vs. shuffled, per-pixel R² (n=70)**: mean difference = −0.00017 (real is marginally *lower*), paired t-test p=0.245, Wilcoxon signed-rank p=0.663. 31/70 pixels favor real PFT, 39/70 favor shuffled — a coin flip. **No statistically detectable difference.**

## 9. Fractional vs. dominant PFT

No detectable difference at any stage (validation or test): 0.34653 vs. 0.34655 (validation), 0.76771 vs. 0.76777 (test 2022). With this little real training signal surviving validation, there isn't enough of a genuine PFT-driven effect for the fractional-vs-dominant distinction to matter — consistent with the single-pixel study's finding (`CHRONOS2_PFT_ABLATION_REPORT.md`) that fractional never showed a reproducible edge over dominant.

## 10. Is PFT actually being used? — direct answer

**No.** The shuffle control is unambiguous: a model trained on garbage PFT assignments performs the same as (numerically, marginally better than) one trained on real PFT assignments, on both pre-2022 validation and the final 2022 test.

Perturbation sensitivity on the **finalized** (`low_rank`, real fractional, 21-step) model, holding real climate/LAI context fixed and sweeping 5 synthetic forest/grass compositions:

| Pixel | Max |Δprediction| |
|---|---|
| evergreen | 0.0048 |
| mixed_forest_grass | 0.0131 |
| low_amplitude | 0.0004 |

These are tiny compared to the smoke test's 0.43–0.63 (an intentionally over-trained, non-validated checkpoint from the prior study) — consistent with the finalized model having received only 21 real gradient steps, and consistent with that residual sensitivity carrying no real information per the shuffle control.

## 11. Mixed vs. pure pixel analysis

Correlation between PFT entropy and ΔR²(fractional vs. baseline): **+0.157** (weak). Correlation between PFT entropy and ΔR²(fractional vs. **shuffled**): **−0.133** (weak, opposite sign). Neither is a meaningful, direction-consistent relationship — see `mixed_vs_pure_final.png`: the "vs. shuffled" deltas cluster tightly around zero across the *entire* entropy range, with no visible dependence on how mixed a pixel's composition is. If fractional PFT carried genuine, decomposable per-class information, mixed pixels (high entropy) should show a *larger* real-vs-shuffled gap than pure pixels — they do not.

## 12. Seasonal-phase breakdown

Mean RMSE by phenological phase (green-up Mar–May, peak Jun–Aug, senescence Sep–Nov, dormant Dec–Feb), real-fractional vs. shuffled:

| Phase | Fractional | Shuffled |
|---|---|---|
| dormant | 0.13213 | 0.13216 |
| green_up | 0.17294 | 0.17284 |
| peak | 0.24358 | 0.24360 |
| senescence | 0.20023 | 0.20049 |

Indistinguishable in every phase, including green-up and senescence — the phenological transitions where a genuine vegetation-composition-dependent response would most plausibly show up first.

## 13. By dominant PFT class

| Dominant PFT | n | Mean ΔR²(fractional−baseline) | Mean ΔR²(fractional−shuffled) |
|---|---|---|---|
| SHRUBS_ND | 6 | +0.0052 | −0.0003 |
| GRASS_NAT | 19 | +0.0041 | −0.0004 |
| SHRUBS_BD | 7 | +0.0035 | −0.0010 |
| TREES_BD | 7 | +0.0013 | +0.0003 |
| TREES_NE | 6 | +0.0009 | +0.0002 |
| GRASS_MAN | 12 | +0.0005 | −0.00000 |
| TREES_ND | 6 | +0.0003 | +0.0002 |
| SHRUBS_NE | 7 | −0.00005 | +0.0001 |

The vs.-baseline column shows apparent variation across classes (SHRUBS_ND highest, SHRUBS_NE ~0), but the vs.-shuffled column — the fair comparison — is uniformly tiny (|Δ| ≤ 0.001) for every class, with no class showing a real, shuffle-surviving benefit. The apparent per-class pattern in the baseline comparison is not attributable to vegetation type.

## 14. Overfitting analysis

`deep_mlp`/`deep_mlp_reg`/`linear_mixture` overfit within the first training step regardless of capacity (100K→15K params) or regularization (dropout, weight decay). `low_rank`'s structural rank-8 bottleneck delayed the onset by ~20 steps, but the shuffle control shows this delay does not correspond to learning anything real — it more plausibly reflects the rank-8 subspace constraint acting as noise-averaging insurance against the worst of what constant full-capacity FiLM does, independent of input content.

## 15. Trainable parameters & compute cost

100,544 (deep_mlp) down to 12,600 (low_rank) new parameters, 0.008–0.084% of the 119.5M-parameter base model, which stayed completely frozen throughout. Total compute: 4 architectures × 2 LRs × 200 search steps + dominant + shuffled screens + 3 final refits (21–400 steps) + final 2022 eval, all on 70 pooled pixels (560 rows/window) — under 2 hours on a single A100 (interrupted once mid-run by an environment teardown; resumed cleanly via per-stage checkpointing without repeating completed work — see `pft_v2_main.py`).

## 16. Limitations

- Screening covered 4 architectures and 2 learning rates each — not exhaustive. Section 4's "condition climate rows too" and cross-attention/MoE-gating variants were reasoned about but not run (§5 above explains why, given the shuffle-control evidence obtained from cheaper variants first).
- The rolling-window protocol still only spans 2010–2021 (11 total pre-2022 transitions) — a genuinely larger multi-decade or multi-region dataset was not available here.
- The `low_rank` architecture's apparent (if spurious) edge might behave differently with a larger validation window count or repeated-seed averaging; this was not explored further once the shuffle control settled the question.
- All findings are specific to LAI forecasting with Chronos-2 on this pixel set; they should not be read as a general claim about PFT's value in vegetation modeling broadly (see corroborating LAI-LSTM literature in §6, which does find climate-vegetation deep-learning value under different architectures/data regimes).

## 17. Scientific interpretation & recommended next step

**PFT information, as currently made available to Chronos-2 through any FiLM-family conditioning mechanism tested here, does not produce a real, reproducible improvement in LAI forecasting.** This corroborates and extends two independent findings already established in this project:

1. `CHRONOS2_PFT_ABLATION_REPORT.md`: a single-pixel constant PFT covariate is architecturally erased by InstanceNorm.
2. `CHRONOS2_ADVANCED_FINETUNING_REPORT.md`: **no** PEFT method (LoRA, DoRA, VeRA, IA3, LN-Tuning, BitFit, partial fine-tuning) beat zero-shot Chronos-2 on this same small-data LAI task — a finding entirely independent of PFT.

Combined with this study's result — that *even scientifically meaningless (shuffled) side information* produces the same small improvement as real PFT — the most parsimonious explanation is not "PFT lacks a good architecture" but **"pretrained zero-shot Chronos-2 is already close to this dataset's achievable ceiling, and any small amount of added, gradient-trained conditioning capacity nudges predictions by a similar, generic amount regardless of what information drives it."** The bottleneck is the interaction between dataset scale and fine-tuning generally, not PFT specifically.

**Recommended next steps, in order of promise:**
1. **Do not pursue further FiLM/adapter-style PFT conditioning of Chronos-2 on this dataset** — the shuffle control is strong, direct evidence against it, not merely an inconclusive negative result.
2. **Test PFT as a *training-time-only* signal** in a non-Chronos-2 architecture better suited to small data with structured side information (e.g., the `linear_mixture` idea implemented as a lightweight standalone model, or the 8 AELSTM-family models from the single-pixel study, which showed more genuine — if noisy — sensitivity to PFT than Chronos-2 ever did).
3. **If returning to Chronos-2**, the highest-value next experiment is not a new architecture but a **much larger pixel/region set or longer temporal record** — the diagnosis here rules out "wrong conditioning mechanism" with reasonable confidence, leaving "not enough independent supervision to move a near-optimal pretrained model" as the standing hypothesis, which only more (or more informative) data can test.

## Files

- `Code/pft_v2_{dataset,model,train,main,analysis}.py`
- `outputs/pft_v2/experiment_log.md` — full run log
- `outputs/pft_v2/architecture_screen_summary.csv`, `screen_{fractional,dominant,shuffled}/*/search_curve.csv`
- `outputs/pft_v2/final_{baseline,fractional,dominant,shuffled}/` — refit checkpoints, per-pixel predictions, metrics
- `outputs/pft_v2/final_2022_summary.csv`, `per_pixel_final_comparison.csv`, `real_vs_shuffled_ttest.csv`
- `outputs/pft_v2/mixed_vs_pure_final.{csv,png}`, `by_dominant_pft_final.csv`, `seasonal_phase_rmse.csv`
- `outputs/pft_v2/perturbation_sensitivity_final.csv`
