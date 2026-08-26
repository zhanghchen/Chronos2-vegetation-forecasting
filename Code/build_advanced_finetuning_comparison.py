# Builds the final comparison for the advanced Chronos-2 fine-tuning
# experiment: reads the 6 new methods' already-saved results plus the 3
# existing baselines (zero-shot, original LoRA, improved LoRA - never
# rerun), and produces the final ranking table, capacity-vs-performance
# analysis, and comparison figures. All outputs saved under
# outputs/advanced_finetuning/ (existing zero_shot/finetuned_lora/
# finetuned_lora_improved/ directories are read-only, never modified).
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import common_pipeline as cp

OUT = cp.OUTPUTS_ROOT / "advanced_finetuning"
SITES = cp.SITES
NEW_METHODS = ["dora", "vera", "ia3", "ln_tuning", "bitfit", "partial_last_block"]
METHOD_LABELS = {
    "zero_shot": "Zero-shot", "finetuned_lora": "Original LoRA", "finetuned_lora_improved": "Improved LoRA",
    "dora": "DoRA", "vera": "VeRA", "ia3": "IA3", "ln_tuning": "LN-Tuning", "bitfit": "BitFit",
    "partial_last_block": "Partial (last block)",
}
PAPER_REF = {
    "zero_shot": "Ansari et al., Chronos-2 (Amazon, 2025)", "finetuned_lora": "Hu et al., LoRA (ICLR'22)",
    "finetuned_lora_improved": "Hu et al., LoRA (ICLR'22) + validation selection",
    "dora": "Liu et al., DoRA (ICML'24 Oral)", "vera": "Kopiczko et al., VeRA (ICLR'24)",
    "ia3": "Liu et al., IA3 (NeurIPS'22)", "ln_tuning": "LN-Tuning (used in Beyond-LoRA, 2409.11302)",
    "bitfit": "Zaken et al., BitFit (ACL'22)", "partial_last_block": "Classical partial fine-tuning",
}
ALL_ORDER = ["zero_shot", "finetuned_lora", "finetuned_lora_improved"] + NEW_METHODS
COLORS = {
    "zero_shot": "#7a7a7a", "finetuned_lora": "#a8791f", "finetuned_lora_improved": "#c9944a",
    "dora": "#1f5c4a", "vera": "#3a6ea5", "ia3": "#7b4b94", "ln_tuning": "#2a9d8f",
    "bitfit": "#c0562f", "partial_last_block": "#555555",
}


def load_baseline_metrics(mode):
    rows = []
    for site in SITES:
        path = cp.OUTPUTS_ROOT / mode / site / "metrics.txt"
        m = {}
        with open(path) as f:
            for line in f:
                k, v = line.strip().split(": ")
                try:
                    m[k] = float(v)
                except ValueError:
                    pass
        m["method"] = mode
        m["site"] = site
        rows.append(m)
    return pd.DataFrame(rows)


def load_all():
    baselines = pd.concat([load_baseline_metrics(m) for m in ["zero_shot", "finetuned_lora", "finetuned_lora_improved"]],
                           ignore_index=True)
    new = pd.read_csv(OUT / "advanced_finetuning_all_results.csv")
    cols = ["method", "site", "R2", "RMSE", "MAE", "Pearson_r"]
    combined = pd.concat([baselines[cols], new[cols + ["n_trainable", "n_total", "train_time_sec", "num_steps"]]],
                          ignore_index=True)
    return combined


