# Generates every figure referenced in paper/latex/main.tex, into
# paper/latex/figures/. Two kinds of work:
#   (1) direct PNG->PDF repackaging of six already-existing, already-correct
#       project figures (no new plotting, just format conversion for LaTeX);
#   (2) real new plotting from already-saved result CSVs for the four
#       figures flagged in paper/latex/README.md as needing new work
#       (prediction_examples, baseline_comparison, study_overview,
#       pft_shuffle_control) -- no new experiments, only new visualizations
#       of existing, already-verified numbers.
# Colors reused from Code/plotting_utils.py and Code/build_fair_comparison.py
# (the project's own Okabe-Ito colorblind-safe palette) for visual
# consistency with every other figure in the repository.
from pathlib import Path

import matplotlib
matplotlib.use("AGG")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from PIL import Image
from scipy import stats

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs"
FIG_DIR = ROOT / "paper" / "latex" / "figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)

GROUND_TRUTH_COLOR = "#555555"
ZERO_SHOT_COLOR = "#0072B2"
AELSTM_COLOR = "#000000"
RF_COLOR = "#D55E00"
SHUFFLED_COLOR = "#999999"
REAL_COLOR = "#0072B2"

plt.rcParams.update({
    "savefig.dpi": 300, "font.size": 10, "axes.titlesize": 13, "axes.labelsize": 11,
    "xtick.labelsize": 9, "ytick.labelsize": 9, "legend.fontsize": 9,
    "lines.linewidth": 2.0, "axes.spines.top": False, "axes.spines.right": False,
})

PIXELS = ["low_amplitude", "high_amplitude_deciduous", "evergreen"]
PIXEL_TITLES = {
    "low_amplitude": "low_amplitude (grassland)",
    "high_amplitude_deciduous": "high_amplitude_deciduous (deciduous forest)",
    "evergreen": "evergreen (needleleaf evergreen forest)",
}


def png_to_pdf(src_png, dst_pdf):
    im = Image.open(src_png).convert("RGB")
    im.save(dst_pdf, "PDF", resolution=300.0)
    print(f"  converted {src_png.name} -> {dst_pdf.name}")


# ============================================================ (1) direct reuse
def build_reused_figures():
    mapping = {
        OUT / "loyo_cv" / "comparison" / "loyo_r2_distributions.png": FIG_DIR / "loyo_r2_distributions.pdf",
        OUT / "loyo_cv" / "comparison" / "loyo_year_difficulty_heatmap.png": FIG_DIR / "loyo_year_difficulty.pdf",
        OUT / "spatial_transfer" / "evergreen_to_evergreen_west" / "spatial_transfer_r2_drop_combined.png": FIG_DIR / "spatial_transfer.pdf",
        OUT / "predictor_ablation" / "comparison" / "predictor_importance_by_pixel.png": FIG_DIR / "predictor_importance.pdf",
        OUT / "advanced_finetuning" / "r2_by_pixel_all_methods.png": FIG_DIR / "adaptation_results.pdf",
        OUT / "leakage_diagnostic_2012" / "evergreen" / "leakage_cross_project_r2_comparison.png": FIG_DIR / "leakage_diagnostic.pdf",
    }
    for src, dst in mapping.items():
        if not src.exists():
            print(f"  MISSING SOURCE, skipped: {src}")
            continue
        png_to_pdf(src, dst)


# ============================================================ (2) prediction_examples.pdf
def build_prediction_examples():
    df = pd.read_csv(OUT / "final_comparison" / "all_methods_vs_raw_obs.csv", parse_dates=["date"])
    fig, axes = plt.subplots(1, 3, figsize=(15, 4), constrained_layout=True)
    for ax, pixel in zip(axes, PIXELS):
        sub = df[df["site"] == pixel].sort_values("date")
        ax.plot(sub["date"], sub["raw_ground_truth"], color=GROUND_TRUTH_COLOR, lw=2.4, label="Observed")
        ax.plot(sub["date"], sub["Chronos-2 (zero-shot)"], color=ZERO_SHOT_COLOR, lw=1.8, label="Zero-shot Chronos-2")
        ax.plot(sub["date"], sub["AELSTM"], color=AELSTM_COLOR, lw=1.5, ls="--", label="AELSTM")
        ax.plot(sub["date"], sub["RF"], color=RF_COLOR, lw=1.5, ls=":", label="RF")
        ax.set_title(PIXEL_TITLES[pixel], loc="left", fontsize=10)
        ax.set_xlabel("2022")
        ax.set_ylabel("LAI")
        ax.tick_params(axis="x", rotation=30)
    axes[0].legend(frameon=False, loc="upper left", fontsize=8)
    fig.savefig(FIG_DIR / "prediction_examples.pdf", bbox_inches="tight")
    plt.close(fig)
    print("  built prediction_examples.pdf")


