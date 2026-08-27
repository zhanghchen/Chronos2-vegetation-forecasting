# Builds pooled multi-pixel batches for the Chronos-2 PFT-conditioning
# experiment: one target (LAI) row + 7 climate-covariate rows per pixel,
# all rows for a pixel sharing one group_id (so GroupSelfAttention mixes
# within a pixel's own target+covariates, exactly as in every other
# Chronos-2 experiment in this project), stacked across many pixels into
# one batch. PFT is attached at the item level via `pft_features`/
# `is_target_row` (see pft_multipixel_model.py) - never as a covariate row.
from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent
SITES_DIR = DATA_DIR / "data" / "processed" / "sites_pft_multipixel"
SELECTION_PATH = DATA_DIR / "data" / "processed" / "pft_diverse_pixels.csv"

CLIMATE_COLS = ["tmmx", "tmmn", "pr", "srad", "vpd", "sph", "vs"]
PFT_CLASSES = [
    "TREES_NE", "TREES_BD", "TREES_BE", "TREES_ND",
    "SHRUBS_NE", "SHRUBS_BE", "SHRUBS_BD", "SHRUBS_ND",
    "GRASS_NAT", "GRASS_MAN",
]
TEST_YEAR = 2022


def load_selection_table():
    return pd.read_csv(SELECTION_PATH)


def load_pixel_df(pixel_id):
    df = pd.read_csv(SITES_DIR / f"{pixel_id}.csv", parse_dates=["date"])
    return df.sort_values("date").reset_index(drop=True)


def fractional_vector(selection_row):
    return selection_row[[f"frac_{c}" for c in PFT_CLASSES]].to_numpy(dtype="float32")


def dominant_vector(selection_row):
    frac = fractional_vector(selection_row)
    onehot = np.zeros_like(frac)
    onehot[int(np.argmax(frac))] = 1.0
    return onehot


def pft_vector(selection_row, pft_mode="fractional"):
    if pft_mode == "fractional":
        return fractional_vector(selection_row)
    if pft_mode == "dominant":
        return dominant_vector(selection_row)
    if pft_mode == "baseline":
        return np.zeros(len(PFT_CLASSES), dtype="float32")
    raise ValueError(pft_mode)


def build_pixel_rows(df, pft_vec, context_end_year, future_year):
    """Returns per-pixel arrays: context/future for the target row and each
    climate-covariate row, plus the item's PFT vector.
    context = rows with year <= context_end_year; future = rows with
    year == future_year. Callers must pass context_end_year < future_year
    (e.g. 2020/2021 for a training window, 2021/2022 for the true held-out
    test) - this function itself does not special-case which is training
    vs. evaluation, so the caller is responsible for never using
    future_year=2022 in a gradient step."""
    years = df["date"].dt.year.to_numpy()
    context_mask = years <= context_end_year
    future_mask = years == future_year
    if not future_mask.any():
        raise ValueError(f"future_year={future_year} not found in this pixel's data")

    context_df = df[context_mask]
    future_df = df[future_mask]

    target_context = context_df["LAI"].to_numpy(dtype="float32")
    target_future = future_df["LAI"].to_numpy(dtype="float32")  # ground truth, used only for the loss/eval

    covariate_rows = []
    for c in CLIMATE_COLS:
        covariate_rows.append({
            "context": context_df[c].to_numpy(dtype="float32"),
            "future": future_df[c].to_numpy(dtype="float32"),  # known future climate
        })

    return {
        "target_context": target_context, "target_future": target_future,
        "covariate_rows": covariate_rows, "pft_vec": pft_vec,
        "future_dates": future_df["date"].to_numpy(), "prediction_length": len(future_df),
    }


def build_batch(pixel_ids, selection_table, context_end_year, future_year, pft_mode="fractional"):
    """Stacks `pixel_ids` into the row-major tensors Chronos2PFTModel.forward()
    expects. The target row's future_covariates are always NaN (LAI is
    always the thing being forecast, whether this batch is used for a
    training step against future_year's real LAI or a final eval against
    2022); `future_target` (built by the caller for training, or compared
    against `ground_truth` in per_pixel_meta for eval) supplies the labels.
    All pixels must share the same context/future length (true for this
    project's site CSVs, all extracted 2000-2022 on the same 8-day grid)."""
    sel_by_id = selection_table.set_index("pixel_id")
    contexts, futures, group_ids, pft_feats, is_target, future_targets = [], [], [], [], [], []
    per_pixel_meta = []

    context_len = None
    future_len = None
    for item_idx, pid in enumerate(pixel_ids):
        df = load_pixel_df(pid)
        pft_vec = pft_vector(sel_by_id.loc[pid], pft_mode=pft_mode)
        rows = build_pixel_rows(df, pft_vec, context_end_year=context_end_year, future_year=future_year)

        if context_len is None:
            context_len = len(rows["target_context"])
            future_len = rows["prediction_length"]
        assert len(rows["target_context"]) == context_len, f"{pid}: context length mismatch"
        assert rows["prediction_length"] == future_len, f"{pid}: future length mismatch"

        # target row
        contexts.append(rows["target_context"])
        futures.append(np.full(future_len, np.nan, dtype="float32"))  # to be forecast
        future_targets.append(rows["target_future"])  # real label, used by the loss
        group_ids.append(item_idx)
        pft_feats.append(pft_vec)
        is_target.append(True)

        # covariate rows (known future climate) - their future_target entry
        # is irrelevant: _compute_loss masks out any row with known future
        # covariates via patched_future_covariates_mask regardless of what
        # future_target holds for that row.
        for cov in rows["covariate_rows"]:
            contexts.append(cov["context"])
            futures.append(cov["future"])
            future_targets.append(np.full(future_len, np.nan, dtype="float32"))
            group_ids.append(item_idx)
            pft_feats.append(np.zeros_like(pft_vec))  # never read (is_target_row gates usage)
            is_target.append(False)

        per_pixel_meta.append({
            "pixel_id": pid, "future_dates": rows["future_dates"], "ground_truth": rows["target_future"],
        })

    batch = {
        "context": np.stack(contexts).astype("float32"),
        "future_covariates": np.stack(futures).astype("float32"),
        "future_target": np.stack(future_targets).astype("float32"),
        "group_ids": np.array(group_ids, dtype="int64"),
        "pft_features": np.stack(pft_feats).astype("float32"),
        "is_target_row": np.array(is_target, dtype=bool),
        "prediction_length": future_len,
    }
    return batch, per_pixel_meta
