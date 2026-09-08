# Zero-Shot Time-Series Foundation Models for Vegetation Forecasting: A Systematic Evaluation of Chronos-2 for Leaf Area Index Prediction, Its Robustness, and the Limits of Adaptation

*Deliverable E — Full Manuscript Draft*

## Abstract

Leaf Area Index (LAI) is a fundamental variable in land–atmosphere modeling, agricultural
monitoring, and drought assessment, and forecasting it typically requires purpose-built statistical
or deep-learning models trained on years of location-specific data. We ask whether a
general-purpose, pretrained time-series foundation model (TSFM) — Amazon's Chronos-2 — can forecast
LAI competitively **without any task-specific training**, and what its zero-shot use reveals about
robustness, generalization, and the value of subsequent adaptation. Using LAI and meteorological
covariates for U.S. vegetation pixels spanning grassland, deciduous, and evergreen-forest regimes,
we compare zero-shot Chronos-2 against eight supervised baselines (Random Forest, SVM, and five
recurrent/convolutional deep-learning architectures, including the domain-specific AELSTM model),
evaluate robustness across eleven held-out years (330 fold results), test spatial generalization
across a 3,700 km transfer, and systematically probe whether task-specific adaptation — standard
and advanced parameter-efficient fine-tuning (7 methods total), and four architecturally distinct
vegetation-composition-conditioning mechanisms — can improve on the pretrained baseline. Zero-shot
Chronos-2 is the best or statistically tied-best model on the majority of pixels tested (mean rank
1.33 of 10 on a single held-out year; 3.70 of 10, second only to Random Forest, across all
LOYO-CV folds) and generalizes across a 3,700 km spatial transfer with no measurable loss. However,
no adaptation method — seven distinct parameter-efficient fine-tuning variants, or four
vegetation-composition-conditioning architectures — improves consistently on the pretrained model;
a decisive randomized control shows that a conditioning head trained on genuine vegetation
composition performs statistically indistinguishably from one trained on randomly shuffled,
scientifically meaningless assignments (paired t-test p=0.245, n=70). We interpret this pattern of
evidence — strong, robust zero-shot transfer alongside adaptation that adds noise rather than
signal — as evidence that Chronos-2's pretrained representation is already close to this dataset's
achievable ceiling, with direct implications for how general-purpose TSFMs should be deployed in
data-limited Earth-system applications: as strong zero-shot forecasters first, with adaptation
reserved for regimes where genuinely larger or more diverse target-domain data are available.

## 1. Introduction

### 1.1 Vegetation and LAI forecasting

Leaf Area Index — the one-sided area of leaf tissue per unit ground area — is a primary control on
canopy photosynthesis, evapotranspiration, and land–atmosphere energy exchange, and is a standard
input to crop-yield, drought, and land-surface models. Forecasting LAI ahead of a growing season, or
under alternative climate scenarios, has historically relied on statistical regression, tree-based
ensembles (Random Forest, [CITATION NEEDED]), and increasingly recurrent or attention-augmented
deep-learning architectures trained from scratch per location [CITATION NEEDED]. This project
builds directly on one such purpose-built architecture, AELSTM, evaluated on the same pixels and
covariates used here.

### 1.2 The rise of time-series foundation models

Time-series foundation models (TSFMs) — large sequence models pretrained on broad, cross-domain
time-series corpora and applied zero-shot to new series — have recently shown strong generic
forecasting performance without domain-specific training [CITATION NEEDED]. Chronos-2 (Amazon,
2025) is distinguished among these by native, first-class support for **known future covariates**:
rather than only extrapolating a univariate history, it can condition a forecast on covariates whose
future values are already known — precisely the structure of a vegetation forecast made with actual
(observed, or scenario) future weather.

### 1.3 Research gap

