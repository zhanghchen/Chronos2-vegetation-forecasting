# Breaks the Part 1 (LAI-anomaly, zero-shot Chronos-2) LOYO-CV results down
# by dominant vegetation class (PFT), instead of one pooled CONUS/Global
# boxplot - per Prof. Wang's feedback that pooling 70 sites x 11 years
# together hides which vegetation types Chronos-2 is actually good at.
#
# Reads only already-saved fold-level results - no new runs:
#   outputs/loyo_cv_anomaly/all_folds_anomaly.csv                (CONUS, 770 folds)
#   experiments/global_era5_chronos/outputs/loyo_cv_anomaly/all_folds_anomaly.csv (Global, 748 folds)
# joined against the existing authoritative per-pixel dominant-PFT
# classification already used elsewhere in this project:
#   data/processed/pft_diverse_pixels.csv                         (CONUS, ESA-CCI PFT fractions)
#   experiments/global_era5_chronos/data_selection/global_candidate_pixels_70.csv (Global, same source)
#
# Grouping is done at the FOLD level (not one point per site) so each class's
# boxplot reflects its full year-to-year spread, not just inter-site spread.
from pathlib import Path

import matplotlib
matplotlib.use("AGG")
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "outputs/loyo_cv_anomaly_by_pft"
OUT_DIR.mkdir(parents=True, exist_ok=True)

DPI = 300

# Same color identity as Code/build_purity32_pixel_comparison.py (CONUS) and
# experiments/global_era5_chronos/scripts/build_global70_comparison.py
# (Global) - underscore and hyphen variants both map to the same colors so
# one dict serves both pools after normalizing "-" -> "_".
CLASS_COLORS = {
    "TREES_NE": "#1B7837", "TREES_BD": "#5AAE61", "TREES_BE": "#2C9E5B", "TREES_ND": "#A6DBA0",
    "SHRUBS_NE": "#B35806", "SHRUBS_BE": "#8C6BB1", "SHRUBS_BD": "#E08214", "SHRUBS_ND": "#FDB863",
    "GRASS_NAT": "#762A83", "GRASS_MAN": "#C2A5CF",
}


def norm(c):
    return c.replace("-", "_")


def load_pool(folds_csv, pft_csv, pool_name):
    folds = pd.read_csv(folds_csv)
    pft = pd.read_csv(pft_csv)[["pixel_id", "dominant_pft"]].copy()
    pft["dominant_pft"] = pft["dominant_pft"].map(norm)
    merged = folds.merge(pft, left_on="site", right_on="pixel_id", how="left")
    missing = merged["dominant_pft"].isna().sum()
    if missing:
        raise RuntimeError(f"{pool_name}: {missing} folds failed to join a PFT class - check site-id mismatch")
    merged["pool"] = pool_name
    return merged


def class_order(df, metric):
    return df.groupby("dominant_pft")[metric].median().sort_values(ascending=False).index.tolist()


def boxplot_panel(ax, df, metric, title):
    order = class_order(df, metric)
    data = [df[df["dominant_pft"] == c][metric].dropna().values for c in order]
    n_folds = [len(d) for d in data]
    n_sites = [df[df["dominant_pft"] == c]["site"].nunique() for c in order]
    labels = [f"{c.replace('_', ' ').title()}\n(n={nf}, {ns} sites)" for c, nf, ns in zip(order, n_folds, n_sites)]
    bp = ax.boxplot(data, tick_labels=labels, patch_artist=True, showmeans=True)
    for patch, c in zip(bp["boxes"], order):
        patch.set_facecolor(CLASS_COLORS.get(c, "#888888"))
        patch.set_alpha(0.75)
    ax.axhline(0, color="black", lw=0.8)
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
    ax.set_ylabel(metric.replace("_", " "))
    ax.set_title(title, loc="left", fontsize=11, fontweight="bold")


def per_site_means(df, metric):
    """Collapse each site's 11 LOYO years to one mean first - the honest unit of
    independence is the site (different location/climate/species), not the
    fold (11 years at the same site are not 11 independent draws). Fixes the
    pseudo-replication the fold-level boxplot above was flagged for: a class
    with 6 sites gets 6 points here, not 66."""
    return df.groupby(["dominant_pft", "site"], as_index=False)[metric].mean()


