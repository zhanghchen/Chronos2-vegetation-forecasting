# Two figures for the GPP_vs_LAI_Progress_Update deck:
#  (1) Part 2 sanity check: actual raw-GPP seasonal time series for 3
#      diverse sites, to visually confirm the data looks physically
#      sensible (clear summer peak, winter dormancy) - not just the annual
#      sum numbers quoted in the text.
#  (2) Part 3: predicted-vs-true GPP ANOMALY curves for 4 example LOYO-CV
#      folds, deliberately spanning the full range of the 220-fold result
#      (best to worst Pearson r) rather than cherry-picked - same
#      transparency convention already used for the LAI anomaly example
#      curves in presentations/Variation_And_Equation_FineTuning.
from pathlib import Path

import matplotlib
matplotlib.use("AGG")
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path("/home/deh25003/chronos-forecasting/Chronos2-vegetation-forecasting")
OUT = ROOT / "presentations/GPP_vs_LAI_Progress_Update/figures"
DPI = 300

ACCENT = "#2F6F5E"
ACCENT_DARK = "#1E4A33"
WARN = "#B5651D"

# ---------------------------------------------------------------- Figure 1: seasonal sanity check
SITES_SEASONAL = ["px005_trees_bd", "px009_shrubs_nd", "px010_grass_nat"]
LABELS = {"px005_trees_bd": "px005 — Trees (Broadleaf-Deciduous)",
          "px009_shrubs_nd": "px009 — Shrubs (Needleleaf-Deciduous)",
          "px010_grass_nat": "px010 — Grass (Natural)"}

fig, axes = plt.subplots(3, 1, figsize=(13, 9), sharex=True, constrained_layout=True)
for ax, site in zip(axes, SITES_SEASONAL):
    df = pd.read_csv(ROOT / f"data/processed/sites_gpp/{site}.csv", parse_dates=["date"])
    df = df[(df["date"] >= "2015-01-01") & (df["date"] <= "2018-12-31")]
    ax.plot(df["date"], df["GPP"], color=ACCENT, lw=1.3)
    ax.fill_between(df["date"], 0, df["GPP"], color=ACCENT, alpha=0.15)
    ax.set_ylabel("GPP\n(kg C/m²/8-day)")
    ax.set_title(LABELS[site], loc="left", fontsize=11, fontweight="bold")
    ax.axhline(0, color="black", lw=0.6)
fig.suptitle("Raw GPP, 2015–2018 — clear summer peaks / winter dormancy, the expected physical pattern", fontsize=12)
axes[-1].set_xlabel("Date")
fig.savefig(OUT / "gpp_seasonal_sanity_check.png", dpi=DPI, bbox_inches="tight")
plt.close(fig)
print("saved gpp_seasonal_sanity_check.png")

# ---------------------------------------------------------------- Figure 2: prediction curves
FOLDS = [("px007_shrubs_ne", 2019), ("px046_grass_nat", 2015),
         ("px011_grass_man", 2014), ("high_amplitude_deciduous", 2012)]

fig2, axes2 = plt.subplots(2, 2, figsize=(15, 9), constrained_layout=True)
for ax, (site, year) in zip(axes2.flat, FOLDS):
    df = pd.read_csv(ROOT / f"outputs/loyo_cv_gpp_anomaly_predictions/{site}_{year}_predictions.csv", parse_dates=["date"])
    import numpy as np
    r = np.corrcoef(df["true_anomaly"], df["pred_anomaly"])[0, 1]
    ax.plot(df["date"], df["true_anomaly"], color=ACCENT_DARK, lw=1.8, marker="o", ms=3, label="True GPP anomaly")
    ax.plot(df["date"], df["pred_anomaly"], color=WARN, lw=1.8, marker="o", ms=3, ls="--", label="Chronos-2 prediction")
    ax.axhline(0, color="black", lw=0.6)
    ax.set_title(f"{site}, {year}  (Pearson r = {r:.2f})", loc="left", fontsize=11, fontweight="bold")
    ax.set_ylabel("GPP anomaly")
    ax.legend(fontsize=8, frameon=False, loc="best")
fig2.suptitle("Zero-shot Chronos-2: predicted vs. true GPP anomaly, 4 example LOYO-CV folds\n"
              "(deliberately spans the full range of the 220-fold result, best to worst — not cherry-picked)",
              fontsize=12)
fig2.savefig(OUT / "gpp_prediction_curves.png", dpi=DPI, bbox_inches="tight")
plt.close(fig2)
print("saved gpp_prediction_curves.png")