TSFMs are extensively benchmarked on generic forecasting suites, but rarely evaluated on
Earth-system or vegetation-specific tasks where (a) covariates carry a known, physically meaningful
future trajectory, (b) target-domain training data is often limited to a handful of locations and
years, and (c) the practical question is not "can this model forecast at all" but "does adapting
it to this domain help, or does its pretrained representation already suffice." This gap motivates
using Chronos-2 as a concrete test case for vegetation LAI forecasting.

### 1.4 Research questions

- **RQ1.** How well does pretrained Chronos-2 perform in zero-shot LAI forecasting?
- **RQ2.** How does its performance compare with conventional supervised ML and deep-learning
  baselines trained specifically for this task?
- **RQ3.** How robust is Chronos-2 across different years, vegetation regimes, and locations?
- **RQ4.** Under what conditions does it perform particularly well or poorly?
- **RQ5.** Does task-specific parameter adaptation improve Chronos-2 beyond its pretrained zero-shot
  capability?
- **RQ6.** What do these experiments imply for applying general-purpose TSFMs to vegetation
  forecasting?

### 1.5 Contributions

1. We provide a systematic evaluation of Chronos-2 for vegetation LAI forecasting under zero-shot
   application, benchmarked fairly (raw-observation rescoring) against eight supervised baselines
   across three vegetation regimes and 330 leave-one-year-out cross-validation folds.
2. We characterize Chronos-2's robustness and generalization behavior — temporal (across 11 years),
   spatial (a 3,700 km transfer test), and failure-mode-specific (a controlled leakage diagnostic
   isolating distribution shift from representational limitation).
3. We conduct the most extensive adaptation study of Chronos-2 for a domain task to date within
   this project — seven parameter-efficient fine-tuning methods and four vegetation-composition
   conditioning architectures, including a randomized shuffled-assignment control — and show that
   none consistently improves on the pretrained zero-shot representation, identifying the mechanism
   (generic capacity-driven noise, not method-specific failure) rather than merely reporting the
   negative result.

## 2. Related Work

