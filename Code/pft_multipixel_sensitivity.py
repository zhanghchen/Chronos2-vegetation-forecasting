# PFT perturbation/sensitivity diagnostic + climate x PFT response curves
# for the multi-pixel experiment. Run on TWO models per condition:
#   - "validated": the actual experiment output (1 training step, selected
#     by held-out validation loss - see search_curve.csv, where val_loss
#     rose monotonically from step 0 for every LR/condition/experiment).
#   - "overfit_150step": the same architecture trained for the full 150
#     search steps at the best LR with NO early stopping - not the
#     recommended model, never evaluated against 2022, but the only way to
#     show whether the architecture retains the large PFT sensitivity the
#     16-pixel smoke test demonstrated, now that a properly validated
#     stopping rule rejects that much training.
import json

import numpy as np
import pandas as pd
import torch
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import common_pipeline as cp
import run_chronos2 as rc2
import pft_multipixel_dataset as pmd
import pft_multipixel_train as pmt
from pft_multipixel_model import Chronos2PFTModel

OUTPUT_DIR = cp.OUTPUTS_ROOT / "pft_multipixel" / "sensitivity"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

COMPOSITIONS = [
    ("100_forest", 1.00), ("75_forest_25_grass", 0.75), ("50_forest_50_grass", 0.50),
    ("25_forest_75_grass", 0.25), ("100_grass", 0.00),
]
PROBE_PIXELS = {
    "evergreen": "TREES_NE",              # near-pure forest (95% TREES_NE)
    "mixed_forest_grass": "TREES_BD",     # genuinely mixed (50/50)
    "low_amplitude": "TREES_NE",          # near-pure grass (84% GRASS_NAT)
}
PRECIP_ANOMALIES_PCT = [-50, -25, 0, 25, 50]  # % change applied to future `pr`


def build_overfit_model(train_pixel_ids, sel, pft_mode, device, lr, n_steps=150):
    pipeline = rc2.get_pipeline(device)
    model = Chronos2PFTModel.from_pretrained_base(pipeline.model, pft_dim=len(pmd.PFT_CLASSES)).to(device)
    model.freeze_base()
    optimizer = torch.optim.Adam(model.pft_encoder.parameters(), lr=lr)
    windows_tensors = [(pmt.build_window_tensors(train_pixel_ids, sel, w, pft_mode, device))
                        for w in pmt.SEARCH_WINDOWS]
    windows_tensors = [(t, n) for (t, pl, n, m) in windows_tensors]
    for step in range(n_steps):
        model.train()
        pmt.run_step(model, windows_tensors, optimizer)
    return model


def load_validated_model(tag, pft_mode, device):
    out_dir = cp.OUTPUTS_ROOT / "pft_multipixel" / tag / pft_mode
    pipeline = rc2.get_pipeline(device)
    model = Chronos2PFTModel.from_pretrained_base(pipeline.model, pft_dim=len(pmd.PFT_CLASSES)).to(device)
    state = torch.load(out_dir / "pft_encoder.pt", map_location=device)
    model.pft_encoder.load_state_dict(state)
    model.eval()
    return model


