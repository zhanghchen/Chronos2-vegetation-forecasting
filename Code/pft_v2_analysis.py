# Final analysis for the PFT-v2 research loop: per-pixel comparison,
# mixed-vs-pure, real-vs-shuffled statistical test, seasonal-phase
# breakdown, and PFT perturbation sensitivity on the finalized (low_rank,
# fractional) model. Reads only outputs/pft_v2/ (new; does not touch any
# prior experiment's outputs).
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import torch

import common_pipeline as cp
import run_chronos2 as rc2
import pft_v2_dataset as pvd
import pft_v2_train as pvt
from pft_v2_model import Chronos2PFTModelV2

OUTPUT_DIR = cp.OUTPUTS_ROOT / "pft_v2"
WINNER_ARCH = "low_rank"


def load_metrics(tag, label):
    return pd.read_csv(OUTPUT_DIR / tag / WINNER_ARCH / f"metrics_{label}.csv")


def per_pixel_comparison(sel):
    base = pd.read_csv(OUTPUT_DIR / "final_baseline" / "metrics_test2022.csv")[["pixel_id", "R2", "RMSE"]]
    frac = load_metrics("final_fractional", "test2022")[["pixel_id", "R2", "RMSE"]]
    dom = load_metrics("final_dominant", "test2022")[["pixel_id", "R2", "RMSE"]]
    shuf = load_metrics("final_shuffled", "test2022")[["pixel_id", "R2", "RMSE"]]

    m = base.merge(frac, on="pixel_id", suffixes=("_baseline", "_fractional"))
    m = m.merge(dom, on="pixel_id").rename(columns={"R2": "R2_dominant", "RMSE": "RMSE_dominant"})
    m = m.merge(shuf, on="pixel_id").rename(columns={"R2": "R2_shuffled", "RMSE": "RMSE_shuffled"})
    m = m.merge(sel[["pixel_id", "dominant_pft", "pft_purity", "pft_entropy"]], on="pixel_id", how="left")

    m["delta_fractional_vs_baseline"] = m.R2_fractional - m.R2_baseline
    m["delta_fractional_vs_shuffled"] = m.R2_fractional - m.R2_shuffled
    m["delta_dominant_vs_baseline"] = m.R2_dominant - m.R2_baseline
    m.to_csv(OUTPUT_DIR / "per_pixel_final_comparison.csv", index=False)
    return m


def real_vs_shuffled_test(m):
    """Paired test: is real-fractional's per-pixel R2 systematically
    different from shuffled-control's, across all 70 pixels? This is the
    key statistical check for whether the tiny aggregate delta is real."""
    diff = (m.R2_fractional - m.R2_shuffled).to_numpy()
    t_stat, t_p = stats.ttest_rel(m.R2_fractional, m.R2_shuffled)
    w_stat, w_p = stats.wilcoxon(m.R2_fractional, m.R2_shuffled)
    n_real_better = int((diff > 0).sum())
    result = {
        "mean_delta_real_minus_shuffled": float(diff.mean()), "std_delta": float(diff.std()),
        "paired_ttest_p": float(t_p), "wilcoxon_p": float(w_p),
        "n_pixels_real_better": n_real_better, "n_pixels_shuffled_better": int((diff < 0).sum()),
        "n_pixels_tied": int((diff == 0).sum()), "n_total": len(m),
    }
    pd.DataFrame([result]).to_csv(OUTPUT_DIR / "real_vs_shuffled_ttest.csv", index=False)
    print("=== Real PFT vs. Shuffled PFT (paired, 70 pixels) ===")
    for k, v in result.items():
        print(f"  {k}: {v}")
    return result