def boxplot_panel_persite(ax, df, metric, title):
    site_means = per_site_means(df, metric)
    order = site_means.groupby("dominant_pft")[metric].median().sort_values(ascending=False).index.tolist()
    data = [site_means[site_means["dominant_pft"] == c][metric].dropna().values for c in order]
    labels = [f"{c.replace('_', ' ').title()}\n(n={len(d)} sites)" for c, d in zip(order, data)]
    bp = ax.boxplot(data, tick_labels=labels, patch_artist=True, showmeans=True)
    for patch, c in zip(bp["boxes"], order):
        patch.set_facecolor(CLASS_COLORS.get(c, "#888888"))
        patch.set_alpha(0.75)
    for i, d in enumerate(data, start=1):
        ax.scatter([i] * len(d), d, color="black", s=14, zorder=3, alpha=0.6)
    ax.axhline(0, color="black", lw=0.8)
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
    ax.set_ylabel(f"{metric.replace('_', ' ')} (site's 11-year mean)")
    ax.set_title(title, loc="left", fontsize=11, fontweight="bold")


def byyear_panel(ax, df, metric, title):
    """One line per vegetation class, its cross-site mean for each LOYO test
    year - shows whether the class ranking (e.g. shrubs > grass > trees) is
    stable across years or driven by a handful of anomalous years."""
    by_year = df.groupby(["dominant_pft", "test_year"])[metric].mean().unstack("dominant_pft")
    order = df.groupby("dominant_pft")[metric].median().sort_values(ascending=False).index.tolist()
    for c in order:
        if c in by_year.columns:
            ax.plot(by_year.index, by_year[c], marker="o", ms=3.5, lw=1.3,
                     color=CLASS_COLORS.get(c, "#888888"), label=c.replace("_", " ").title())
    ax.axhline(0, color="black", lw=0.8)
    ax.set_xlabel("LOYO test year")
    ax.set_ylabel(f"cross-site mean {metric.replace('_', ' ')}")
    ax.set_title(title, loc="left", fontsize=11, fontweight="bold")
    ax.legend(fontsize=7, ncol=2, frameon=False, loc="upper left", bbox_to_anchor=(1.01, 1.0))


def summarize(df, metric):
    g = df.groupby("dominant_pft").agg(
        n_folds=("site", "size"),
        n_sites=("site", "nunique"),
        mean=(metric, "mean"),
        median=(metric, "median"),
        std=(metric, "std"),
    ).sort_values("median", ascending=False)
    return g


