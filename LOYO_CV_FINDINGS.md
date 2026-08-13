# LOYO-CV: Scientific Findings

**Scope**: all 10 methods (AELSTM, BiLSTM, LSTM, GRU, RNN, CNN, RF, SVM, Chronos-2 zero-shot,
Chronos-2 LoRA fine-tuned), 3 pixels (`low_amplitude`, `high_amplitude_deciduous`, `evergreen`),
11 held-out years (2012-2022), each trained on a fixed 12-year rolling window immediately before
its held-out year. 330 fold results total, every one scored against raw observed LAI. See
`AELSTM/README.md`'s LOYO-CV section for the full design rationale (why a fixed rolling window,
not classic leave-one-year-out or an expanding window) and the two leakage bugs fixed to build this.

Sources: `outputs/loyo_cv/comparison/loyo_all_folds.csv` (long format, 330 rows),
`loyo_summary_mean_std.csv` (mean/median/std/min/max per model/pixel),
`loyo_rank_consistency_<pixel>.csv`. Built by `Code/loyo_scientific_analysis.py`.

---

## 1. Full distribution statistics, per model and pixel (R²)

| `low_amplitude` | mean | median | std | min | max |
|---|---|---|---|---|---|
| AELSTM | 0.145 | 0.341 | 0.684 | -1.829 | 0.657 |
| BiLSTM | 0.162 | 0.309 | 0.692 | -1.818 | 0.673 |
| LSTM | 0.164 | 0.328 | 0.671 | -1.780 | 0.685 |
| GRU | 0.188 | 0.422 | 0.696 | -1.802 | 0.660 |
| RNN | 0.185 | 0.363 | 0.588 | -1.462 | 0.632 |
| CNN | 0.074 | 0.191 | 0.653 | -1.797 | 0.520 |
| RF | 0.251 | 0.402 | 0.623 | -1.510 | 0.723 |
| SVM | 0.307 | 0.401 | 0.392 | -0.747 | 0.706 |
| **zero_shot** | **0.317** | 0.387 | 0.388 | -0.717 | 0.645 |
| finetuned_lora | 0.095 | 0.259 | 0.452 | -0.817 | 0.577 |

| `high_amplitude_deciduous` | mean | median | std | min | max |
|---|---|---|---|---|---|
| AELSTM | 0.944 | 0.941 | 0.021 | 0.919 | 0.980 |
| BiLSTM | 0.958 | 0.961 | 0.021 | 0.926 | 0.983 |
| LSTM | 0.951 | 0.949 | 0.020 | 0.923 | 0.981 |
| GRU | 0.957 | 0.961 | 0.021 | 0.922 | 0.980 |
| RNN | 0.949 | 0.947 | 0.023 | 0.917 | 0.979 |
| CNN | 0.940 | 0.938 | 0.027 | 0.891 | 0.972 |
| **RF** | **0.960** | 0.969 | 0.022 | 0.915 | 0.986 |
| SVM | 0.943 | 0.955 | 0.028 | 0.886 | 0.968 |
| zero_shot | 0.957 | 0.961 | 0.023 | 0.896 | 0.985 |
| finetuned_lora | 0.946 | 0.949 | 0.024 | 0.880 | 0.971 |

| `evergreen` | mean | median | std | min | max |
|---|---|---|---|---|---|
| AELSTM | -0.263 | 0.485 | 2.272 | -7.052 | 0.763 |
| BiLSTM | -0.181 | 0.532 | 2.091 | -6.425 | 0.760 |
| LSTM | -0.128 | 0.515 | 2.019 | -6.175 | 0.753 |
| GRU | -0.240 | 0.540 | 2.219 | -6.866 | 0.768 |
| RNN | -0.137 | 0.531 | 1.946 | -5.952 | 0.729 |
| CNN | -0.229 | 0.519 | 2.183 | -6.729 | 0.781 |
| RF | -0.168 | 0.522 | 2.415 | -7.423 | 0.809 |
| SVM | 0.049 | 0.565 | 1.546 | -4.548 | 0.797 |
| zero_shot | -0.134 | 0.583 | 2.495 | -7.637 | 0.900 |
| **finetuned_lora** | -0.261 | **0.683** | 2.757 | -8.522 | 0.925 |