def build_final_table(df):
    zs = df[df.method == "zero_shot"].set_index("site")["R2"]
    lora = df[df.method == "finetuned_lora"].set_index("site")["R2"]

    rows = []
    for method in ALL_ORDER:
        sub = df[df.method == method].set_index("site").reindex(zs.index)
        mean_r2 = sub["R2"].mean()
        std_r2 = sub["R2"].std()
        mean_rmse = sub["RMSE"].mean()
        mean_mae = sub["MAE"].mean()
        mean_pearson = sub["Pearson_r"].mean()
        delta_vs_zs = (sub["R2"] - zs).mean()
        delta_vs_lora = (sub["R2"] - lora).mean()
        n_beats_zs = int((sub["R2"] > zs).sum())
        rows.append({
            "Method": METHOD_LABELS[method], "Paper": PAPER_REF[method],
            "Trainable Params": int(sub["n_trainable"].iloc[0]) if "n_trainable" in sub and pd.notna(sub["n_trainable"].iloc[0]) else np.nan,
            "Mean R2": mean_r2, "Std R2 (3 pixels)": std_r2, "Mean RMSE": mean_rmse, "Mean MAE": mean_mae,
            "Mean Pearson r": mean_pearson, "Mean Train Time (s)": sub["train_time_sec"].mean() if "train_time_sec" in sub else np.nan,
            "Delta vs Zero-shot": delta_vs_zs, "Delta vs Original LoRA": delta_vs_lora,
            "Pixels Beating Zero-shot": f"{n_beats_zs}/3",
        })
    table = pd.DataFrame(rows).sort_values("Mean R2", ascending=False)
    table.to_csv(OUT / "final_ranking_table.csv", index=False)
    print(table.to_string(index=False))
    return table


def plot_r2_by_pixel(df):
    fig, axes = plt.subplots(1, 3, figsize=(20, 6), constrained_layout=True, sharey=True)
    for ax, site in zip(axes, SITES):
        sub = df[df.site == site].set_index("method").reindex(ALL_ORDER)
        colors = [COLORS[m] for m in ALL_ORDER]
        ax.bar(range(len(ALL_ORDER)), sub["R2"], color=colors)
        ax.axhline(sub.loc["zero_shot", "R2"], color="black", linewidth=1.2, linestyle="--", label="Zero-shot level")
        ax.axhline(0, color="#999", linewidth=0.8)
        ax.set_xticks(range(len(ALL_ORDER)))
        ax.set_xticklabels([METHOD_LABELS[m] for m in ALL_ORDER], rotation=45, ha="right", fontsize=9)
        ax.set_title(site, loc="left", fontsize=12.5)
        ax.legend(frameon=False, fontsize=8)
    axes[0].set_ylabel("R² (test year 2022)")
    fig.suptitle("All 9 methods, all 3 pixels: R² vs. zero-shot", fontsize=15, fontweight="bold")
    fig.savefig(OUT / "r2_by_pixel_all_methods.png", dpi=150, facecolor="white")
    plt.close(fig)


def plot_params_vs_r2(df):
    new_df = df[df.method.isin(NEW_METHODS)].copy()
    fig, ax = plt.subplots(figsize=(9, 6.5), constrained_layout=True)
    markers = {"low_amplitude": "o", "high_amplitude_deciduous": "s", "evergreen": "^"}
    for site in SITES:
        sub = new_df[new_df.site == site]
        for _, row in sub.iterrows():
            ax.scatter(row["n_trainable"], row["R2"], color=COLORS[row["method"]], marker=markers[site], s=110,
                       edgecolor="black", linewidth=0.6, zorder=3)
    ax.set_xscale("log")
    ax.set_xlabel("Trainable parameters (log scale)")
    ax.set_ylabel("R² (test year 2022)")
    ax.set_title("Trainable parameter count vs. test R² (new methods only)", loc="left", fontsize=12.5)
    ax.axhline(0, color="#999", linewidth=0.8)
    method_handles = [plt.Line2D([0], [0], marker="o", color="w", markerfacecolor=COLORS[m], markersize=9, label=METHOD_LABELS[m])
                       for m in NEW_METHODS]
    site_handles = [plt.Line2D([0], [0], marker=markers[s], color="w", markerfacecolor="gray", markersize=9, label=s)
                     for s in SITES]
    leg1 = ax.legend(handles=method_handles, frameon=False, fontsize=8.5, loc="lower right", title="Method")
    ax.add_artist(leg1)
    ax.legend(handles=site_handles, frameon=False, fontsize=8.5, loc="upper left", title="Pixel")
    fig.savefig(OUT / "params_vs_r2.png", dpi=150, facecolor="white")
    plt.close(fig)


