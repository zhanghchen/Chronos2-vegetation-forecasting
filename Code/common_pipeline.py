# Shared data loading, Chronos-2 input formatting, and evaluation metrics for
# the vegetation-forecasting experiments. Kept independent of the AELSTM
# project's own common_pipeline.py (only the *data* is reused, not the code),
# but the metric definitions are deliberately ported 1:1 so results are
# directly comparable.
from math import sqrt
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score

DATA_DIR = Path(__file__).resolve().parent.parent
SITES_DIR = DATA_DIR / "data" / "processed" / "sites"
OUTPUTS_ROOT = DATA_DIR / "outputs"

TARGET_COL = "LAI"
FEATURE_COLS = ["tmmx", "tmmn", "pr", "srad", "vpd", "sph", "vs"]
TEST_YEAR = 2022
SITES = ["low_amplitude", "high_amplitude_deciduous", "evergreen"]

MODEL_ID = "amazon/chronos-2"

# LoRA fine-tuning hyperparameters, taken directly from Amazon's own
# chronos-2-quickstart notebook example (not invented) for reproducibility.
FINETUNE_LEARNING_RATE = 1e-4
FINETUNE_NUM_STEPS = 1000
FINETUNE_BATCH_SIZE = 32


def load_site_df(site):
    df = pd.read_csv(SITES_DIR / f"{site}.csv", parse_dates=["date"])
    return df.sort_values("date").reset_index(drop=True)


def build_chronos_inputs(df, target_col=TARGET_COL, feature_cols=FEATURE_COLS, test_year=TEST_YEAR):
    """Splits a site's full dataframe at the same year boundary AELSTM used
    (train < test_year, test = all of test_year) into a Chronos-2 input dict:
      - target: historical LAI (the context)
      - past_covariates: historical climate, aligned to the context
      - future_covariates: the *actual observed* climate during the test
        year, supplied as known future forcings (per the project's research
        question: forecast LAI given known future climate).
    """
    years = df["date"].dt.year.values
    split_idx = int(np.argmax(years == test_year))

    context = df.iloc[:split_idx]
    future = df.iloc[split_idx:]

    input_dict = {
        "target": context[target_col].to_numpy(dtype="float32"),
        "past_covariates": {c: context[c].to_numpy(dtype="float32") for c in feature_cols},
        "future_covariates": {c: future[c].to_numpy(dtype="float32") for c in feature_cols},
    }
    prediction_length = len(future)
    future_dates = future["date"].to_numpy()
    ground_truth = future[target_col].to_numpy(dtype="float32")
    return input_dict, prediction_length, future_dates, ground_truth


def cal_mape(y_true, y_pred):
    """Percent error over rows where both true & predicted are positive -
    mirrors AELSTM's Cal_mape exactly, so MAPE is computed the same way."""
    df = pd.DataFrame({"A": y_true, "B": y_pred})
    df = df[(df.A > 0) & (df.B > 0)]
    if len(df) == 0:
        return 0.0
    return float((np.abs((df.A - df.B) / df.A)).mean() * 100)


def compute_metrics(y_true, y_pred):
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    rmse = sqrt(mean_squared_error(y_true, y_pred))
    mae = mean_absolute_error(y_true, y_pred)
    mape = cal_mape(y_true, y_pred)
    r2 = r2_score(y_true, y_pred)
    pearson_r = float(np.corrcoef(y_true, y_pred)[0, 1])
    return {"RMSE": rmse, "MAE": mae, "MAPE": mape, "R2": r2, "Pearson_r": pearson_r}
