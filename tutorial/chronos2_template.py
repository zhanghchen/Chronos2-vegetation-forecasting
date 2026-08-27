# chronos2_template.py
#
# Reusable Chronos-2 data-preparation and forecasting pipeline. Copy this
# file into a new project and edit only the CONFIG block below to point it
# at a different dataset - everything downstream (validation, frequency
# alignment, Chronos-2 input construction, forecasting, evaluation,
# plotting) is written generically against the config, not against any
# specific column names.
#
# Verified against the installed chronos-forecasting source
# (src/chronos/chronos2/{pipeline,dataset}.py) - every Chronos-2 API call
# below matches the current signatures, not assumed or invented.
#
# Requires: chronos-forecasting, torch, pandas, numpy, scikit-learn,
# matplotlib.

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from math import sqrt
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd
import torch
import matplotlib.pyplot as plt
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score

# =============================================================================
# CONFIG - edit this block for a new dataset. Nothing below this block
# should need to change to adapt the pipeline to a different domain.
# =============================================================================

MODEL_ID = "amazon/chronos-2"

TIMESTAMP_COLUMN = "date"          # column holding the timestamp of each row
ID_COLUMN = "series_id"            # column identifying which series a row belongs to
                                    # (use a constant column, e.g. "site", if you only have one series)
TARGET = "target"                  # column to forecast

# Covariates known only in the past (e.g. a sensor reading with no forecast
# product available) go in PAST_COVARIATES only. Covariates you will also
# have future values for (e.g. a weather forecast, a calendar feature) go
# in FUTURE_COVARIATES - and MUST also appear in PAST_COVARIATES, since
# Chronos-2 requires historical values for every covariate the model sees.
PAST_COVARIATES: list[str] = ["temperature", "precipitation", "vpd"]
FUTURE_COVARIATES: list[str] = ["temperature", "precipitation", "vpd"]

FREQ = "8D"                        # pandas frequency string for this dataset's regular time step
                                    # (e.g. "h" hourly, "D" daily, "8D" 8-day composite, "W" weekly, "MS" month start)

PREDICTION_LENGTH = 46             # forecast horizon, in TIME STEPS (not days/months - see tutorial Part 8)
CONTEXT_LENGTH: int | None = None  # None = use the model's default (2048 for Chronos-2); cap it explicitly if desired


# =============================================================================
# 1. LOAD
# =============================================================================

def load_data(path: str | Path) -> pd.DataFrame:
    """Loads a long-format CSV: one row per (series, timestamp), with the
    target and covariate columns declared above. Any additional columns in
    the file are ignored - only TIMESTAMP_COLUMN, ID_COLUMN, TARGET, and
    the covariate columns are used downstream."""
    df = pd.read_csv(path)
    df[TIMESTAMP_COLUMN] = pd.to_datetime(df[TIMESTAMP_COLUMN])
    if ID_COLUMN not in df.columns:
        df[ID_COLUMN] = "series_0"  # single-series convenience default
    return df.sort_values([ID_COLUMN, TIMESTAMP_COLUMN]).reset_index(drop=True)


# =============================================================================
# 2. VALIDATE
# =============================================================================

@dataclass
class ValidationReport:
    n_series: int
    n_rows: int
    missing_columns: list[str] = field(default_factory=list)
    nan_counts: dict[str, int] = field(default_factory=dict)
    irregular_series: list[str] = field(default_factory=list)
    ok: bool = True

    def summary(self) -> str:
        lines = [f"{self.n_series} series, {self.n_rows} rows total"]
        if self.missing_columns:
            lines.append(f"MISSING REQUIRED COLUMNS: {self.missing_columns}")
        for col, n in self.nan_counts.items():
            if n:
                lines.append(f"  {col}: {n} NaN values")
        if self.irregular_series:
            lines.append(f"IRREGULAR TIMESTAMPS in series: {self.irregular_series} "
                          f"(run align_frequency() before continuing)")
        lines.append("Status: " + ("OK" if self.ok else "ISSUES FOUND - see above"))
        return "\n".join(lines)


def validate_data(df: pd.DataFrame, freq: str = FREQ) -> ValidationReport:
    """Checks the four things that silently break a Chronos-2 forecast if
    missed: required columns present, target/covariate NaNs, and irregular
    timestamps per series (Chronos-2's own `predict_df` requires perfectly
    regular timestamps; the lower-level API tolerates irregularity but
    every step is then implicitly treated as one time unit regardless of
    its real duration - see tutorial Part 8)."""
    required = [TIMESTAMP_COLUMN, ID_COLUMN, TARGET] + PAST_COVARIATES
    missing = [c for c in required if c not in df.columns]

    nan_counts = {c: int(df[c].isna().sum()) for c in required if c in df.columns}

    irregular = []
    for series_id, g in df.groupby(ID_COLUMN):
        ts = g[TIMESTAMP_COLUMN].sort_values()
        deltas = ts.diff().dropna().dt.total_seconds()
        expected = pd.tseries.frequencies.to_offset(freq).nanos / 1e9 if freq[-1] not in "MYQ" else None
        if expected is not None and deltas.nunique() > 1 and (deltas != expected).any():
            irregular.append(series_id)

    ok = not missing and not any(nan_counts.values()) and not irregular
    report = ValidationReport(
        n_series=df[ID_COLUMN].nunique() if ID_COLUMN in df.columns else 0,
        n_rows=len(df), missing_columns=missing, nan_counts=nan_counts,
        irregular_series=irregular, ok=ok,
    )
    print(report.summary())
    return report