def plot_validation_curves(method_a="bitfit", method_b="dora", site="evergreen"):
    """The clearest failure-mode illustration: BitFit's best validation loss
    (lowest of ALL 24 evergreen configs across all 6 methods) but worst test
    R2, vs. DoRA's genuine train/val convergence that also generalizes."""
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5), constrained_layout=True)
    for ax, method in zip(axes, [method_a, method_b]):
        search_dir = OUT / method / site / "search"
        summary = pd.read_csv(OUT / method / site / "search_summary.csv")
        winner_tag = "_".join(f"{k}{v:g}" for k, v in summary.sort_values("best_eval_loss").iloc[0][
            [c for c in ["learning_rate", "rank"] if c in summary.columns]].items())
        train = pd.read_csv(search_dir / f"{winner_tag}_train_loss.csv")
        ev = pd.read_csv(search_dir / f"{winner_tag}_eval_loss.csv")
        ax.plot(train.step, train.train_loss, marker="o", markersize=4, color="#a8791f", label="Train loss")
        ax.plot(ev.step, ev.eval_loss, marker="s", markersize=5, color="#1f5c4a", label="Validation loss")
        best_step = ev.loc[ev.eval_loss.idxmin(), "step"]
        ax.axvline(best_step, color="#c0562f", linestyle="--", linewidth=1.2, label=f"Selected step={best_step}")
        ax.set_xlabel("Training step")
        ax.set_ylabel("Loss")
        ax.set_title(f"{METHOD_LABELS[method]} / {site} (winning config: {winner_tag})", loc="left", fontsize=12)
        ax.legend(frameon=False, fontsize=9)
    fig.suptitle("Validation-loss selection looks fine for both methods - but test R² tells a different story\n"
                 f"({METHOD_LABELS[method_a]} test R²=0.587 vs. {METHOD_LABELS[method_b]} test R²=0.835, same pixel)",
                 fontsize=13, fontweight="bold")
    fig.savefig(OUT / f"validation_curves_{method_a}_vs_{method_b}_{site}.png", dpi=150, facecolor="white")
    plt.close(fig)


def plot_prediction_curves(site="evergreen", methods=("zero_shot", "finetuned_lora", "dora", "bitfit")):
    fig, ax = plt.subplots(figsize=(11, 5.5), constrained_layout=True)
    for method in methods:
        if method in ("zero_shot", "finetuned_lora", "finetuned_lora_improved"):
            preds = pd.read_csv(cp.OUTPUTS_ROOT / method / site / "predictions.csv", parse_dates=["date"])
            obs_col, pred_col = "ground_truth", "prediction"
        else:
            preds = pd.read_csv(OUT / method / site / "predictions.csv", parse_dates=["date"])
            obs_col, pred_col = "ground_truth", "prediction"
        if method == methods[0]:
            ax.plot(preds.date, preds[obs_col], color="black", linewidth=2.6, label="Observed", zorder=10)
        ax.plot(preds.date, preds[pred_col], color=COLORS[method], linewidth=2.0, marker="o", markersize=3,
                label=METHOD_LABELS[method])
    ax.set_title(f"{site}, 2022: prediction curves, selected methods", loc="left", fontsize=13)
    ax.set_ylabel("LAI")
    ax.tick_params(axis="x", rotation=20)
    ax.legend(frameon=False, fontsize=9)
    fig.savefig(OUT / f"prediction_curves_{site}.png", dpi=150, facecolor="white")
    plt.close(fig)


def main():
    df = load_all()
    table = build_final_table(df)
    plot_r2_by_pixel(df)
    plot_params_vs_r2(df)
    plot_validation_curves("bitfit", "dora", "evergreen")
    plot_prediction_curves("evergreen", ("zero_shot", "finetuned_lora", "dora", "bitfit"))
    plot_prediction_curves("low_amplitude", ("zero_shot", "finetuned_lora_improved", "ia3", "dora"))
    plot_prediction_curves("high_amplitude_deciduous", ("zero_shot", "vera", "bitfit", "dora"))
    print(f"\nSaved all figures + final_ranking_table.csv to {OUT}")


if __name__ == "__main__":
    main()