def main():
    conus = load_pool(ROOT / "outputs/loyo_cv_anomaly/all_folds_anomaly.csv",
                       ROOT / "data/processed/pft_diverse_pixels.csv", "CONUS")
    glob = load_pool(ROOT / "experiments/global_era5_chronos/outputs/loyo_cv_anomaly/all_folds_anomaly.csv",
                      ROOT / "experiments/global_era5_chronos/data_selection/global_candidate_pixels_70.csv", "Global")

    fig, axes = plt.subplots(2, 2, figsize=(16, 13), constrained_layout=True)
    boxplot_panel(axes[0, 0], conus, "Pearson_r_anomaly", "(a) CONUS - Pearson r (LAI anomaly) by vegetation class")
    boxplot_panel(axes[0, 1], glob, "Pearson_r_anomaly", "(b) Global - Pearson r (LAI anomaly) by vegetation class")
    boxplot_panel(axes[1, 0], conus, "R2_anomaly", "(c) CONUS - R² (LAI anomaly) by vegetation class")
    boxplot_panel(axes[1, 1], glob, "R2_anomaly", "(d) Global - R² (LAI anomaly) by vegetation class")
    fig.suptitle("LAI-anomaly LOYO-CV, zero-shot Chronos-2, broken down by dominant vegetation class\n"
                  "(previously pooled across all 70/68 sites - see outputs/loyo_cv_anomaly_by_pft/README.md)",
                  fontsize=12)
    fig.savefig(OUT_DIR / "loyo_anomaly_by_pft_boxplots.png", dpi=DPI, bbox_inches="tight")
    fig.savefig(OUT_DIR / "loyo_anomaly_by_pft_boxplots.pdf", bbox_inches="tight")
    plt.close(fig)
    print("saved loyo_anomaly_by_pft_boxplots.png/.pdf (fold-level - pseudo-replicated, see per-site version)")

    # --- per-site version: one point per site (11-year mean), not one per fold ---
    fig2, axes2 = plt.subplots(2, 2, figsize=(16, 11), constrained_layout=True)
    boxplot_panel_persite(axes2[0, 0], conus, "Pearson_r_anomaly", "(a) CONUS - Pearson r, per-site 11-yr mean")
    boxplot_panel_persite(axes2[0, 1], glob, "Pearson_r_anomaly", "(b) Global - Pearson r, per-site 11-yr mean")
    boxplot_panel_persite(axes2[1, 0], conus, "R2_anomaly", "(c) CONUS - R², per-site 11-yr mean")
    boxplot_panel_persite(axes2[1, 1], glob, "R2_anomaly", "(d) Global - R², per-site 11-yr mean")
    fig2.suptitle("Same data, collapsed to one point per site (11-year mean) instead of one per fold\n"
                  "- the honest sample size per class is the site count, not the fold count",
                  fontsize=12)
    fig2.savefig(OUT_DIR / "loyo_anomaly_by_pft_persite_boxplots.png", dpi=DPI, bbox_inches="tight")
    fig2.savefig(OUT_DIR / "loyo_anomaly_by_pft_persite_boxplots.pdf", bbox_inches="tight")
    plt.close(fig2)
    print("saved loyo_anomaly_by_pft_persite_boxplots.png/.pdf")

    # --- by-year version: is the class ranking stable across the 11 LOYO years? ---
    fig3, axes3 = plt.subplots(1, 2, figsize=(17, 6), constrained_layout=True)
    byyear_panel(axes3[0], conus, "Pearson_r_anomaly", "(a) CONUS - Pearson r by class, per LOYO test year")
    byyear_panel(axes3[1], glob, "Pearson_r_anomaly", "(b) Global - Pearson r by class, per LOYO test year")
    fig3.suptitle("Cross-site mean Pearson r per vegetation class, year by year (not pooled across years)", fontsize=12)
    fig3.savefig(OUT_DIR / "loyo_anomaly_by_pft_byyear.png", dpi=DPI, bbox_inches="tight")
    fig3.savefig(OUT_DIR / "loyo_anomaly_by_pft_byyear.pdf", bbox_inches="tight")
    plt.close(fig3)
    print("saved loyo_anomaly_by_pft_byyear.png/.pdf")

    conus_persite_r = per_site_means(conus, "Pearson_r_anomaly").rename(columns={"Pearson_r_anomaly": "site_mean_pearson_r"})
    conus_persite_r.to_csv(OUT_DIR / "conus_persite_means_pearson_r.csv", index=False)
    glob_persite_r = per_site_means(glob, "Pearson_r_anomaly").rename(columns={"Pearson_r_anomaly": "site_mean_pearson_r"})
    glob_persite_r.to_csv(OUT_DIR / "global_persite_means_pearson_r.csv", index=False)

    conus_r = summarize(conus, "Pearson_r_anomaly")
    conus_r2 = summarize(conus, "R2_anomaly")
    glob_r = summarize(glob, "Pearson_r_anomaly")
    glob_r2 = summarize(glob, "R2_anomaly")
    conus_r.to_csv(OUT_DIR / "conus_by_pft_pearson_r.csv")
    conus_r2.to_csv(OUT_DIR / "conus_by_pft_r2.csv")
    glob_r.to_csv(OUT_DIR / "global_by_pft_pearson_r.csv")
    glob_r2.to_csv(OUT_DIR / "global_by_pft_r2.csv")

    print("\n=== CONUS, Pearson r (anomaly), by class ===")
    print(conus_r)
    print("\n=== CONUS, R2 (anomaly), by class ===")
    print(conus_r2)
    print("\n=== Global, Pearson r (anomaly), by class ===")
    print(glob_r)
    print("\n=== Global, R2 (anomaly), by class ===")
    print(glob_r2)

    print("\n=== CONUS, per-site 11-yr mean Pearson r, by class (honest n=sites) ===")
    print(conus_persite_r.groupby("dominant_pft")["site_mean_pearson_r"].agg(["count", "mean", "median"]).sort_values("median", ascending=False))
    print("\n=== Global, per-site 11-yr mean Pearson r, by class (honest n=sites) ===")
    print(glob_persite_r.groupby("dominant_pft")["site_mean_pearson_r"].agg(["count", "mean", "median"]).sort_values("median", ascending=False))


if __name__ == "__main__":
    main()
