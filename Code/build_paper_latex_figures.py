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
# Full redesign (v2): a real CONUS basemap (via geopandas/Natural Earth
# state polygons already bundled with cartopy -- no network access, no
# hand-drawn placeholder rectangle), an illustrative seasonal-LAI curve
# driving the task-formulation panel instead of plain labeled boxes, and
# a pill/badge-style pipeline instead of flat grey rectangles.
def build_study_overview():
    import geopandas as gpd
    import matplotlib.patheffects as pe
    from matplotlib.lines import Line2D
    from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

    INK = "#1C2119"
    MUTED = "#5C6355"
    ACCENT = ZERO_SHOT_COLOR          # #0072B2, already the paper's primary accent
    ACCENT_TINT = "#E4EEF5"
    WARN = RF_COLOR                   # #D55E00, already the paper's secondary accent
    WARN_TINT = "#FBEFE6"
    MAP_FILL = "#EEF0EA"
    MAP_EDGE = "#FFFFFF"
    PANEL_BG = "#FAFAF7"

    fig = plt.figure(figsize=(15.5, 6.0), constrained_layout=True)
    gs = fig.add_gridspec(1, 3, width_ratios=[1.35, 1.15, 1.0])

    # ---------------------------------------------------------------- (a) real CONUS map
    ax0 = fig.add_subplot(gs[0])
    ax0.set_title("(a) Study Pixels Across the Continental U.S.", loc="left", fontsize=12, fontweight="bold", color=INK)

    shp = "/home/deh25003/.local/share/cartopy/shapefiles/natural_earth/cultural/ne_50m_admin_1_states_provinces_lakes.shp"
    states = gpd.read_file(shp)
    exclude = {"Alaska", "Hawaii", "Puerto Rico"}
    conus = states[(states["admin"] == "United States of America") & (~states["name"].isin(exclude))]
    conus.plot(ax=ax0, facecolor=MAP_FILL, edgecolor=MAP_EDGE, linewidth=1.1, zorder=1)
    ax0.set_facecolor(PANEL_BG)
    for spine in ax0.spines.values():
        spine.set_visible(False)
    ax0.set_xticks([]); ax0.set_yticks([])
    ax0.set_xlim(-127, -65)
    ax0.set_ylim(23, 50)
    ax0.set_aspect(1.35)

    core = [
        ("low_amplitude", -117.56, 37.53, "grassland"),
        ("high_amplitude_deciduous", -84.48, 36.23, "deciduous forest"),
        ("evergreen", -82.43, 30.53, "evergreen forest"),
    ]
    label_offsets = {
        "low_amplitude": (-14, 14),
        "high_amplitude_deciduous": (10, 14),
        "evergreen": (12, -20),
    }
    for name, lon, lat, veg in core:
        ax0.scatter(lon, lat, s=170, color=ACCENT, edgecolor="white", linewidth=1.6, zorder=5)
        dx, dy = label_offsets[name]
        ax0.annotate(f"{name}\n({veg})", (lon, lat), xytext=(dx, dy), textcoords="offset points",
                     fontsize=7.6, color=INK, ha="left" if dx >= 0 else "right", zorder=6,
                     bbox=dict(boxstyle="round,pad=0.28", facecolor="white", edgecolor="#D8DCD3", linewidth=0.7))

    # spatial-transfer target: evergreen -> evergreen_west
    ew_lon, ew_lat = -122.5, 42.0
    ax0.scatter(ew_lon, ew_lat, s=170, facecolor="white", edgecolor=ACCENT, linewidth=2.0, zorder=5)
    ax0.annotate("evergreen_west\n(transfer target)", (ew_lon, ew_lat), xytext=(-10, 14),
                 textcoords="offset points", fontsize=7.6, color=INK, ha="right", zorder=6,
                 bbox=dict(boxstyle="round,pad=0.28", facecolor="white", edgecolor="#D8DCD3", linewidth=0.7))
    arrow = FancyArrowPatch((-82.43, 30.53), (ew_lon, ew_lat), connectionstyle="arc3,rad=0.22",
                             arrowstyle="-|>", mutation_scale=14, color=MUTED, linewidth=1.3,
                             linestyle=(0, (4, 2)), zorder=4)
    ax0.add_patch(arrow)
    ax0.text(-104, 40.5, "spatial transfer\n$\\sim$3,700 km", fontsize=7.6, color=MUTED, ha="center", style="italic")

    # PFT-ablation companion pixel
    mfg_lon, mfg_lat = -89.4, 40.1
    ax0.scatter(mfg_lon, mfg_lat, s=150, marker="D", color=WARN, edgecolor="white", linewidth=1.4, zorder=5)
    ax0.annotate("mixed_forest_grass\n(PFT companion)", (mfg_lon, mfg_lat), xytext=(10, -6),
                 textcoords="offset points", fontsize=7.6, color=INK, ha="left", zorder=6,
                 bbox=dict(boxstyle="round,pad=0.28", facecolor="white", edgecolor="#D8DCD3", linewidth=0.7))

    legend_handles = [
        Line2D([0], [0], marker="o", color="none", markerfacecolor=ACCENT, markeredgecolor="white",
               markersize=10, label="Core pixel (3)"),
        Line2D([0], [0], marker="o", color="none", markerfacecolor="white", markeredgecolor=ACCENT,
               markersize=10, markeredgewidth=1.8, label="Spatial-transfer target"),
        Line2D([0], [0], marker="D", color="none", markerfacecolor=WARN, markeredgecolor="white",
               markersize=9, label="PFT-ablation companion"),
    ]
    ax0.legend(handles=legend_handles, loc="lower left", frameon=False, fontsize=7.6, handletextpad=0.6)

    # ---------------------------------------------------------------- (b) forecasting task
    ax1 = fig.add_subplot(gs[1])
    ax1.set_title("(b) The Forecasting Task", loc="left", fontsize=12, fontweight="bold", color=INK)
    ax1.set_facecolor(PANEL_BG)
    ax1.axis("off")
    ax1.set_xlim(0, 1)
    ax1.set_ylim(-0.36, 1.14)

    # illustrative seasonal LAI curve: ~5 context cycles (observed) + 1
    # highlighted forecast cycle -- a stylized, physically plausible
    # green-up/senescence shape (not a real pixel's values).
    t = np.linspace(0, 1, 900)
    n_cycles = 5.6
    phase = (t * n_cycles) % 1.0
    season = np.clip(np.sin(np.pi * phase) ** 1.6, 0, None)
    curve = 0.18 + 0.62 * season + 0.03 * np.sin(2 * np.pi * t * 1.3)
    curve_top, curve_h = 0.66, 0.22
    y = curve_top + (curve - curve.min()) / (curve.max() - curve.min()) * curve_h
    split = 1.0 - 1.0 / n_cycles
    ctx_mask = t <= split
    fut_mask = t >= split
    ax1.plot(t[ctx_mask], y[ctx_mask], color=MUTED, linewidth=1.8, zorder=3)
    ax1.plot(t[fut_mask], y[fut_mask], color=ACCENT, linewidth=2.2, linestyle=(0, (3, 1.5)), zorder=4)
    ax1.axvspan(split, 1.0, color=ACCENT_TINT, zorder=1, ymin=0.60)
    ax1.text((0 + split) / 2, curve_top + curve_h + 0.06, "observed history, 2000–2021",
              ha="center", fontsize=7.8, color=MUTED)
    ax1.text((split + 1.0) / 2, curve_top + curve_h + 0.06, "to forecast\n(2022)",
              ha="center", fontsize=7.8, color=ACCENT, fontweight="bold")
    ax1.plot([split, split], [curve_top - 0.02, curve_top + curve_h + 0.03], color="#C7CBC0", lw=0.9, zorder=2)

    # three input chips -> Chronos-2 pill -> forecast pill
    chip_y = 0.42
    chips = [
        (0.145, "Historical LAI\n(target)"),
        (0.5, "Historical climate\n(past_covariates)"),
        (0.855, "Actual future climate\n(future_covariates)"),
    ]
    model_xy = (0.5, 0.10)
    for cx, label in chips:
        box = FancyBboxPatch((cx - 0.155, chip_y - 0.075), 0.31, 0.15,
                              boxstyle="round,pad=0.012,rounding_size=0.03",
                              facecolor=ACCENT_TINT, edgecolor=ACCENT, linewidth=1.1, zorder=3)
        ax1.add_patch(box)
        ax1.text(cx, chip_y, label, ha="center", va="center", fontsize=7.4, color=INK, zorder=4)
        arr = FancyArrowPatch((cx, chip_y - 0.075), (model_xy[0], model_xy[1] + 0.085),
                               arrowstyle="-|>", mutation_scale=11, color="#9AA294", linewidth=1.0, zorder=2)
        ax1.add_patch(arr)

    model_box = FancyBboxPatch((model_xy[0] - 0.22, model_xy[1] - 0.085), 0.44, 0.17,
                                boxstyle="round,pad=0.014,rounding_size=0.04",
                                facecolor=ACCENT, edgecolor=INK, linewidth=1.0, zorder=4,
                                path_effects=[pe.withSimplePatchShadow(offset=(0.6, -0.6), alpha=0.18)])
    ax1.add_patch(model_box)
    ax1.text(*model_xy, "Chronos-2\n(zero-shot)", ha="center", va="center", fontsize=9, color="white",
              fontweight="bold", zorder=5)

    out_arr = FancyArrowPatch((model_xy[0], model_xy[1] - 0.085), (model_xy[0], -0.22),
                               arrowstyle="-|>", mutation_scale=13, color=INK, linewidth=1.3, zorder=3)
    ax1.add_patch(out_arr)
    out_box = FancyBboxPatch((model_xy[0] - 0.27, -0.34), 0.54, 0.13,
                              boxstyle="round,pad=0.012,rounding_size=0.03",
                              facecolor=WARN_TINT, edgecolor=WARN, linewidth=1.1, zorder=4)
    ax1.add_patch(out_box)
    ax1.text(model_xy[0], -0.275, "LAI forecast — all 45 steps of 2022", ha="center", va="center",
              fontsize=8, color=INK, fontweight="bold", zorder=5)

    # ---------------------------------------------------------------- (c) experiment pipeline
    ax2 = fig.add_subplot(gs[2])
    ax2.set_title("(c) Experiment Pipeline", loc="left", fontsize=12, fontweight="bold", color=INK)
    ax2.set_facecolor(PANEL_BG)
    ax2.axis("off")
    ax2.set_xlim(0, 1)
    ax2.set_ylim(0, 1)

    steps = [
        "Zero-shot Chronos-2",
        "vs. 8 supervised baselines",
        "LOYO-CV (11 yrs) +\nspatial transfer",
        "Predictor sensitivity",
        "Adaptation: 7 PEFT methods +\n4 PFT-conditioning architectures",
        "Failure-mode diagnostics",
    ]
    refs = ["§6.1", "§6.2", "§6.3", "§6.4", "§6.5", "§6.6"]
    n = len(steps)
    box_h, gap = 0.125, 0.043
    total_h = n * box_h + (n - 1) * gap
    y_top = 0.5 + total_h / 2
    ys = [y_top - box_h / 2 - i * (box_h + gap) for i in range(n)]

    for i, (y, text, ref) in enumerate(zip(ys, steps, refs)):
        fill = ACCENT_TINT if i % 2 == 0 else "white"
        box = FancyBboxPatch((0.16, y - box_h / 2), 0.80, box_h,
                              boxstyle="round,pad=0.010,rounding_size=0.035",
                              facecolor=fill, edgecolor="#C7CBC0", linewidth=1.0, zorder=3)
        ax2.add_patch(box)
        ax2.text(0.565, y + 0.015, text, ha="center", va="center", fontsize=7.9, color=INK, zorder=4)
        ax2.text(0.565, y - box_h / 2 + 0.022, ref, ha="center", va="center", fontsize=6.6,
                  color=MUTED, style="italic", zorder=4)
        badge = plt.Circle((0.10, y), 0.045, facecolor=ACCENT, edgecolor="white", linewidth=1.2, zorder=5)
        ax2.add_patch(badge)
        ax2.text(0.10, y, str(i + 1), ha="center", va="center", fontsize=8.5, color="white",
                  fontweight="bold", zorder=6)
        if i < n - 1:
            ax2.add_patch(FancyArrowPatch((0.565, y - box_h / 2), (0.565, ys[i + 1] + box_h / 2),
                                           arrowstyle="-|>", mutation_scale=10, color="#9AA294",
                                           linewidth=1.0, zorder=2))

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