# ============================================================ (3) baseline_comparison.pdf
def build_baseline_comparison():
    fair = pd.read_csv(OUT / "fair_comparison_vs_raw_observations.csv")
    rank = pd.read_csv(OUT / "fair_comparison_rank_consistency.csv")

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 4.5), constrained_layout=True)

    # (a) R^2 by pixel, all 10 methods, grouped bars
    models = fair["model"].unique().tolist()
    x = np.arange(len(PIXELS))
    width = 0.8 / len(models)
    for i, model in enumerate(models):
        vals = [fair[(fair.site == p) & (fair.model == model)]["R2"].values[0] for p in PIXELS]
        color = ZERO_SHOT_COLOR if model == "zero_shot" else (RF_COLOR if model == "RF" else (AELSTM_COLOR if model == "AELSTM" else "#BBBBBB"))
        ax1.bar(x + i * width, vals, width, label=model if model in ("zero_shot", "RF", "AELSTM") else None, color=color)
    ax1.set_xticks(x + width * len(models) / 2)
    ax1.set_xticklabels([p.replace("_", "\n") for p in PIXELS], fontsize=8)
    ax1.set_ylabel("$R^2$ (vs. raw observed LAI)")
    ax1.set_title("(a) All 10 methods, per pixel", loc="left")
    ax1.legend(frameon=False, fontsize=8)
    ax1.axhline(0, color="black", lw=0.6)

    # (b) mean rank +/- std, sorted
    rank_sorted = rank.sort_values("mean_rank")
    colors_b = [ZERO_SHOT_COLOR if m == "zero_shot" else (RF_COLOR if m == "RF" else "#888888") for m in rank_sorted["model"]]
    ax2.barh(rank_sorted["model"], rank_sorted["mean_rank"], xerr=rank_sorted["std_rank"], color=colors_b, capsize=3)
    ax2.invert_yaxis()
    ax2.set_xlabel("Mean rank across 3 pixels (lower = better), $\\pm$ std. dev.")
    ax2.set_title("(b) Cross-pixel rank consistency", loc="left")

    fig.savefig(FIG_DIR / "baseline_comparison.pdf", bbox_inches="tight")
    plt.close(fig)
    print("  built baseline_comparison.pdf")


# ============================================================ (4) study_overview.pdf
def build_study_overview():
    fig = plt.figure(figsize=(13, 5.5), constrained_layout=True)
    gs = fig.add_gridspec(1, 3, width_ratios=[1.1, 1.0, 1.3])

    # (a) task formulation schematic
    ax0 = fig.add_subplot(gs[0])
    ax0.axis("off")
    ax0.set_title("(a) Forecasting task", loc="left", fontsize=11)
    boxes = [
        (0.5, 0.85, "Historical LAI\n(2000–2021)\ntarget"),
        (0.5, 0.60, "Historical climate\n(7 gridMET vars)\npast_covariates"),
        (0.5, 0.35, "Actual future climate\n(2022)\nfuture_covariates"),
    ]
    for x, y, text in boxes:
        ax0.add_patch(plt.Rectangle((x - 0.42, y - 0.08), 0.84, 0.14, fill=True,
                                     facecolor="#EAF2F8", edgecolor=ZERO_SHOT_COLOR, lw=1.2))
        ax0.text(x, y, text, ha="center", va="center", fontsize=8)
        ax0.annotate("", xy=(1.0, y), xytext=(0.92, y),
                     arrowprops=dict(arrowstyle="-", color="none"))
    ax0.add_patch(plt.Rectangle((0.55, 0.05), 0.35, 0.16, fill=True, facecolor=ZERO_SHOT_COLOR,
                                 edgecolor="black", lw=1.2))
    ax0.text(0.72, 0.13, "Chronos-2\n(zero-shot)", ha="center", va="center", fontsize=8, color="white")
    for x, y, _ in boxes:
        ax0.plot([x, 0.72], [y - 0.08, 0.21], color="#888888", lw=0.8)
    ax0.annotate("", xy=(0.72, -0.05), xytext=(0.72, 0.05), arrowprops=dict(arrowstyle="->", color="black"))
    ax0.text(0.72, -0.12, "Forecast:\nLAI, all 45 steps of 2022", ha="center", va="center", fontsize=8, fontweight="bold")
    ax0.set_xlim(0, 1.1)
    ax0.set_ylim(-0.2, 1.0)

    # (b) study pixels, approximate CONUS positions (illustrative, not a projection)
    ax1 = fig.add_subplot(gs[1])
    ax1.set_title("(b) Study pixels (illustrative)", loc="left", fontsize=11)
    conus = plt.Rectangle((-125, 24), 59, 26, fill=False, edgecolor="#AAAAAA", lw=1.0, linestyle="--")
    ax1.add_patch(conus)
    pts = [
        ("low_amplitude", -117.56, 37.53, "#8B4513"),
        ("high_amplitude_deciduous", -84.48, 36.23, "#2E8B57"),
        ("evergreen", -82.43, 30.53, "#006400"),
        ("evergreen_west", -122.5, 42.0, "#006400"),
        ("mixed_forest_grass", -89.0, 40.0, "#DAA520"),
    ]
    for name, lon, lat, c in pts:
        ax1.scatter(lon, lat, color=c, s=70, edgecolor="black", zorder=3)
        ax1.annotate(name, (lon, lat), textcoords="offset points", xytext=(4, 4), fontsize=7)
    ax1.plot([-82.43, -122.5], [30.53, 42.0], color="#999999", lw=0.8, ls=":", zorder=1)
    ax1.text(-102, 34.5, "spatial\ntransfer\n$\\sim$3,700 km", fontsize=6.5, color="#666666", ha="center")
    ax1.set_xlim(-128, -64)
    ax1.set_ylim(22, 52)
    ax1.set_xlabel("Longitude")
    ax1.set_ylabel("Latitude")

    # (c) experiment tree
    ax2 = fig.add_subplot(gs[2])
    ax2.axis("off")
    ax2.set_title("(c) Experiment tree", loc="left", fontsize=11)
    steps = [
        "Zero-shot Chronos-2\n(§6.1)",
        "vs. 8 supervised baselines\n(§6.2)",
        "LOYO-CV, 11 years\n+ spatial transfer (§6.3)",
        "Predictor sensitivity\n(§6.4)",
        "Adaptation: 7 PEFT methods\n+ 4 PFT-conditioning\narchitectures (§6.5)",
        "Failure-mode diagnostics\n(§6.6)",
    ]
    n = len(steps)
    ys = np.linspace(0.92, 0.08, n)
    for y, text in zip(ys, steps):
        ax2.add_patch(plt.Rectangle((0.05, y - 0.055), 0.9, 0.09, fill=True,
                                     facecolor="#F5F5F5", edgecolor="#666666", lw=1.0))
        ax2.text(0.5, y, text, ha="center", va="center", fontsize=8)
    for y0, y1 in zip(ys[:-1], ys[1:]):
        ax2.annotate("", xy=(0.5, y1 + 0.055), xytext=(0.5, y0 - 0.055),
                     arrowprops=dict(arrowstyle="->", color="#666666"))
    ax2.set_xlim(0, 1)
    ax2.set_ylim(0, 1)

    fig.savefig(FIG_DIR / "study_overview.pdf", bbox_inches="tight")
    plt.close(fig)
    print("  built study_overview.pdf")