# =============================================================================
# 3. ALIGN FREQUENCY
# =============================================================================

def align_frequency(df: pd.DataFrame, freq: str = FREQ, method: str = "linear") -> pd.DataFrame:
    """Reindexes every series onto a strictly regular timestamp grid at
    `freq`, interpolating small gaps (`method`, forwarded to
    `pd.Series.interpolate`) and leaving larger gaps as NaN rather than
    fabricating long stretches of invented data. Run this whenever
    validate_data() reports irregular timestamps, or whenever you plan to
    use predict_df (which requires regular timestamps outright)."""
    cols = [TARGET] + sorted(set(PAST_COVARIATES) | set(FUTURE_COVARIATES))
    aligned = []
    for series_id, g in df.groupby(ID_COLUMN):
        g = g.set_index(TIMESTAMP_COLUMN).sort_index()
        full_index = pd.date_range(g.index.min(), g.index.max(), freq=freq)
        g = g.reindex(full_index)
        for c in cols:
            if c in g.columns:
                g[c] = g[c].interpolate(method=method, limit_direction="both")
        g[ID_COLUMN] = series_id
        g.index.name = TIMESTAMP_COLUMN
        aligned.append(g.reset_index())
    return pd.concat(aligned, ignore_index=True)


# =============================================================================
# 4. PREPARE CHRONOS-2 INPUTS
# =============================================================================

def prepare_chronos_inputs(
    df: pd.DataFrame,
    split_date,
    series_ids: Sequence[str] | None = None,
) -> tuple[list[dict], dict[str, np.ndarray], dict[str, np.ndarray]]:
    """Splits each series at `split_date` into context (everything before)
    and future (everything from `split_date` onward), and builds the
    list-of-dicts input Chronos-2's low-level `predict`/`predict_quantiles`/
    `fit` API expects (verified against chronos2/pipeline.py's own
    docstring). Returns:
      - `inputs`: one dict per series, ready to pass to a Chronos-2 pipeline
      - `ground_truth`: {series_id: array of true future target values}
      - `future_dates`: {series_id: array of future timestamps}

    Every covariate in FUTURE_COVARIATES gets a `future_covariates` entry
    with real future values (must already be known - a weather forecast,
    a calendar feature, etc.). Covariates that are ONLY in PAST_COVARIATES
    are past-only and are automatically left out of future_covariates,
    which tells Chronos-2 they are not known ahead of time.
    """
    if series_ids is None:
        series_ids = sorted(df[ID_COLUMN].unique())

    inputs, ground_truth, future_dates = [], {}, {}
    for sid in series_ids:
        g = df[df[ID_COLUMN] == sid].sort_values(TIMESTAMP_COLUMN)
        context = g[g[TIMESTAMP_COLUMN] < split_date]
        future = g[g[TIMESTAMP_COLUMN] >= split_date]
        if len(future) == 0:
            warnings.warn(f"series {sid!r} has no rows on/after split_date - skipping")
            continue

        item = {
            "target": context[TARGET].to_numpy(dtype="float32"),
            "past_covariates": {c: context[c].to_numpy(dtype="float32") for c in PAST_COVARIATES},
            "future_covariates": {c: future[c].to_numpy(dtype="float32") for c in FUTURE_COVARIATES},
        }
        inputs.append(item)
        ground_truth[sid] = future[TARGET].to_numpy(dtype="float32")
        future_dates[sid] = future[TIMESTAMP_COLUMN].to_numpy()

    return inputs, ground_truth, future_dates


# =============================================================================
# 5. RUN FORECAST
# =============================================================================

def load_pipeline(device: str | None = None, model_id: str = MODEL_ID):
    """Loads the pretrained Chronos-2 pipeline. `BaseChronosPipeline` auto-
    detects the correct concrete pipeline class (Chronos2Pipeline) from the
    model's config - this is the same entry point Amazon's own quickstart
    notebook uses. device=None auto-selects "cuda" if available, else "cpu"."""
    from chronos import BaseChronosPipeline

    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
    pipeline = BaseChronosPipeline.from_pretrained(model_id, device_map=device)

    # Verify the load succeeded and report the model's default context/horizon.
    assert hasattr(pipeline, "predict_quantiles"), "Loaded pipeline does not expose predict_quantiles - unexpected pipeline class"
    print(f"Loaded {model_id} on {device}. "
          f"Default context_length={pipeline.model_context_length}, "
          f"default prediction_length={pipeline.model_prediction_length}, "
          f"output_patch_size={pipeline.model_output_patch_size}.")
    return pipeline