**Read the mean and median together, not the mean alone.** At `evergreen`, every method's mean R²
is near zero or negative — but every method's *median* is a perfectly respectable 0.48-0.68. One
fold (2012) is single-handedly dragging every mean deeply negative (see §3). `loyo_r2_distributions.png`
shows this directly: a healthy box-and-median sitting well above an isolated outlier point far below it.

---

## 2. Which years are consistently difficult, and why

`loyo_year_difficulty_heatmap.png` shows the z-score of each pixel's median-across-10-models R²,
computed separately per pixel (so the three very different R² scales - roughly [-8, 1] at
`evergreen`, [-1.8, 0.7] at `low_amplitude`, [0.89, 0.99] at `high_amplitude_deciduous` - are
comparable). Two folds stand out as genuine, large outliers (z < -2.8); nothing else comes close:

| Pixel | Year | z-score | Median R² (that pixel's other years) |
|---|---|---|---|
| `evergreen` | **2012** | -3.0 | -6.80 (vs. 0.22 to 0.77 every other year) |
| `low_amplitude` | **2018** | -2.9 | -1.64 (vs. 0.04 to 0.65 every other year) |

**No year is difficult across all three pixels at once** - 2012 and 2018 are each hard at exactly
one pixel and unremarkable at the other two. Difficulty here is local to a pixel's own history, not
a shared climate signal across this small 3-pixel sample.

Checking both flagged folds against the raw data (`loyo_outlier_fold_investigation.png`) shows two
*different* failure modes, not one:

- **`evergreen`/2012 - a real, sustained climate anomaly.** The pixel's 2000-2011 training
  climatology expects LAI to climb to a seasonal peak of ~5.0-5.1 in May-June. 2012's actual LAI
  never exceeds ~3.9 and spends the second half of the year well below 2.5 (annual mean drops from
  4.19 in 2011 to 2.69 in 2012), consistent with the 2011-2012 US Southeast drought. Every model,
  never having seen a comparable stress year in training, confidently forecasts a normal season and
  is wrong for months at a stretch.
- **`low_amplitude`/2018 - not a climate-driver anomaly, but a signal-to-noise failure.** Annual
  precipitation (26.9mm) and mean VPD for 2018 are unremarkable versus the 2006-2017 training
  average (24.1mm) - there's no single driving-variable story here. What's different is the
  *shape*: 2018's actual LAI zig-zags up and down every ~8 days instead of tracing the smooth
  single-peaked curve the climatology expects. This pixel was selected in the first place for its
  very small seasonal amplitude (0.18 normalized) - its year-to-year "signal" is already tiny
  relative to short-term noise, so a single unusually choppy year is enough to tank every model's R²
  even without an extreme annual-scale event.

Two milder dips are visible at `high_amplitude_deciduous` (2020: z=-1.2, 2021: z=-1.7) but these
aren't practically meaningful - R² there never drops below 0.92, i.e. statistical noise around an
already excellent baseline (peak LAI 5.16-5.20 vs. 5.29-5.57 in surrounding years - a small, real
difference, just not one severe enough to matter for forecast quality).

---

## 3. Does Chronos-2 hold up better on difficult years?

**No consistent pattern - the two outlier folds tell opposite stories**, which matters more than
either average given there are only two of them:

| Outlier fold | zero_shot rank (of 10) | finetuned_lora rank (of 10) | Best performer |
|---|---|---|---|
| `evergreen`/2012 | **9th** | **10th (worst)** | SVM (R²=-4.55, "least bad") |
| `low_amplitude`/2018 | **1st (best)** | 3rd | zero_shot |

On the severe, sustained drought fold, both Chronos-2 variants are the *worst two* of all 10
methods - the AELSTM-family models (SVM, RNN, LSTM in particular) degrade more gracefully than
Chronos-2 here. On the erratic/noisy fold, zero-shot is the single best performer and fine-tuned is
3rd, while most of the AELSTM family (everything except SVM) clusters much worse (R² -1.46 to -1.83).

Averaged across just these two folds, zero-shot's mean rank moves from 3.6 (normal folds) to 5.0
(difficult folds), and its R² advantage over the AELSTM-family average flips from +0.07 to -0.18 -
but this two-point average is driven entirely by the catastrophic `evergreen` result and shouldn't
be read as "Chronos-2 is worse in hard years" in general; the `low_amplitude` fold shows the exact
opposite. With only two genuine outlier folds in this sample, the honest conclusion is: **Chronos-2's
relative robustness to anomalous years is fold-dependent, not a fixed property of the model** - it
has no special resistance to a sustained, multi-month climate anomaly it never saw in training, but
copes at least as well as (and here, better than) the AELSTM family with a noisy, low-signal year.

---

## 4. Model ranking consistency (across all 33 folds = 3 pixels × 11 years)

| Model | Mean rank (of 10) | Std rank | Top-3 finishes | Bottom-3 finishes |
|---|---|---|---|---|
| **RF** | **3.39** | 2.24 | 20 / 33 (61%) | 3 |
| **zero_shot** | **3.70** | 2.96 | 21 / 33 (64%) | 6 |
| SVM | 5.06 | 2.88 | 11 | 9 |
| BiLSTM | 5.30 | 2.72 | 11 | 11 |
| GRU | 5.45 | 2.24 | 6 | 4 |
| finetuned_lora | 5.76 | **3.66** | 13 | 15 |
| LSTM | 5.82 | 2.01 | 5 | 8 |
| RNN | 6.03 | 2.66 | 8 | 12 |
| AELSTM | 7.00 | 2.33 | 2 | 12 |
| CNN | 7.48 | 2.37 | 2 | 19 |

`loyo_ranking_frequency.png` visualizes this directly. Two findings stand out:

- **RF and zero-shot are the only methods that are both frequently best *and* rarely worst** - the
  two lowest mean ranks, combined with top-3 finishes on roughly 6 of every 10 folds. RF has the
  single lowest rank-volatility (std 2.24) of any method with a comparably strong mean rank.
- **LoRA fine-tuning is the single most volatile method** (std rank 3.66, the highest of all 10) -
  it has more top-3 finishes (13) than most AELSTM-family models, but *also* more bottom-3 finishes
  (15) than all but CNN. It is rarely "middling": across 33 folds it lands in the middle (4th-7th)
  only 5 times, versus RF's 10. Fine-tuning doesn't uniformly help or hurt so much as it makes
  outcomes less predictable in both directions.
- **AELSTM itself and CNN are the weakest methods in this study**: AELSTM finishes in the bottom-3
  on 12 of 33 folds (36%) and top-3 on only 2 (6%); CNN is worse still, bottom-3 on 19 of 33 folds
  (58%). Neither the published architecture nor the simplest baseline NN generalizes as reliably
  across pixels and years as RF, SVM, or Chronos-2.

---

## Key Findings

1. **Report median alongside mean for any pixel with a severe outlier year.** At `evergreen`, every
   method's mean R² is at or below zero, which looks like uniform failure - but the median for every
   method is a healthy 0.48-0.68. A single catastrophic fold (2012) drives the mean; it does not
   reflect typical performance.
2. **The two hardest folds in this study are pixel-specific and mechanistically different.**
   `evergreen`/2012 is a genuine, months-long climate anomaly (drought) no model had trained on.
   `low_amplitude`/2018 has unremarkable annual climate totals but an erratic, non-seasonal LAI
   trajectory - a signal-to-noise failure specific to an already-low-amplitude pixel. No single year
   was difficult across all three pixels at once.
3. **Chronos-2 has no general "robustness advantage" on anomalous years.** It was the two worst
   methods of ten on the drought fold, and the single best method on the noisy fold. Its edge over
   the AELSTM family (established on the single-2022-split results) comes from normal years, not
   from unusual resilience to distribution shift.
4. **RF and Chronos-2 zero-shot are the most dependable methods overall** - lowest mean rank,
   highest top-3 rate, and (for RF especially) the lowest rank volatility across 33 folds spanning
   3 pixels and 11 years. This corroborates, with far more evidence, the single-2022-split finding
   that zero-shot Chronos-2 and RF/SVM were the most consistent performers.
5. **LoRA fine-tuning is confirmed to underperform zero-shot on average, but the more precise
   finding is that it is the most *volatile* method in the study** - capable of the best result on a
   given fold and also disproportionately likely to produce the worst. This is consistent with the
   earlier finding that no validation-based checkpoint selection is used during fine-tuning: without
   a safeguard, outcomes swing further in both directions rather than reliably improving.
6. **The published AELSTM architecture and the CNN baseline are the least reliable methods tested**,
   finishing in the bottom 3 of 10 on 36% and 58% of folds respectively - simpler methods (RF, SVM)
   generalize more consistently across this project's pixels and years than either.