def mixed_vs_pure(m):
    corr_purity = m["pft_purity"].corr(m["delta_fractional_vs_baseline"])
    corr_entropy = m["pft_entropy"].corr(m["delta_fractional_vs_baseline"])
    corr_purity_shuf = m["pft_purity"].corr(m["delta_fractional_vs_shuffled"])
    result = pd.DataFrame([{
        "correlation_purity_vs_delta_fractional_baseline": corr_purity,
        "correlation_entropy_vs_delta_fractional_baseline": corr_entropy,
        "correlation_purity_vs_delta_fractional_shuffled": corr_purity_shuf,
    }])
    result.to_csv(OUTPUT_DIR / "mixed_vs_pure_final.csv", index=False)
    print("\n=== Mixed vs. pure (final model) ===")
    print(result.to_string(index=False))

    fig, ax = plt.subplots(figsize=(8, 6), constrained_layout=True)
    ax.scatter(m.pft_entropy, m.delta_fractional_vs_baseline, alpha=0.7, s=50, label="vs. baseline")
    ax.scatter(m.pft_entropy, m.delta_fractional_vs_shuffled, alpha=0.7, s=50, marker="^", label="vs. shuffled")
    ax.axhline(0, color="#999", linewidth=0.8)
    ax.set_xlabel("PFT entropy (higher = more mixed)")
    ax.set_ylabel("ΔR² (fractional PFT model)")
    ax.set_title("Does fractional PFT help more for mixed pixels? (final 2022 model)", loc="left", fontsize=11)
    ax.legend(frameon=False)
    fig.savefig(OUTPUT_DIR / "mixed_vs_pure_final.png", dpi=150, facecolor="white")
    plt.close(fig)
    return result


def by_dominant_pft(m):
    g = m.groupby("dominant_pft").agg(
        n=("pixel_id", "size"),
        mean_delta_fractional=("delta_fractional_vs_baseline", "mean"),
        mean_delta_vs_shuffled=("delta_fractional_vs_shuffled", "mean"),
    ).reset_index().sort_values("mean_delta_fractional", ascending=False)
    g.to_csv(OUTPUT_DIR / "by_dominant_pft_final.csv", index=False)
    print("\n=== By dominant PFT class ===")
    print(g.to_string(index=False))
    return g


def seasonal_phase_breakdown():
    """Splits the 2022 forecast horizon into 3 phenological phases (using
    calendar-month bins as a simple, defensible proxy - green-up
    Mar-May, peak Jun-Aug, senescence Sep-Nov; Dec-Feb pooled with
    green-up's neighboring dormant season) and compares RMSE by phase."""
    phase_map = {}
    for m_ in [3, 4, 5]:
        phase_map[m_] = "green_up"
    for m_ in [6, 7, 8]:
        phase_map[m_] = "peak"
    for m_ in [9, 10, 11]:
        phase_map[m_] = "senescence"
    for m_ in [12, 1, 2]:
        phase_map[m_] = "dormant"

    rows = []
    for label, tag in [("baseline", "final_baseline"), ("fractional", "final_fractional"),
                         ("shuffled", "final_shuffled")]:
        pred_dir = OUTPUT_DIR / tag if label == "baseline" else OUTPUT_DIR / tag / WINNER_ARCH
        for f in pred_dir.glob("predictions_test2022_*.csv"):
            df = pd.read_csv(f, parse_dates=["date"])
            df["phase"] = df["date"].dt.month.map(phase_map)
            for phase, g in df.groupby("phase"):
                valid = g.dropna(subset=["ground_truth", "prediction"])
                if len(valid) < 2:
                    continue
                rmse = float(np.sqrt(np.mean((valid.ground_truth - valid.prediction) ** 2)))
                rows.append({"method": label, "pixel_id": f.stem.replace("predictions_test2022_", ""),
                              "phase": phase, "rmse": rmse, "n": len(valid)})
    df_all = pd.DataFrame(rows)
    summary = df_all.groupby(["method", "phase"])["rmse"].mean().reset_index()
    summary.to_csv(OUTPUT_DIR / "seasonal_phase_rmse.csv", index=False)
    print("\n=== Seasonal-phase RMSE (mean across pixels) ===")
    print(summary.pivot(index="phase", columns="method", values="rmse").to_string())
    return summary