def run_forecast(
    pipeline,
    inputs: list[dict],
    prediction_length: int = PREDICTION_LENGTH,
    quantile_levels: list[float] = (0.1, 0.5, 0.9),
    context_length: int | None = CONTEXT_LENGTH,
):
    """Thin wrapper around `pipeline.predict_quantiles` (zero-shot: no
    parameters are updated). Returns (quantiles, median) where quantiles[i]
    has shape (n_variates, prediction_length, len(quantile_levels)) and
    median[i] has shape (n_variates, prediction_length), one entry per
    series in `inputs`, in the same order."""
    kwargs = {}
    if context_length is not None:
        kwargs["context_length"] = context_length
    quantiles, median = pipeline.predict_quantiles(
        inputs=inputs, prediction_length=prediction_length,
        quantile_levels=list(quantile_levels), **kwargs,
    )
    return quantiles, median


# =============================================================================
# 6. EVALUATE
# =============================================================================

def evaluate_forecast(y_true, y_pred) -> dict[str, float]:
    """RMSE, MAE, R-squared, and Pearson correlation between the observed
    and predicted series. All four are standard regression/forecast-
    accuracy metrics:
      - RMSE: average error magnitude, in the target's own units, penalizing large errors more.
      - MAE: average absolute error, in the target's own units, robust to outliers.
      - R2: fraction of the observed variance explained by the forecast (1.0 = perfect, 0.0 = no
            better than predicting the mean, negative = worse than predicting the mean).
      - Pearson r: linear correlation between observed and predicted, independent of scale/bias.
    """
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    mask = np.isfinite(y_true) & np.isfinite(y_pred)
    y_true, y_pred = y_true[mask], y_pred[mask]
    if len(y_true) < 2 or np.std(y_true) == 0:
        return {"RMSE": np.nan, "MAE": np.nan, "R2": np.nan, "Pearson_r": np.nan, "n": len(y_true)}
    return {
        "RMSE": sqrt(mean_squared_error(y_true, y_pred)),
        "MAE": mean_absolute_error(y_true, y_pred),
        "R2": r2_score(y_true, y_pred),
        "Pearson_r": float(np.corrcoef(y_true, y_pred)[0, 1]),
        "n": len(y_true),
    }


# =============================================================================
# 7. PLOT
# =============================================================================

def plot_forecast(dates, y_true, y_pred, y_lower=None, y_upper=None, title="Forecast", ax=None):
    """Observed-vs-predicted time series, with an optional uncertainty band
    (pass the low/high quantile arrays from run_forecast's `quantiles`
    output, e.g. quantiles[i][..., 0] and quantiles[i][..., -1] for the
    0.1/0.9 levels)."""
    if ax is None:
        fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.plot(dates, y_true, color="black", linewidth=1.8, label="Observed")
    ax.plot(dates, y_pred, color="#2F6F5E", linewidth=1.8, marker="o", markersize=3, label="Predicted (median)")
    if y_lower is not None and y_upper is not None:
        ax.fill_between(dates, y_lower, y_upper, color="#2F6F5E", alpha=0.15, label="Prediction interval")
    ax.set_title(title)
    ax.legend(frameon=False)
    ax.tick_params(axis="x", rotation=20)
    return ax


def plot_scatter(y_true, y_pred, title="Observed vs. Predicted", ax=None):
    if ax is None:
        fig, ax = plt.subplots(figsize=(5.5, 5.5))
    y_true, y_pred = np.asarray(y_true, dtype=float), np.asarray(y_pred, dtype=float)
    ax.scatter(y_true, y_pred, alpha=0.6, s=20, color="#2F6F5E")
    lims = [min(y_true.min(), y_pred.min()), max(y_true.max(), y_pred.max())]
    ax.plot(lims, lims, color="#999", linestyle="--", linewidth=1, label="1:1 line")
    ax.set_xlabel("Observed"); ax.set_ylabel("Predicted"); ax.set_title(title)
    ax.legend(frameon=False)
    return ax


def plot_residuals(dates, y_true, y_pred, title="Residuals (Predicted - Observed)", ax=None):
    if ax is None:
        fig, ax = plt.subplots(figsize=(10, 3.5))
    residuals = np.asarray(y_pred, dtype=float) - np.asarray(y_true, dtype=float)
    ax.axhline(0, color="#999", linewidth=1)
    ax.plot(dates, residuals, color="#B5651D", marker="o", markersize=3, linewidth=1.2)
    ax.set_title(title)
    ax.tick_params(axis="x", rotation=20)
    return ax


if __name__ == "__main__":
    print(__doc__)
    print("This file defines the reusable pipeline functions; see chronos2_tutorial.ipynb "
          "or TUTORIAL.md for a runnable end-to-end example.")
