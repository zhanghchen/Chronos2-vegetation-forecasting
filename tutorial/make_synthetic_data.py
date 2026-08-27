# Generates a small, self-contained synthetic dataset so this tutorial is
# runnable by anyone without access to any private project data. The
# series mimics the SHAPE of a real vegetation/climate forecasting problem
# (seasonal target driven by a few correlated climate covariates, observed
# on an 8-day step - the same cadence real satellite vegetation indices
# like LAI are typically composited at) but every number is fabricated.
#
# Run: python make_synthetic_data.py
# Produces: data/example_timeseries.csv (2 series, ~7 years of 8-day steps)
import numpy as np
import pandas as pd
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent / "data"
OUT_DIR.mkdir(exist_ok=True)

N_STEPS = 320          # ~7 years at an 8-day step
FREQ = "8D"
SERIES = {"site_A": 0.0, "site_B": 0.6}  # per-series seasonal offset, for a bit of diversity


def make_series(series_id: str, offset: float, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2016-01-01", periods=N_STEPS, freq=FREQ)
    t = np.arange(N_STEPS)
    period = 365.25 / 8  # one year, in 8-day steps

    temperature = 15 + 12 * np.sin(2 * np.pi * t / period - 0.6) + rng.normal(0, 1.2, N_STEPS)
    precipitation = np.clip(rng.gamma(shape=2.0, scale=1.3, size=N_STEPS) *
                             (1 + 0.4 * np.sin(2 * np.pi * t / period)), 0, None)
    vpd = np.clip(0.6 + 0.4 * np.sin(2 * np.pi * t / period - 0.3) + rng.normal(0, 0.06, N_STEPS), 0.05, None)
    radiation = 200 + 120 * np.sin(2 * np.pi * t / period - 0.5) + rng.normal(0, 10, N_STEPS)

    seasonal_target = 1.8 + offset + 1.6 * np.sin(2 * np.pi * t / period - 0.8) ** 3
    seasonal_target = np.clip(seasonal_target, 0.05, None)
    target = (
        seasonal_target
        + 0.015 * (temperature - temperature.mean())
        - 0.05 * (vpd - vpd.mean())
        + 0.002 * (precipitation - precipitation.mean())
        + rng.normal(0, 0.08, N_STEPS)
    )
    target = np.clip(target, 0.02, None)

    return pd.DataFrame({
        "date": dates, "series_id": series_id, "target": target,
        "temperature": temperature, "precipitation": precipitation,
        "vpd": vpd, "radiation": radiation,
    })


def main():
    dfs = [make_series(sid, offset, seed=i) for i, (sid, offset) in enumerate(SERIES.items())]
    df = pd.concat(dfs, ignore_index=True)
    out_path = OUT_DIR / "example_timeseries.csv"
    df.to_csv(out_path, index=False)
    print(f"Wrote {len(df)} rows ({df.series_id.nunique()} series) to {out_path}")
    print(df.head())


if __name__ == "__main__":
    main()