def perturbation_sensitivity(sel, device):
    """PFT perturbation sweep on the FINALIZED (low_rank, fractional)
    model, exactly as in the multi-pixel study, for direct comparability."""
    pipeline = rc2.get_pipeline(device)
    conditioner = pvt.ARCHITECTURES[WINNER_ARCH](len(pvd.PFT_CLASSES), pipeline.model.config.d_model)
    model = Chronos2PFTModelV2.from_pretrained_base(pipeline.model, conditioner).to(device)
    model.pft_conditioner.load_state_dict(
        torch.load(OUTPUT_DIR / "final_fractional" / WINNER_ARCH / "conditioner.pt", map_location=device)
    )
    model.eval()

    compositions = [("100_forest", 1.0), ("75_forest_25_grass", 0.75), ("50_forest_50_grass", 0.5),
                     ("25_forest_75_grass", 0.25), ("100_grass", 0.0)]
    probes = {"evergreen": "TREES_NE", "mixed_forest_grass": "TREES_BD", "low_amplitude": "TREES_NE"}

    rows = []
    for pixel_id, forest_col in probes.items():
        df = pvd.load_pixel_df(pixel_id)
        pixel_rows = pvd.build_pixel_rows(df, context_end_year=2021, future_year=2022)
        context = [pixel_rows["target_context"]] + [c["context"] for c in pixel_rows["covariate_rows"]]
        future = [np.full(len(pixel_rows["target_future"]), np.nan, dtype="float32")] + \
                 [c["future"] for c in pixel_rows["covariate_rows"]]
        context_t = torch.tensor(np.stack(context), device=device)
        future_t = torch.tensor(np.stack(future), device=device)
        group_ids_t = torch.zeros(8, dtype=torch.long, device=device)
        is_target_t = torch.tensor([True] + [False] * 7, device=device)
        n_out = -(-len(pixel_rows["target_future"]) // 16)

        forest_idx = pvd.PFT_CLASSES.index(forest_col)
        grass_idx = pvd.PFT_CLASSES.index("GRASS_NAT")
        preds_by_comp = {}
        with torch.no_grad():
            for label, frac in compositions:
                pft_t = torch.zeros(8, len(pvd.PFT_CLASSES), device=device)
                vec = np.zeros(len(pvd.PFT_CLASSES), dtype="float32")
                vec[forest_idx] = frac
                vec[grass_idx] = 1 - frac
                pft_t[0] = torch.tensor(vec, device=device)
                preds, _ = model(context=context_t, group_ids=group_ids_t, future_covariates=future_t,
                                   num_output_patches=n_out, pft_features=pft_t, condition_rows=is_target_t)
                median_idx = preds.shape[1] // 2
                preds_by_comp[label] = preds[0, median_idx, : len(pixel_rows["target_future"])].cpu().numpy()
        stacked = np.stack(list(preds_by_comp.values()))
        max_diff = float(np.max(np.abs(stacked - stacked[0])))
        rows.append({"pixel_id": pixel_id, "max_abs_pred_diff": max_diff})
        print(f"[perturbation/{pixel_id}] max abs diff across 5 compositions (final low_rank model): {max_diff:.5f}")

    pd.DataFrame(rows).to_csv(OUTPUT_DIR / "perturbation_sensitivity_final.csv", index=False)


def main():
    sel = pvd.load_selection_table()
    device = "cuda" if torch.cuda.is_available() else "cpu"

    m = per_pixel_comparison(sel)
    real_vs_shuffled_test(m)
    mixed_vs_pure(m)
    by_dominant_pft(m)
    seasonal_phase_breakdown()
    perturbation_sensitivity(sel, device)
    print(f"\nSaved all final analysis to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