# ============================================================ (5) pft_shuffle_control.pdf
def build_pft_shuffle_control():
    df = pd.read_csv(OUT / "pft_v2" / "per_pixel_final_comparison.csv")
    ttest = pd.read_csv(OUT / "pft_v2" / "real_vs_shuffled_ttest.csv").iloc[0]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.3), constrained_layout=True)

    ax1.scatter(df["pft_entropy"], df["delta_fractional_vs_shuffled"], color=ZERO_SHOT_COLOR,
                edgecolor="black", linewidth=0.4, alpha=0.85, s=40)
    ax1.axhline(0, color="black", lw=1.0, ls="--")
    ax1.set_xlabel("PFT entropy (0 = pure pixel, higher = more mixed)")
    ax1.set_ylabel("$\\Delta R^2$ (real fractional PFT $-$ shuffled control)")
    ax1.set_title("(a) Real vs. shuffled PFT, per pixel ($n=70$)", loc="left", fontsize=10)
    ax1.text(0.03, 0.03,
              f"mean $\\Delta$ = {ttest['mean_delta_real_minus_shuffled']:.5f}\n"
              f"paired $t$-test $p$ = {ttest['paired_ttest_p']:.3f}\n"
              f"Wilcoxon $p$ = {ttest['wilcoxon_p']:.3f}",
              transform=ax1.transAxes, fontsize=8, va="bottom",
              bbox=dict(boxstyle="round", facecolor="white", edgecolor="#888888"))

    conditions = ["Baseline\n(no PFT)", "Real\nfractional", "Real\ndominant", "Shuffled\n(control)"]
    means = [df["R2_baseline"].mean(), df["R2_fractional"].mean(), df["R2_dominant"].mean(), df["R2_shuffled"].mean()]
    colors_c = ["#BBBBBB", REAL_COLOR, "#5588BB", SHUFFLED_COLOR]
    bars = ax2.bar(conditions, means, color=colors_c, edgecolor="black", linewidth=0.6)
    ax2.set_ylim(min(means) - 0.01, max(means) + 0.01)
    ax2.set_ylabel("Mean 2022 $R^2$ (70 pooled pixels)")
    ax2.set_title("(b) Mean $R^2$: real vs. shuffled PFT", loc="left", fontsize=10)
    for bar, m in zip(bars, means):
        ax2.text(bar.get_x() + bar.get_width() / 2, m + 0.0005, f"{m:.4f}",
                  ha="center", va="bottom", fontsize=7.5)

    fig.savefig(FIG_DIR / "pft_shuffle_control.pdf", bbox_inches="tight")
    plt.close(fig)
    print("  built pft_shuffle_control.pdf")


if __name__ == "__main__":
    print("Reused (converted) figures:")
    build_reused_figures()
    print("New figures:")
    build_prediction_examples()
    build_baseline_comparison()
    build_study_overview()
    build_pft_shuffle_control()
    print("\nAll figures in:", FIG_DIR)
    for f in sorted(FIG_DIR.glob("*.pdf")):
        print(" -", f.name, f"({f.stat().st_size // 1024} KB)")
