# Expanded rolling-window dataset for the PFT-v2 research loop. Same row-
# stacking convention as pft_multipixel_dataset.py (1 target + 7 climate
# covariate rows per pixel, shared group_id), but with MANY more rolling
# one-year-ahead (context_end_year -> future_year) transitions than the
# original 2-window design, to give the PFT conditioning head enough real,
# independent supervision to separate a generalizing signal from
# single-year noise (the diagnosed cause of the original overfitting).
#
# TRAIN_WINDOWS: 2010->2011 ... 2017->2018 (8 transitions)
# VAL_WINDOWS:   2018->2019, 2019->2020, 2020->2021 (3 transitions, held out
#                for model/hyperparameter selection only - never used for
#                gradients)
# TEST_WINDOW:   2021->2022 (the true held-out year; touched exactly once,
#                at the very end, for the finalized method only)
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

TRAIN_WINDOWS = [(y, y + 1) for y in range(2010, 2018)]   # 8 transitions
VAL_WINDOWS = [(2018, 2019), (2019, 2020), (2020, 2021)]  # 3 transitions
FINAL_WINDOWS = TRAIN_WINDOWS + VAL_WINDOWS               # 11, for the final refit
TEST_WINDOW = (2021, 2022)


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


def shuffled_pft_table(selection_table, seed):
    """Returns a copy of the selection table with PFT fraction columns
    permuted across pixels (breaking the true pixel<->composition link
    while preserving the marginal distribution of PFT values used) - the
    key control for whether a model benefits from REAL vegetation
    information or just from extra conditioning capacity/noise."""
    rng = np.random.default_rng(seed)
    perm = rng.permutation(len(selection_table))
    shuffled = selection_table.copy()
    frac_cols = [f"frac_{c}" for c in PFT_CLASSES]
    shuffled[frac_cols] = selection_table[frac_cols].to_numpy()[perm]
    shuffled["dominant_pft"] = selection_table["dominant_pft"].to_numpy()[perm]
    shuffled["pft_purity"] = selection_table["pft_purity"].to_numpy()[perm]
    shuffled["pft_entropy"] = selection_table["pft_entropy"].to_numpy()[perm]
    return shuffled


def build_pixel_rows(df, context_end_year, future_year):
    years = df["date"].dt.year.to_numpy()
    context_mask = years <= context_end_year
    future_mask = years == future_year
    if not future_mask.any():
        raise ValueError(f"future_year={future_year} not found in this pixel's data")

    context_df = df[context_mask]
    future_df = df[future_mask]

    target_context = context_df["LAI"].to_numpy(dtype="float32")
    target_future = future_df["LAI"].to_numpy(dtype="float32")

    covariate_rows = [
        {"context": context_df[c].to_numpy(dtype="float32"), "future": future_df[c].to_numpy(dtype="float32")}
        for c in CLIMATE_COLS
    ]
    return {
        "target_context": target_context, "target_future": target_future,
        "covariate_rows": covariate_rows,
        "future_dates": future_df["date"].to_numpy(), "prediction_length": len(future_df),
    }


def build_batch(pixel_ids, selection_table, context_end_year, future_year, pft_mode="fractional"):
    sel_by_id = selection_table.set_index("pixel_id")
    contexts, futures, group_ids, pft_feats, is_target, future_targets = [], [], [], [], [], []
    per_pixel_meta = []

    context_len = None
    future_len = None
    for item_idx, pid in enumerate(pixel_ids):
        df = load_pixel_df(pid)
        pft_vec = pft_vector(sel_by_id.loc[pid], pft_mode=pft_mode)
        rows = build_pixel_rows(df, context_end_year=context_end_year, future_year=future_year)

        if context_len is None:
            context_len = len(rows["target_context"])
            future_len = rows["prediction_length"]
        assert len(rows["target_context"]) == context_len, f"{pid}: context length mismatch"
        assert rows["prediction_length"] == future_len, f"{pid}: future length mismatch"

        contexts.append(rows["target_context"])
        futures.append(np.full(future_len, np.nan, dtype="float32"))
        future_targets.append(rows["target_future"])
        group_ids.append(item_idx)
        pft_feats.append(pft_vec)
        is_target.append(True)

        for cov in rows["covariate_rows"]:
            contexts.append(cov["context"])
            futures.append(cov["future"])
            future_targets.append(np.full(future_len, np.nan, dtype="float32"))
            group_ids.append(item_idx)
            pft_feats.append(np.zeros_like(pft_vec))
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