def perturbation_sweep(model, pixel_id, forest_col, sel, device):
    sel_by_id = sel.set_index("pixel_id")
    df = pmd.load_pixel_df(pixel_id)
    rows = pmd.build_pixel_rows(df, None, context_end_year=2021, future_year=2022)

    forest_idx = pmd.PFT_CLASSES.index(forest_col)
    grass_idx = pmd.PFT_CLASSES.index("GRASS_NAT")

    context = [rows["target_context"]] + [c["context"] for c in rows["covariate_rows"]]
    future = [np.full(len(rows["target_future"]), np.nan, dtype="float32")] + [c["future"] for c in rows["covariate_rows"]]
    context_t = torch.tensor(np.stack(context), device=device)
    future_t = torch.tensor(np.stack(future), device=device)
    group_ids_t = torch.zeros(8, dtype=torch.long, device=device)
    is_target_t = torch.tensor([True] + [False] * 7, device=device)
    n_out = -(-len(rows["target_future"]) // 16)

    preds_by_comp = {}
    with torch.no_grad():
        for label, frac in COMPOSITIONS:
            pft_t = torch.zeros(8, len(pmd.PFT_CLASSES), device=device)
            vec = np.zeros(len(pmd.PFT_CLASSES), dtype="float32")
            vec[forest_idx] = frac
            vec[grass_idx] = 1 - frac
            pft_t[0] = torch.tensor(vec, device=device)
            preds, _ = model(context=context_t, group_ids=group_ids_t, future_covariates=future_t,
                               num_output_patches=n_out, pft_features=pft_t, is_target_row=is_target_t)
            median_idx = preds.shape[1] // 2
            preds_by_comp[label] = preds[0, median_idx, : len(rows["target_future"])].cpu().numpy()

    stacked = np.stack(list(preds_by_comp.values()))
    max_diff = float(np.max(np.abs(stacked - stacked[0])))
    return preds_by_comp, rows["target_future"], rows["future_dates"], max_diff


def climate_response_curve(model, pixel_id, forest_col, sel, device):
    """Predicted LAI (mean over the 2022 forecast horizon) vs. a
    precipitation anomaly applied to the known future `pr` covariate, for
    3 fixed PFT compositions (100% forest / 50-50 / 100% grass)."""
    df = pmd.load_pixel_df(pixel_id)
    rows = pmd.build_pixel_rows(df, None, context_end_year=2021, future_year=2022)
    forest_idx = pmd.PFT_CLASSES.index(forest_col)
    grass_idx = pmd.PFT_CLASSES.index("GRASS_NAT")

    context = [rows["target_context"]] + [c["context"] for c in rows["covariate_rows"]]
    context_t = torch.tensor(np.stack(context), device=device)
    group_ids_t = torch.zeros(8, dtype=torch.long, device=device)
    is_target_t = torch.tensor([True] + [False] * 7, device=device)
    n_out = -(-len(rows["target_future"]) // 16)

    results = {}
    for comp_label, frac in [("100% forest", 1.0), ("50/50 mix", 0.5), ("100% grass", 0.0)]:
        curve = []
        for pct in PRECIP_ANOMALIES_PCT:
            future = [np.full(len(rows["target_future"]), np.nan, dtype="float32")]
            for c_name, cov in zip(cp.FEATURE_COLS, rows["covariate_rows"]):
                fut = cov["future"].copy()
                if c_name == "pr":
                    fut = fut * (1 + pct / 100.0)
                future.append(fut)
            future_t = torch.tensor(np.stack(future), device=device)
            pft_t = torch.zeros(8, len(pmd.PFT_CLASSES), device=device)
            vec = np.zeros(len(pmd.PFT_CLASSES), dtype="float32")
            vec[forest_idx] = frac
            vec[grass_idx] = 1 - frac
            pft_t[0] = torch.tensor(vec, device=device)
            with torch.no_grad():
                preds, _ = model(context=context_t, group_ids=group_ids_t, future_covariates=future_t,
                                   num_output_patches=n_out, pft_features=pft_t, is_target_row=is_target_t)
            median_idx = preds.shape[1] // 2
            mean_lai = float(preds[0, median_idx, : len(rows["target_future"])].mean().cpu())
            curve.append(mean_lai)
        results[comp_label] = curve
    return results


def main():
    sel = pmd.load_selection_table()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    all_pixels = sel["pixel_id"].tolist()

    with open(cp.OUTPUTS_ROOT / "pft_multipixel" / "expA_temporal" / "fractional" / "config.json") as f:
        best_cfg = json.load(f)
    print(f"Best config for expA_temporal/fractional: {best_cfg}")

    models = {
        "validated_1step": load_validated_model("expA_temporal", "fractional", device),
        "overfit_150step": build_overfit_model(all_pixels, sel, "fractional", device, lr=best_cfg["lr"], n_steps=150),
    }

    summary_rows = []
    fig, axes = plt.subplots(len(PROBE_PIXELS), 2, figsize=(14, 4 * len(PROBE_PIXELS)), constrained_layout=True)
    for row_i, (pixel_id, forest_col) in enumerate(PROBE_PIXELS.items()):
        for model_label, model in models.items():
            preds_by_comp, ground_truth, dates, max_diff = perturbation_sweep(model, pixel_id, forest_col, sel, device)
            summary_rows.append({"pixel_id": pixel_id, "model": model_label, "max_abs_diff": max_diff})
            print(f"[{pixel_id}/{model_label}] max abs pred diff across 5 PFT compositions: {max_diff:.5f}")

            ax = axes[row_i, 0] if model_label == "validated_1step" else axes[row_i, 1]
            for label, _ in COMPOSITIONS:
                ax.plot(dates, preds_by_comp[label], marker="o", markersize=2.5, linewidth=1.3, label=label)
            ax.plot(dates, ground_truth, color="black", linewidth=2, linestyle="--", label="Observed", alpha=0.6)
            ax.set_title(f"{pixel_id} ({model_label})", fontsize=10, loc="left")
            ax.tick_params(axis="x", rotation=20, labelsize=7)
            if row_i == 0:
                ax.legend(frameon=False, fontsize=6.5, ncol=2)
    fig.suptitle("PFT perturbation sweep, 2022: validated (1-step) vs. deliberately-overfit (150-step) model",
                 fontsize=13, fontweight="bold")
    fig.savefig(OUTPUT_DIR / "perturbation_sweep_all_pixels.png", dpi=150, facecolor="white")
    plt.close(fig)

    pd.DataFrame(summary_rows).to_csv(OUTPUT_DIR / "perturbation_summary.csv", index=False)

    # Climate x PFT response curves - overfit model only (validated model's
    # PFT channel is ~0, so its response curves would be flat by construction).
    fig2, axes2 = plt.subplots(1, len(PROBE_PIXELS), figsize=(6 * len(PROBE_PIXELS), 5), constrained_layout=True)
    response_rows = []
    for i, (pixel_id, forest_col) in enumerate(PROBE_PIXELS.items()):
        curves = climate_response_curve(models["overfit_150step"], pixel_id, forest_col, sel, device)
        ax = axes2[i]
        for comp_label, vals in curves.items():
            ax.plot(PRECIP_ANOMALIES_PCT, vals, marker="o", label=comp_label)
            for pct, v in zip(PRECIP_ANOMALIES_PCT, vals):
                response_rows.append({"pixel_id": pixel_id, "composition": comp_label,
                                        "precip_anomaly_pct": pct, "mean_predicted_lai": v})
        ax.set_xlabel("Precipitation anomaly (%)")
        ax.set_ylabel("Mean predicted LAI, 2022")
        ax.set_title(pixel_id, fontsize=11, loc="left")
        ax.legend(frameon=False, fontsize=8)
    fig2.suptitle("Climate x PFT response (overfit_150step model, illustrative - not the validated model)",
                  fontsize=12, fontweight="bold")
    fig2.savefig(OUTPUT_DIR / "climate_pft_response_curves.png", dpi=150, facecolor="white")
    plt.close(fig2)
    pd.DataFrame(response_rows).to_csv(OUTPUT_DIR / "climate_pft_response_curves.csv", index=False)

    print(f"\nSaved sensitivity diagnostics to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