### 2.1 Vegetation and LAI forecasting
[CITATION NEEDED — statistical/RS-based LAI estimation and forecasting literature; AELSTM as the
direct architectural precedent for this project's baselines.]

### 2.2 Time-series forecasting
[CITATION NEEDED — classical statistical methods, tree ensembles, and deep sequence architectures
(LSTM/BiLSTM/GRU/CNN/attention) as used for the baseline suite here.]

### 2.3 Time-series foundation models
Chronos and Chronos-2 (Ansari et al., Amazon) are pretrained, general-purpose forecasters; Chronos-2
adds native known-future-covariate support, the specific capability exercised throughout this
paper's task formulation. [CITATION NEEDED for TimesFM, Moirai, and other contemporary TSFMs, for
completeness of the related-work landscape — not otherwise used in this project's experiments.]

### 2.4 Foundation models for environmental / Earth-system applications
[CITATION NEEDED — this project did not conduct a literature review specific to Earth-system
foundation models; the research gap in §1.3 is stated on the basis of this project's own search,
not a systematic survey, and should be qualified as such in the final manuscript.]

### 2.5 Parameter-efficient adaptation
LoRA (Hu et al., ICLR 2022) is the standard parameter-efficient fine-tuning (PEFT) baseline used
throughout. This project's own literature review (`CHRONOS2_ADVANCED_FINETUNING_REPORT.md`)
additionally evaluated DoRA (Liu et al., ICML 2024), VeRA (Kopiczko et al., ICLR 2024), IA3 (Liu et
al., NeurIPS 2022), LN-Tuning (as applied to Chronos in a small-data healthcare task, arXiv
2409.11302), and BitFit (Zaken et al., ACL 2022), cross-checked directly against the installed
Chronos-2 and `peft==0.17.1` source for architectural compatibility rather than assumed from the
papers alone. Independent, directly relevant prior evidence — arXiv 2607.23146, evaluating
Chronos-2 itself, found zero-shot beats fine-tuning on small datasets, and full fine-tuning
"unreliable... consistently degrading performance"; arXiv 2409.11302 found lighter PEFT methods can
match or beat LoRA on Chronos under scarce-data conditions — both point in the same direction this
paper's own results independently confirm (§6.5).

## 3. Data and Study Design

### 3.1 LAI dataset
HiQ-LAI, 8-day composite, ~1/24° (~4.6 km) native grid, continental United States, 2000–2022.

### 3.2 Meteorological covariates
Seven daily gridMET variables — maximum/minimum temperature (`tmmx`/`tmmn`), precipitation (`pr`),
downward shortwave radiation (`srad`), vapor pressure deficit (`vpd`), specific humidity (`sph`),
and wind speed (`vs`) — aligned to each LAI composite's 8-day window by mean, matching the
sibling AELSTM project's established convention exactly.

### 3.3 Study locations

**Table 1** (see `03_tables.tex`) summarizes the primary study pixels. Three pixels, selected by
seasonal-LAI characteristics alone (never by model performance, per the pixel-selection
methodology inherited from the AELSTM project) anchor the core comparison: `low_amplitude`
(37.53°N, 117.56°W; 84% natural grassland; smallest normalized seasonal amplitude, 0.57), `high_
amplitude_deciduous` (36.23°N, 84.48°W; 89% broadleaf deciduous forest; largest amplitude among
deciduous pixels, 1.73), and `evergreen` (30.53°N, 82.43°W; 95% needleleaf evergreen forest;
flattest evergreen-like seasonal cycle, 0.63). Two additional pixels support specific
generalization tests: `evergreen_west` (Klamath Mountains, N. California/S. Oregon border, ~3,700
km from `evergreen`, same vegetation type — spatial transfer target) and `mixed_forest_grass` (IL,
50% broadleaf-deciduous forest / 50% natural grassland — PFT ablation companion pixel). A 70-pixel
pooled set, farthest-point-sampled across a 10-class PFT-composition space with a geographic
minimum-separation constraint (8 dominant vegetation classes, 9 U.S. regions, composition purity
0.46–1.00), supports the multi-pixel PFT-conditioning experiments. Three further pixels
(`cropland_managed`, `grassland_shrubland`, `strong_interannual_variability`) were selected by the
same methodology but **have not been run through Chronos-2** — an explicit limitation (§8).

### 3.4 Forecasting formulation

For the primary task, Chronos-2 is given historical LAI (2000–2021, ~1,002 8-day steps) as
`target`, the same-period climate as `past_covariates`, and the **actual observed** 2022 climate as
`future_covariates`, forecasting all 45 steps of 2022 in a single direct (non-autoregressive) call
— well within Chronos-2's native 1,024-step direct-forecasting horizon. This is a deliberately
different task from the AELSTM baselines, which predict LAI from past climate alone; the
implications of this asymmetry are addressed directly in §6.2 and §8. Leave-one-year-out
cross-validation (LOYO-CV) extends this to 11 held-out years (2012–2022) using a **fixed 12-year
rolling training window** immediately preceding each held-out year — not classic all-other-years
LOYO (which would leak future years into a forecaster) and not an expanding window (which would
confound "difficult year" with "how much training data this fold happened to receive").

## 4. Methods

### 4.1 Chronos-2
Chronos-2 is a pretrained, T5-style encoder-only patch-transformer (12 blocks,
119.5M parameters) that stacks a target series and its covariates into a shared representation,
normalizes each series independently by its own per-series statistics (InstanceNorm) before
patch-embedding, and produces a direct multi-step forecast. This normalization detail is not
incidental — it is the direct mechanistic cause of one of this paper's architectural findings
(§6.5, §6.6): a covariate that is *constant* across the context and forecast window has zero
variance, and Chronos-2's InstanceNorm replaces a zero standard deviation with a small epsilon,
erasing the covariate's value to exactly zero regardless of its content.

### 4.2 Zero-shot forecasting setup
No trainable weights; the pretrained checkpoint is applied directly with the input structure of
§3.4. Kept identical across every experiment in this paper as the reference condition.

### 4.3 Baseline models
Eight models from the sibling AELSTM project, each trained from scratch per pixel on **past
climate only** (no future covariates): Random Forest, SVM, and five neural sequence
architectures (RNN, LSTM, BiLSTM, GRU, CNN), plus AELSTM itself, an attention-augmented LSTM
architecture purpose-built for this task. All are rescored against the same raw, unsmoothed LAI
observations Chronos-2 is evaluated against, correcting for the fact that the AELSTM project's own
pipeline reports metrics against a Savitzky–Golay-smoothed target.

### 4.4 Parameter adaptation methods
**LoRA** (original: `lr=1e-4`, rank 8/α16, fixed 1,000 steps, no validation; improved: chronological
validation, 6-config search over `lr∈{1e-5,1e-4}×rank∈{4,8,16}`, early stopping, two-stage refit).
**Six additional PEFT methods** (DoRA, VeRA, IA3, LN-Tuning, BitFit, partial last-transformer-block
fine-tuning), implemented via a generalized fit wrapper (`advanced_finetuning_core.py`) that
replicates Chronos-2's public `fit()` internals but accepts any `peft.PeftConfig`, under an
identical validated protocol and an equal-sized 4-config search budget per method. **PFT-composition
conditioning**: a FiLM-style side-input head (vegetation-composition encoder → feature-wise affine
modulation of the target row's forecast hidden states, base model frozen), tested in four
architecturally distinct forms — a deep MLP head (100,544 params), a regularized/smaller variant,
a biologically-structured linear mixture of per-class response vectors, and a rank-8-bottleneck
variant — plus the decisive control of training the same architecture on randomly shuffled
PFT-to-pixel assignments.

### 4.5 Evaluation metrics
RMSE, MAE, MAPE (computed only over rows where both true and predicted values are positive,
matching the AELSTM project's convention), R², and Pearson r; LOYO-CV additionally reports an
anomaly correlation coefficient (ACC) against a per-fold day-of-year climatology built only from
that fold's own training years.

## 5. Experimental Design

### 5.1 Single-split evaluation and fairness
Every baseline is rescored against raw (unsmoothed) LAI observations before any cross-model
comparison; the naive, smoothed-target comparison is retained in the repository only to show what
the baseline project's own pipeline reports internally, and is explicitly excluded from this
paper's evidence.

### 5.2 LOYO-CV design
330 fold results (3 pixels × 11 years × 10 methods), each scored against raw observed LAI, using
the fixed rolling-window design of §3.4.

### 5.3 Spatial-transfer design
A single LoRA adapter, fit once on `evergreen`'s full 2000–2022 series, is evaluated **unmodified**
at `evergreen_west` using that pixel's own context and real 2022 climate — a legitimate
generalization test (the target pixel's data never participates in fitting), contrasted with the
same adapter's performance at its own source pixel and with a separately-fit target-local adapter.

### 5.4 Adaptation search protocols
Every adaptation method in this paper (LoRA-improved, all 6 additional PEFT methods, all 4
PFT-conditioning architectures) uses the same discipline: model/hyperparameter/checkpoint selection
is driven **only** by a chronological validation split carved from pre-2022 data; the 2022 test
year is evaluated exactly once, after every selection decision is locked in.

### 5.5 The PFT shuffled-assignment control
The decisive PFT experiment retrains the best-performing conditioning architecture (`low_rank`)
identically, except with vegetation-composition vectors randomly permuted across the 70 pixels
before training — breaking the true pixel↔composition link while preserving the marginal
distribution of PFT values the model sees. If real PFT provides genuine information, the real
condition should measurably outperform the shuffled one on the same, otherwise-untouched
validation and test protocol; if not, this is a randomized negative control, not merely an
additional ablation arm.

## 6. Results

### 6.1 Zero-shot LAI forecasting performance

Zero-shot Chronos-2 achieves R² = 0.542 (`low_amplitude`), R² = 0.965
(`high_amplitude_deciduous`), and R² = 0.832 (`evergreen`) on the 2022 held-out year — the best or
statistically tied-best of all 10 methods compared at every one of the 3 pixels (Table 2).

> **RESULT**: zero-shot Chronos-2 ranks 1st on 2 of 3 pixels and is separated from the best method
> by 0.00003 R² on the third.
> **INTERPRETATION**: a pretrained, general-purpose time-series representation transfers to LAI
> forecasting without any task-specific training.
> **HYPOTHESIS**: broad pretraining on diverse time series may encode generic seasonal/periodic
> structure that is also present, and exploitable, in vegetation phenology — this has not been
> demonstrated directly here and remains a hypothesis, not a result.

### 6.2 Comparison with supervised baselines

Table 2 gives the full per-pixel ranking. Across the 3 shared pixels, zero-shot Chronos-2 has the
lowest (best) and most consistent mean rank of any method (1.33, std 0.58); the published AELSTM
architecture itself never places better than 8th of 10 at any pixel.

**This advantage is not evidence of purely architectural superiority.** Chronos-2 is given the
actual future climate as a known covariate; none of the eight baselines have a mechanism to use
this information at all, by design — they forecast from past climate only. The single largest
identifiable contributor to Chronos-2's advantage is this task asymmetry, not an implicit claim
that Chronos-2 "predicts LAI better from the same information," because it does not receive the
same information. What remains genuinely notable, and defensible independent of the covariate
asymmetry, is that a **zero-shot, untrained** model is competitive at all against eight specialized
models each trained from scratch on the target pixel.

> **RESULT**: zero-shot Chronos-2 is the best or tied-best model on 3/3 tested pixels, with future
> climate as an input the baselines lack.
> **INTERPRETATION**: when reliable future meteorological forcing is available (seasonal forecasts,
> scenario analysis), a foundation model with native covariate support is a strong practical choice
> — a claim about deployment usefulness under a specific information regime, not a head-to-head
> architecture verdict.

### 6.3 Temporal and spatial robustness

Across all 330 LOYO-CV folds (Table 3), zero-shot Chronos-2 has the second-lowest mean rank (3.70
of 10, behind only Random Forest's 3.39) but the single highest top-3 finish rate of any method
(21/33 = 64%, vs. RF's 20/33 = 61%) — the two lowest-mean-rank methods in the entire study. Two
folds are severe, genuine outliers (z < −2.8 on a per-pixel-normalized difficulty
score): `evergreen`/2012 (a real, sustained 2011–2012 U.S. Southeast drought, unlike anything in
2000–2011 training data) and `low_amplitude`/2018 (not a climate anomaly — an erratic, low-signal
LAI trajectory at an already-low-amplitude pixel). On the drought fold, both Chronos-2 variants
rank 9th and 10th (worst) of 10; on the noisy fold, zero-shot ranks 1st. No single year is difficult
at more than one pixel simultaneously.

> **RESULT**: Chronos-2 is the two worst-of-ten methods on the one severe climate-anomaly fold in
> this dataset, and the single best method on a different, non-anomalous but noisy fold.
> **INTERPRETATION**: Chronos-2 has no general "robustness bonus" to anomalous years; its overall
> edge over the baseline family comes from typical years, not special resilience to distribution
> shift.
> **HYPOTHESIS**: models with more explicit within-training exposure to anomaly-adjacent dynamics
> (e.g. SVM, which degrades most gracefully on the drought fold) may encode features less reliant
> on a "normal seasonal cycle" prior — untested directly here.

Spatially, a single LoRA adapter fit on `evergreen` and deployed **without retraining** at
`evergreen_west` (~3,700 km away, same vegetation type) achieves R² = 0.823, fractionally exceeding
a separately-fit target-local adapter (R² = 0.819) — the best spatial generalization of any of 9
methods compared, against AELSTM's own collapse to negative R² under the identical test.

### 6.4 Performance across vegetation and LAI regimes

Performance is strongly pixel-dependent: R² spans roughly 0.5 (`low_amplitude`, a sparse,
low-signal grassland pixel) to 0.97 (`high_amplitude_deciduous`, a strong, high-amplitude seasonal
cycle) for essentially every method tested, including Chronos-2 — a far larger range than the
spread between methods at any single pixel (§6.5 confirms this holds under adaptation too).
Predictor-sensitivity analysis (zero-shot Chronos-2 among 9 methods) finds `srad` (downward
shortwave radiation) the only predictor whose removal consistently hurts at every pixel; temperature
importance is almost entirely pixel-specific (critical at `low_amplitude`, unimportant-to-mildly-
helpful-when-removed elsewhere); and a leaner 5-predictor set (dropping `vs`, `pr`) improves mean R²
at all 3 pixels simultaneously, a validated actionable finding independent of which forecasting
model is used.

### 6.5 Can parameter adaptation improve Chronos-2?

**No adaptation method tested in this project consistently beats zero-shot Chronos-2.** Table 4
summarizes. Original (unvalidated) LoRA fine-tuning is uniformly worse (ΔR² = −0.163, −0.014,
−0.120 across the 3 pixels). Adding validation-based checkpoint selection recovers most, but not
all, of this gap on the two pixels where it was worst (`low_amplitude`: −0.042 remaining;
`evergreen`: −0.003, effectively closed) without ever crossing zero-shot outright. Extending to six
further PEFT methods spanning a 1,500-fold range of trainable-parameter count (8,352 to
13,093,536) — additive low-rank (DoRA), multiplicative rescaling (IA3), bias-only (BitFit),
normalization-only (LN-Tuning), shared-random-projection (VeRA), and full-weight partial fine-tuning
— finds the same pattern: mean R² across all 9 fine-tuning variants (7 PEFT methods × pixel-mean,
plus the two LoRA variants) is uniformly below zero-shot's 0.780, and only one method/pixel
combination (DoRA on `evergreen`, +0.0026) beats zero-shot at all, by a margin plausibly
attributable to noise. Trainable-parameter count is, at best, a weak and inconsistent predictor of
outcome (pooled r = +0.10 with test R²; the sign of the correlation even flips between pixels).

The vegetation-composition-conditioning experiments extend this finding with a mechanistic
explanation rather than merely replicating it. A single-pixel, constant PFT covariate is
**architecturally provably erased** by Chronos-2's per-series InstanceNorm — confirmed by direct
source inspection and an exact, 8-decimal-place-zero empirical perturbation test. Fixing this with a
FiLM-conditioning head genuinely capable of learning a PFT-dependent response (verified via a smoke
test and a deliberately-overfit checkpoint that shows large, physically plausible sensitivity, up to
0.63 LAI units) still fails to produce a validated improvement: across four architecturally distinct
conditioning designs — spanning an 8× range in trainable parameters, with and without dropout and
weight decay — three of four overfit within the first training step even given 8 rolling training
windows (4× more temporal supervision than the initial 2-window design). The fourth (`low_rank`,
a rank-8-bottleneck design) is the only architecture that trains past step 0 — and the paper's
decisive result is that an identical `low_rank` head trained on **randomly shuffled** PFT-to-pixel
assignments improves 2022 R² by +0.0024, marginally *more* than the real-PFT condition's +0.0022,
with no statistically detectable difference between them (paired t-test p=0.245, Wilcoxon p=0.663,
n=70 pixels; 31/70 pixels favor real PFT, 39/70 favor shuffled). Neither seasonal-phase breakdown
nor mixed-vs-pure-pixel entropy analysis reveals any shuffle-surviving signal.

> **RESULT**: seven distinct parameter-efficient fine-tuning methods and four vegetation-composition-
> conditioning architectures were tested under a validated, test-isolated protocol; none
> consistently beats zero-shot Chronos-2, and a randomized shuffled-assignment control shows the
> one architecture that does train past initialization derives no detectable benefit from real
> vegetation-composition information over scientifically meaningless input.
> **INTERPRETATION**: this is not evidence that any single adaptation method or covariate design was
> chosen poorly — the shuffle control specifically rules out "wrong information, right mechanism" as
> the explanation. Task-specific adaptation did not consistently improve upon the zero-shot model,
> highlighting the strength of the pretrained representation and the difficulty of improving a
> strong foundation-model baseline with limited target-domain data.
> **HYPOTHESIS**: pretrained zero-shot Chronos-2 may already sit close to this dataset's achievable
> ceiling; any small amount of gradient-trained conditioning capacity added on top, on data this
> limited, may nudge predictions by a similarly-sized, generic amount regardless of what
> information drives it — a hypothesis directly motivated by, but not fully proven beyond, the
> shuffle-control result and the PEFT sweep's parameter-count-independence finding taken together.

### 6.6 Failure cases and challenging environmental conditions

The `evergreen`/2012 LOYO-CV failure (zero-shot R² = −7.64; original LoRA R² = −8.29, the single
worst score of all 9 methods compared this way) is mechanistically resolved by the leakage
diagnostic: allowing 2012 to participate in LoRA fitting (a deliberate leakage condition, **not** a
valid evaluation) recovers RMSE by 59.9% and R² to −0.50 — the second-largest recovery of 9 methods
tested this way (behind only Random Forest, +8.01), landing squarely in the middle of the baseline
pack rather than uniquely bad. Both the recovering and the original failure are large and consistent
across essentially every architecture tested (tree ensemble, six neural sequence models, and a large
pretrained transformer), which is the signature of a shared external cause — the 2012 drought being
genuinely unlike anything in 2000–2011 training data — rather than an architecture-specific
representational limitation.

## 7. Discussion

**Why might Chronos-2 transfer successfully to LAI?** Vegetation phenology is strongly seasonal and
climate-driven, structurally similar to many series in a broad pretraining corpus; Chronos-2's
native handling of known future covariates directly matches this paper's forecasting formulation.
The strong zero-shot baseline (§6.1–6.2) suggests pretrained time-series representations can
transfer effectively to this domain without modification — a result consistent with, and extending
to a new domain, prior evidence that Chronos-2 zero-shot performance is strong relative to
fine-tuning on small datasets (arXiv 2607.23146).

**What does strong zero-shot performance imply, and what doesn't it imply?** It implies that, for
practitioners with access to reliable future meteorological forcing, a general-purpose TSFM is a
credible default without investing in a purpose-built architecture or a target-domain training
pipeline. It does not imply Chronos-2's architecture is intrinsically superior at sequence modeling
in general — this project's comparison is not same-task (§6.2), and the baselines' collapse under
spatial transfer (in sharp contrast to Chronos-2's success, §6.3) suggests at least some of them
were fitting genuinely useful, if non-transferable, location-specific structure that a
covariate-blind pure zero-shot comparison cannot credit them for.

**When do supervised models retain advantages?** Random Forest is the single most consistent
performer across the entire LOYO-CV study (lowest rank volatility, comparable mean rank to
Chronos-2) and degrades most gracefully of all 10 methods on the one severe drought fold — evidence
that a simple, well-regularized supervised model trained directly on the target series retains real
advantages in anomalous conditions a pretrained zero-shot model has not encountered.

**Why might fine-tuning fail to improve a strong pretrained model, here specifically?** Three lines
of evidence converge: (1) each fine-tuning run adapts on a single, short (~1,000-point) series — the
scenario Chronos-2's own documentation identifies as a regime where fine-tuning "may not improve
over zero-shot (and may even worsen accuracy sometimes)"; (2) trainable-parameter count is a weak,
inconsistent predictor of outcome across a 1,500× range, arguing against "insufficient capacity" as
the explanation; (3) the PFT shuffle control directly demonstrates that added conditioning capacity
produces a similar effect size whether or not it carries real information, which is difficult to
reconcile with any story in which the *specific* information being added is the limiting factor.
Together, these support the hypothesis that the binding constraint is the **combination** of a
strong pretrained prior and a small amount of target-domain data, not any one adaptation method's
design.

**What environmental regimes remain difficult?** Sustained, multi-month anomalies genuinely absent
from a model's training window (§6.6) remain hard for every method tested, Chronos-2 included, and
Chronos-2 shows no special resistance to this specific failure mode — an important tempering of the
paper's otherwise favorable robustness story (§6.3).

**Implications for future vegetation foundation-model research.** The clearest actionable
implication is methodological: any future claim that an adaptation or conditioning method improves
a strong pretrained forecaster on limited data should be checked against a randomized-assignment
control before being reported as a positive result — this project's own PFT-multipixel experiment
(Experiment 8) would have been reported as a promising, if inconclusive, positive direction without
the shuffle control that Experiment 9 added, and that control reversed the reading entirely.

## 8. Limitations

- **Small core sample.** The primary cross-model comparison rests on 3 pixels; rank volatility
  among several baselines (e.g., GRU swinging from rank 2 to rank 10) is a direct warning that
  single-digit-pixel-count rankings, including "Chronos-2 is best," could shift with more locations.
  Three additional pre-selected pixels exist but have not been run through Chronos-2 (§Deliverable H).
- **Task asymmetry.** Chronos-2's headline comparison against the baselines is not same-information;
  the baselines never receive future climate. This is repeatedly flagged in-text (§6.2) and should
  not be read as a pure architecture verdict.
- **Geographic scope.** All experiments are CONUS-only (HiQ-LAI/gridMET coverage); a global ERA5-
  based generalization study is underway but has produced no results as of this writing (§Deliverable H).
- **Single pretrained checkpoint, unseeded fine-tuning stochasticity.** All results use one Chronos-2
  checkpoint (`amazon/chronos-2`); `Chronos2Dataset`'s training-window sampling is not seeded across
  fine-tuning runs, introducing run-to-run noise on the order of the leakage diagnostic's ~0.6 ΔR²
  reproduction gap between two nominally identical fine-tuning conditions.
- **PFT screening is not exhaustive.** Four conditioning architectures and two learning rates each
  were tested; conditioning additional (covariate) rows beyond the target row, and
  cross-attention/mixture-of-experts-style gating, were reasoned about but not run, for reasons
  given in the source report (§Deliverable H).

## 9. Conclusion

Across a systematic evaluation spanning a single-year comparison, 330 leave-one-year-out
cross-validation folds, a long-distance spatial transfer test, and the most extensive adaptation
study conducted in this project — seven parameter-efficient fine-tuning methods and four
vegetation-composition-conditioning architectures, including a randomized control — zero-shot
Chronos-2 emerges as a strong, robust, and (with one important, honestly-reported exception:
sustained climate anomalies genuinely absent from its context) dependable LAI forecaster, on par
with the best supervised alternatives tested, without any task-specific training. Its zero-shot
representation appears to already be close to what limited-data adaptation on this dataset can
reach: not one of eleven distinct adaptation mechanisms tested consistently improves on it, and the
project's decisive randomized control shows that even a genuinely working conditioning architecture
derives no detectable benefit from real information over scientifically meaningless input. For
vegetation LAI forecasting specifically, and plausibly for other data-limited Earth-system tasks
with structurally similar covariates, these results support deploying general-purpose,
pretrained time-series foundation models zero-shot as a strong default, reserving further
adaptation effort for settings with substantially larger or more diverse target-domain data than
were available here.
